"""ScanResult and statistics.

The scan snapshot fingerprint is a deterministic digest of every discovered
entry's identity. It lets the CLI detect stale previews cheaply and feeds the
plan fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sfo.domain.records import FileRecord


@dataclass(frozen=True, slots=True)
class ScanError:
    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class ScanStatistics:
    files: int = 0
    directories: int = 0
    symlinks: int = 0
    special: int = 0
    ignored: int = 0
    protected: int = 0
    inaccessible: int = 0
    hash_failures: int = 0

    @property
    def total_entries(self) -> int:
        return self.files + self.directories + self.symlinks + self.special + self.ignored


@dataclass(slots=True)
class ScanCounters:
    """Mutable accumulation buffer for the scanner; frozen into ScanStatistics."""

    files: int = 0
    directories: int = 0
    symlinks: int = 0
    special: int = 0
    ignored: int = 0
    protected: int = 0
    inaccessible: int = 0
    hash_failures: int = 0

    def freeze(self) -> ScanStatistics:
        return ScanStatistics(
            files=self.files,
            directories=self.directories,
            symlinks=self.symlinks,
            special=self.special,
            ignored=self.ignored,
            protected=self.protected,
            inaccessible=self.inaccessible,
            hash_failures=self.hash_failures,
        )


@dataclass(frozen=True, slots=True)
class ScanResult:
    root: Path
    files: tuple[FileRecord, ...] = ()
    directories: tuple[FileRecord, ...] = ()
    symlinks: tuple[FileRecord, ...] = ()
    special: tuple[FileRecord, ...] = ()
    ignored_items: tuple[FileRecord, ...] = ()
    errors: tuple[ScanError, ...] = ()
    scan_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    statistics: ScanStatistics = ScanStatistics()
    snapshot: str = ""

    def record_by_path(self, path: Path) -> FileRecord | None:
        target = Path(path).resolve(strict=False)
        for record in self.iter_all():
            if record.absolute_path == target:
                return record
        return None

    def iter_all(self):
        yield from self.files
        yield from self.directories
        yield from self.symlinks
        yield from self.special
        yield from self.ignored_items

    def regular_files(self) -> tuple[FileRecord, ...]:
        """Regular files eligible for analysis (ignored contents excluded)."""
        return tuple(r for r in self.files if r.is_scannable)


def compute_snapshot(root: Path, records) -> str:
    lines = [f"root={Path(root).resolve(strict=False)}"]
    for record in sorted(records, key=lambda r: r.relative_path.as_posix()):
        ident = record.identity
        lines.append(
            "|".join(
                [
                    record.relative_path.as_posix(),
                    record.file_type.value,
                    str(ident.device if ident else -1),
                    str(ident.inode if ident else -1),
                    str(record.size),
                    f"{record.modified_at:.6f}" if record.modified_at is not None else "-",
                    ident.sha256 or "-" if ident else "-",
                ]
            )
        )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def snapshot_payload(scan: ScanResult) -> str:
    return json.dumps({"root": str(scan.root), "snapshot": scan.snapshot}, sort_keys=True)
