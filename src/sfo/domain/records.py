"""FileRecord: the scanner's output unit.

A FileRecord carries everything later phases need to reason about an entry
without touching the filesystem again: identity, paths, timestamps, type,
hidden/symlink/protected/ignored flags and an honest scan status.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sfo.domain.fs_types import FileType
from sfo.domain.identity import FileIdentity


class ScanStatus(str, Enum):
    STABLE = "STABLE"
    CHANGED_DURING_SCAN = "CHANGED_DURING_SCAN"
    INACCESSIBLE = "INACCESSIBLE"
    DISAPPEARED = "DISAPPEARED"
    UNSUPPORTED = "UNSUPPORTED"


class SkipReason(str, Enum):
    NONE = "NONE"
    SPECIAL_FILE = "SPECIAL_FILE"
    SYMLINK_NOT_FOLLOWED = "SYMLINK_NOT_FOLLOWED"
    SYMLINK_OUTSIDE_ROOT = "SYMLINK_OUTSIDE_ROOT"
    INACCESSIBLE = "INACCESSIBLE"
    DISAPPEARED = "DISAPPEARED"
    IGNORED_DIRECTORY = "IGNORED_DIRECTORY"
    CHANGED_DURING_SCAN = "CHANGED_DURING_SCAN"
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"


@dataclass(frozen=True, slots=True)
class FileRecord:
    absolute_path: Path
    relative_path: Path
    name: str
    extension: str  # lowercase including dot, "" when none
    size: int
    modified_at: float | None
    created_at: float | None
    accessed_at: float | None
    file_type: FileType
    hidden: bool
    symlink_target: str | None
    mode: int | None
    identity: FileIdentity | None
    protected: bool = False
    ignored: bool = False
    scan_status: ScanStatus = ScanStatus.STABLE
    skip_reason: SkipReason | None = None

    @property
    def is_symlink(self) -> bool:
        return self.file_type is FileType.SYMLINK

    @property
    def is_regular_file(self) -> bool:
        return self.file_type is FileType.REGULAR_FILE

    @property
    def is_directory(self) -> bool:
        return self.file_type is FileType.DIRECTORY

    @property
    def is_scannable(self) -> bool:
        return (
            self.file_type is FileType.REGULAR_FILE
            and self.scan_status is ScanStatus.STABLE
            and not self.ignored
        )
