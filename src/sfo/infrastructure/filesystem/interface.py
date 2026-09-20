"""The filesystem abstraction is SFO's mutation boundary.

Only the operations listed in ALLOWED_OPERATIONS exist. Deletion, overwrite,
truncation, arbitrary writes, chmod/chown and execution are deliberately
absent from this interface — no component can call what does not exist.

``move`` and ``create_directory`` are the only mutating operations; they are
used exclusively by sfo.execution after plan validation and confirmation.
Read-side components (scanner, analysis, planning) never invoke them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from sfo.domain.fs_types import FileType
from sfo.errors import SfoError


class FileSystemError(SfoError):
    """A filesystem operation failed in a way the user should hear about."""


ALLOWED_OPERATIONS = frozenset(
    {
        "inspect",
        "list_directory",
        "exists",
        "create_directory",
        "move",
        "hash_file",
    }
)


@dataclass(frozen=True, slots=True)
class PathInfo:
    """Everything inspect() knows about one entry, obtained without following
    symlinks (lstat semantics)."""

    path: Path
    exists: bool
    file_type: FileType
    size: int | None = None
    mode: int | None = None
    device: int | None = None
    inode: int | None = None
    modified_at: float | None = None
    created_at: float | None = None
    accessed_at: float | None = None
    symlink_target: str | None = None

    @classmethod
    def missing(cls, path: Path) -> "PathInfo":
        return cls(path=path, exists=False, file_type=FileType.MISSING)


class FileSystem(ABC):
    """Minimal safe filesystem surface. See module docstring for the policy."""

    @abstractmethod
    def exists(self, path: Path) -> bool: ...

    @abstractmethod
    def inspect(self, path: Path) -> PathInfo: ...

    @abstractmethod
    def list_directory(self, path: Path) -> list[Path]: ...

    @abstractmethod
    def create_directory(self, path: Path) -> None:
        """Create path and missing parents. Idempotent. Directories only."""

    @abstractmethod
    def move(self, source: Path, destination: Path) -> None:
        """Move source to destination.

        Contract: refuses to overwrite. If destination exists (or is a
        dangling symlink) raises DestinationExistsError and changes nothing.
        Same-filesystem only; cross-device moves raise rather than falling
        back to copy+delete, because deletion is prohibited.
        """

    @abstractmethod
    def hash_file(self, path: Path, algorithm: str = "sha256") -> str:
        """Stream-hash a regular file in bounded chunks. Read-only."""


def assert_no_forbidden_operations(cls_or_module: object) -> None:
    """Guard used by tests: fail if forbidden names appear on a class/module."""
    forbidden = (
        "delete",
        "unlink",
        "remove",
        "rmdir",
        "rmtree",
        "write",
        "write_text",
        "write_bytes",
        "truncate",
        "overwrite",
        "chmod",
        "chown",
        "execute",
        "rename",
        "copy",
        "replace",
        "open",
    )
    present = [name for name in forbidden if hasattr(cls_or_module, name)]
    if present:
        raise AssertionError(f"forbidden filesystem operations exposed: {present}")
