"""First-run storage initialization.

Creates only SFO's own directories and database — never touches any user
folder, and never scans or organizes anything.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sfo.config.paths import AppPaths
from sfo.persistence.database import Database
from sfo.persistence.schema import initialize
from sfo.security.permissions import validate_private_directory


@dataclass(frozen=True, slots=True)
class InitializationReport:
    ensured_dirs: tuple[Path, ...]
    database_path: Path
    schema_version: int


def initialize_storage(paths: AppPaths) -> InitializationReport:
    paths.ensure()
    ensured = (paths.config_dir, paths.data_dir, paths.cache_dir, paths.journal_dir, paths.lock_dir)
    db_path = paths.database_path
    fresh = not db_path.exists()
    conn = Database(db_path).connect()
    try:
        version = initialize(conn)
    finally:
        conn.close()
    if fresh:
        os.chmod(db_path, 0o600)
    for directory in (paths.config_dir, paths.data_dir):
        validate_private_directory(directory)
    return InitializationReport(ensured_dirs=ensured, database_path=db_path, schema_version=version)
