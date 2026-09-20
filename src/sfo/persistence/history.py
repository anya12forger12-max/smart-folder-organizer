"""Read-side history queries for the CLI.

History contains only what audit/undo/debugging need: paths, identities,
statuses and timestamps. No file contents, no secrets. It never leaves the
machine.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TransactionSummary:
    id: int
    kind: str
    root: str
    status: str
    created_at: str
    moves: int
    completed: int
    failed: int


@dataclass(frozen=True, slots=True)
class OperationRow:
    seq: int
    op_kind: str
    source: str
    destination: str
    status: str
    error: str | None


@dataclass(frozen=True, slots=True)
class TransactionDetail:
    id: int
    kind: str
    root: str
    status: str
    created_at: str
    plan_fingerprint: str
    operations: tuple[OperationRow, ...]


class HistoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def summaries(self, limit: int = 10) -> list[TransactionSummary]:
        rows = self.conn.execute(
            """
            SELECT t.id, t.kind, t.root, t.status, t.created_at,
                   COUNT(*) AS moves,
                   SUM(o.status IN ('VERIFIED','COMPLETED')) AS completed,
                   SUM(o.status = 'FAILED') AS failed
            FROM transactions t LEFT JOIN operations o ON o.transaction_id = t.id
            GROUP BY t.id ORDER BY t.id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            TransactionSummary(
                id=r["id"],
                kind=r["kind"],
                root=r["root"],
                status=r["status"],
                created_at=r["created_at"],
                moves=r["moves"] or 0,
                completed=r["completed"] or 0,
                failed=r["failed"] or 0,
            )
            for r in rows
        ]

    def detail(self, transaction_id: int) -> TransactionDetail | None:
        tx = self.conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if tx is None:
            return None
        ops = self.conn.execute(
            "SELECT seq, op_kind, source, destination, status, error "
            "FROM operations WHERE transaction_id = ? ORDER BY seq",
            (transaction_id,),
        ).fetchall()
        return TransactionDetail(
            id=tx["id"],
            kind=tx["kind"],
            root=tx["root"],
            status=tx["status"],
            created_at=tx["created_at"],
            plan_fingerprint=tx["plan_fingerprint"],
            operations=tuple(
                OperationRow(
                    seq=o["seq"],
                    op_kind=o["op_kind"],
                    source=o["source"],
                    destination=o["destination"],
                    status=o["status"],
                    error=o["error"],
                )
                for o in ops
            ),
        )

    def latest_undoable(self) -> TransactionSummary | None:
        for summary in self.summaries(limit=50):
            if summary.kind == "organize" and summary.status in {"COMPLETED", "PARTIAL"}:
                return summary
        return None
