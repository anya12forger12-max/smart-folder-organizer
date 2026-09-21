"""Local history database (SQLite) per the versioned schema in schema.py.

History stores METADATA ONLY: operation ids, paths, identities, statuses,
timestamps. Never file contents. The database records what happened; it is
never the authority for executing anything - journals are.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sfo.persistence.schema import initialize

_KIND_ORGANIZE = "ORGANIZE"
_KIND_UNDO = "UNDO"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        # History contains user file paths: always private, regardless of umask.
        os.chmod(self.path, 0o600)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        initialize(conn)
        return conn

    # -- transactions ----------------------------------------------------
    def record_transaction(
        self,
        kind: str,
        root: Path,
        plan_fingerprint: str = "",
        external_id: str | None = None,
    ) -> int:
        conn = self.connect()
        try:
            cur = conn.execute(
                "INSERT INTO transactions(kind, root, plan_fingerprint, status,"
                " created_at, updated_at) VALUES (?, ?, ?, 'PLANNED', ?, ?)",
                (kind, str(root), plan_fingerprint, _now(), _now()),
            )
            txn_id = int(cur.lastrowid)
            if external_id:
                conn.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                    (f"opmap:{txn_id}", external_id),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                    (f"opmap-ext:{external_id}", str(txn_id)),
                )
            conn.commit()
            return txn_id
        finally:
            conn.close()

    def set_transaction_status(self, txn_id: int, status: str) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE transactions SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), txn_id),
            )
            conn.commit()
        finally:
            conn.close()

    def record_operation(
        self,
        txn_id: int,
        seq: int,
        op_kind: str,
        source: Path,
        destination: Path,
        expected_identity: str | None,
        result_identity: str | None,
        status: str,
        error: str | None = None,
    ) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO operations(transaction_id, seq, op_kind,"
                " source, destination, expected_identity, result_identity, status,"
                " error, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    txn_id,
                    seq,
                    op_kind,
                    str(source),
                    str(destination),
                    expected_identity,
                    result_identity,
                    status,
                    error,
                    _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # -- queries -----------------------------------------------------------
    def list_transactions(
        self, limit: int = 20, kinds: tuple[str, ...] = (_KIND_ORGANIZE,)
    ) -> list[dict]:
        conn = self.connect()
        try:
            placeholders = ",".join("?" for _ in kinds)
            rows = conn.execute(
                f"SELECT * FROM transactions WHERE kind IN ({placeholders})"
                " ORDER BY id DESC LIMIT ?",
                (*kinds, limit),
            ).fetchall()
            return [dict(r) | self._ext(conn, r["id"]) for r in rows]
        finally:
            conn.close()

    def get_transaction(self, external_or_int: str | int) -> dict | None:
        conn = self.connect()
        try:
            if isinstance(external_or_int, int):
                row = conn.execute(
                    "SELECT * FROM transactions WHERE id = ?", (external_or_int,)
                ).fetchone()
                return dict(row) | self._ext(conn, row["id"]) if row else None
            raw = conn.execute(
                "SELECT value FROM meta WHERE key = ?",
                (f"opmap-ext:{external_or_int}",),
            ).fetchone()
            if not raw:
                return None
            row = conn.execute(
                "SELECT * FROM transactions WHERE id = ?", (int(raw["value"]),)
            ).fetchone()
            return dict(row) | self._ext(conn, row["id"]) if row else None
        finally:
            conn.close()

    def transaction_operations(self, txn_id: int) -> list[dict]:
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM operations WHERE transaction_id = ? ORDER BY seq",
                (txn_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def has_undo_for(self, external_id: str) -> bool:
        conn = self.connect()
        try:
            raw = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (f"opmap-ext:{external_id}",)
            ).fetchone()
            if not raw:
                return False
            row = conn.execute(
                "SELECT 1 FROM operations WHERE transaction_id = ? AND op_kind = 'UNDO' LIMIT 1",
                (int(raw["value"]),),
            ).fetchone()
            return bool(row)
        finally:
            conn.close()

    # -- undo bookkeeping via meta --------------------------------------
    def mark_undone(self, external_id: str) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                (f"undone:{external_id}", _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def is_undone(self, external_id: str) -> bool:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM meta WHERE key = ?", (f"undone:{external_id}",)
            ).fetchone()
            return bool(row)
        finally:
            conn.close()

    # ---------------------------------------------------------------------
    def _ext(self, conn: sqlite3.Connection, txn_id: int) -> dict:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (f"opmap:{txn_id}",)).fetchone()
        return {"operation_id": row["value"] if row else f"txn-{txn_id}"}


def summary_json(moved: int, verified: int, failed: int) -> str:
    return json.dumps({"moved": moved, "verified": verified, "failed": failed})
