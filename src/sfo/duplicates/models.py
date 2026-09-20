"""Data model for duplicate reports. Pure data; no filesystem access."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DupFile:
    """One regular file as seen by the duplicate scanner."""

    path: Path
    size: int
    modified_at: float
    device: int
    inode: int
    sha256: str | None = None
    protected: bool = False
    ignored: bool = False
    project: str | None = None


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """Files that share exact content (or the same underlying inode).

    kind:
      CONFIRMED  identical content hashes, independent files
      EMPTY      zero-byte files (trivially identical)
      HARDLINKS  distinct names, one underlying object - NOT redundant copies
    """

    group_id: str
    kind: str
    files: tuple[DupFile, ...]
    sha256: str | None = None

    @property
    def size(self) -> int:
        return self.files[0].size if self.files else 0

    @property
    def redundant_bytes(self) -> int:
        """Bytes that would be recoverable if the user removed extra copies.

        Hard-linked groups are one physical object, so nothing is redundant.
        """
        if self.kind == "HARDLINKS" or len(self.files) < 2:
            return 0
        return self.size * (len(self.files) - 1)


@dataclass(frozen=True, slots=True)
class DuplicateReport:
    root: Path
    scanned_files: int
    skipped_symlinks: int
    skipped_special: int
    skipped_vcs: int
    unreadable: int
    stale: int
    incomplete: bool
    groups: tuple[DuplicateGroup, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = ()

    @property
    def confirmed_groups(self) -> tuple[DuplicateGroup, ...]:
        return tuple(g for g in self.groups if g.kind in ("CONFIRMED", "EMPTY"))

    @property
    def potentially_reclaimable(self) -> int:
        return sum(g.redundant_bytes for g in self.groups)

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "scanned_files": self.scanned_files,
            "skipped_symlinks": self.skipped_symlinks,
            "skipped_special": self.skipped_special,
            "skipped_vcs": self.skipped_vcs,
            "unreadable": self.unreadable,
            "stale": self.stale,
            "incomplete": self.incomplete,
            "potentially_reclaimable_bytes": self.potentially_reclaimable,
            "groups": [
                {
                    "group_id": g.group_id,
                    "kind": g.kind,
                    "size": g.size,
                    "redundant_bytes": g.redundant_bytes,
                    "sha256": g.sha256,
                    "files": [
                        {
                            "path": str(f.path),
                            "size": f.size,
                            "sha256": f.sha256,
                            "protected": f.protected,
                            "ignored": f.ignored,
                            "project": f.project,
                        }
                        for f in g.files
                    ],
                }
                for g in self.groups
            ],
            "warnings": list(self.warnings),
        }
