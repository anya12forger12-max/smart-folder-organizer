"""Local schema: meta, transactions, operations, arrangement memory.

Schema versioning is fail-safe: a database written by a NEWER SFO version is
rejected instead of being silently "upgraded" backwards. SQLite transactions
give the journal atomic bookkeeping — but they do NOT make filesystem moves
atomic; filesystem state and journal state are reconciled explicitly by the
recovery module.
"""

from __future__ import annotations

import sqlite3

from sfo.errors import SchemaMismatchError

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    kind              TEXT NOT NULL,
    root              TEXT NOT NULL,
    plan_fingerprint  TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id     INTEGER NOT NULL REFERENCES transactions(id),
    seq                INTEGER NOT NULL,
    op_kind            TEXT NOT NULL,
    source             TEXT NOT NULL,
    destination        TEXT NOT NULL,
    expected_identity  TEXT,
    result_identity    TEXT,
    status             TEXT NOT NULL,
    error              TEXT,
    updated_at         TEXT NOT NULL,
    UNIQUE(transaction_id, seq)
);

CREATE TABLE IF NOT EXISTS arrangement_memory (
    key         TEXT PRIMARY KEY,
    path        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


def initialize(conn: sqlite3.Connection) -> int:
    """Create tables if needed; enforce forward-only schema versions."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise SchemaMismatchError(
            f"database schema v{current} was written by a newer SFO "
            f"(this build supports v{SCHEMA_VERSION}); refusing to modify it"
        )
    conn.executescript(_DDL)
    if current < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    return SCHEMA_VERSION


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return int(row["value"]) if row else 0
