"""The Scanner: recursive, read-only discovery inside one selected root.

Hard guarantees (security-sensitive):

* ZERO mutation capability: the scanner only calls read operations of the
  FileSystem abstraction (inspect / list_directory / exists / hash_file).
  It has no reference to create_directory or move at all.
* It never follows symlinks — not even into directories inside the root.
* Ignored directories are recorded as single entries; their contents never
  enter analysis.
* Protected entries are analyzed but flagged protected=True.
* One unreadable entry becomes an error record; the scan continues.
* Files that change mid-scan are flagged CHANGED_DURING_SCAN via a
  double-stat check around hashing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sfo.domain.fs_types import FileType
from sfo.domain.records import FileRecord, ScanStatus, SkipReason
from sfo.domain.rules import RuleSet
from sfo.errors import ScanCancelled
from sfo.infrastructure.filesystem.interface import FileSystem
from sfo.scanning.result import ScanCounters, ScanError, ScanResult, compute_snapshot
from sfo.security.containment import is_within


class Scanner:
    def __init__(
        self,
        fs: FileSystem,
        rules: RuleSet = RuleSet.EMPTY,
        *,
        hash_files: bool = True,
        progress: Callable[[int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        self._fs = fs
        self._rules = rules
        self._hash_files = hash_files
        self._progress = progress
        self._cancelled = cancelled

    def scan(self, root: Path) -> ScanResult:
        root = Path(root)
        info = self._fs.inspect(root)
        if not info.exists:
            raise FileNotFoundError(f"selected root does not exist: {root}")
        if info.file_type is not FileType.DIRECTORY:
            raise NotADirectoryError(f"selected root is not a directory: {root}")

        files: list[FileRecord] = []
        directories: list[FileRecord] = []
        symlinks: list[FileRecord] = []
        special: list[FileRecord] = []
        ignored_items: list[FileRecord] = []
        errors: list[ScanError] = []
        stats = ScanCounters()
        seen = 0

        stack: list[Path] = [root]
        while stack:
            if self._cancelled and self._cancelled():
                raise ScanCancelled("scan cancelled by user")
            current = stack.pop()
            try:
                entries = self._fs.list_directory(current)
            except Exception as exc:  # unreadable directory: record, continue
                errors.append(ScanError(current, f"cannot list directory: {exc}"))
                stats.inaccessible += 1
                continue
            for entry in entries:
                seen += 1
                if self._progress:
                    self._progress(seen)
                if not is_within(root, entry):
                    errors.append(
                        ScanError(entry, "entry escaped root during listing; skipped")
                    )
                    continue
                if self._rules.is_ignored(root, entry):
                    ignored_items.append(self._basic_record(root, entry, ignored=True))
                    stats.ignored += 1
                    continue
                protected = self._rules.is_protected(root, entry)
                if protected:
                    stats.protected += 1
                try:
                    info = self._fs.inspect(entry)
                except Exception as exc:
                    errors.append(ScanError(entry, f"cannot inspect: {exc}"))
                    stats.inaccessible += 1
                    continue
                if not info.exists:
                    errors.append(ScanError(entry, "entry disappeared during scan"))
                    continue
                rel = entry.relative_to(root)
                match info.file_type:
                    case FileType.DIRECTORY:
                        directories.append(
                            self._record(root, entry, rel, info, protected=protected)
                        )
                        stats.directories += 1
                        stack.append(entry)
                    case FileType.SYMLINK:
                        symlinks.append(
                            self._symlink_record(root, entry, rel, info, protected)
                        )
                        stats.symlinks += 1
                    case FileType.REGULAR_FILE:
                        record = self._file_record(root, entry, rel, info, protected, errors, stats)
                        files.append(record)
                        stats.files += 1
                    case _:
                        special.append(
                            FileRecord(
                                absolute_path=entry,
                                relative_path=rel,
                                name=entry.name,
                                extension=_extension(entry.name),
                                size=info.size or 0,
                                modified_at=info.modified_at,
                                created_at=info.created_at,
                                accessed_at=info.accessed_at,
                                file_type=info.file_type,
                                hidden=_hidden(entry.name),
                                symlink_target=None,
                                mode=info.mode,
                                identity=None,
                                protected=protected,
                                skip_reason=SkipReason.SPECIAL_FILE,
                                scan_status=ScanStatus.UNSUPPORTED,
                            )
                        )
                        stats.special += 1

        return ScanResult(
            root=root,
            files=tuple(files),
            directories=tuple(directories),
            symlinks=tuple(symlinks),
            special=tuple(special),
            ignored_items=tuple(ignored_items),
            errors=tuple(errors),
            statistics=stats.freeze(),
            snapshot=compute_snapshot(
                root,
                [*files, *directories, *symlinks, *special, *ignored_items],
            ),
        )

    def _basic_record(self, root: Path, path: Path, *, ignored: bool) -> FileRecord:
        info = self._fs.inspect(path)
        return FileRecord(
            absolute_path=path,
            relative_path=path.relative_to(root),
            name=path.name,
            extension=_extension(path.name),
            size=info.size or 0,
            modified_at=info.modified_at,
            created_at=info.created_at,
            accessed_at=info.accessed_at,
            file_type=info.file_type,
            hidden=_hidden(path.name),
            symlink_target=info.symlink_target,
            mode=info.mode,
            identity=None,
            ignored=ignored,
            skip_reason=SkipReason.IGNORED_DIRECTORY if ignored else None,
        )

    def _record(
        self, root: Path, path: Path, rel: Path, info, *, protected: bool
    ) -> FileRecord:
        from sfo.domain.identity import FileIdentity

        identity = None
        if info.device is not None:
            identity = FileIdentity.from_stat(_StatShim(info))
        return FileRecord(
            absolute_path=path,
            relative_path=rel,
            name=path.name,
            extension=_extension(path.name),
            size=info.size or 0,
            modified_at=info.modified_at,
            created_at=info.created_at,
            accessed_at=info.accessed_at,
            file_type=info.file_type,
            hidden=_hidden(path.name),
            symlink_target=None,
            mode=info.mode,
            identity=identity,
            protected=protected,
        )

    def _symlink_record(self, root: Path, path: Path, rel: Path, info, protected: bool) -> FileRecord:
        target = info.symlink_target or ""
        resolved = (path.parent / target).resolve(strict=False)
        outside = not is_within(root, resolved)
        return FileRecord(
            absolute_path=path,
            relative_path=rel,
            name=path.name,
            extension=_extension(path.name),
            size=0,
            modified_at=info.modified_at,
            created_at=info.created_at,
            accessed_at=info.accessed_at,
            file_type=FileType.SYMLINK,
            hidden=_hidden(path.name),
            symlink_target=target,
            mode=info.mode,
            identity=None,
            protected=protected,
            skip_reason=(
                SkipReason.SYMLINK_OUTSIDE_ROOT
                if outside
                else SkipReason.SYMLINK_NOT_FOLLOWED
            ),
        )

    def _file_record(self, root, path, rel, info, protected, errors, stats) -> FileRecord:
        from sfo.domain.identity import FileIdentity

        before = _StatShim(info)
        sha256: str | None = None
        status = ScanStatus.STABLE
        reason: SkipReason | None = None
        if self._hash_files:
            try:
                sha256 = self._fs.hash_file(path)
            except Exception as exc:
                errors.append(ScanError(path, f"hashing failed: {exc}"))
                stats.hash_failures += 1
            after_info = self._fs.inspect(path)
            if not after_info.exists:
                return FileRecord(
                    absolute_path=path,
                    relative_path=rel,
                    name=path.name,
                    extension=_extension(path.name),
                    size=info.size or 0,
                    modified_at=info.modified_at,
                    created_at=info.created_at,
                    accessed_at=info.accessed_at,
                    file_type=FileType.REGULAR_FILE,
                    hidden=_hidden(path.name),
                    symlink_target=None,
                    mode=info.mode,
                    identity=None,
                    protected=protected,
                    scan_status=ScanStatus.DISAPPEARED,
                    skip_reason=SkipReason.DISAPPEARED,
                )
            if not before.matches_stat(_StatShim(after_info)):
                status = ScanStatus.CHANGED_DURING_SCAN
                reason = SkipReason.CHANGED_DURING_SCAN
                info = after_info
        return FileRecord(
            absolute_path=path,
            relative_path=rel,
            name=path.name,
            extension=_extension(path.name),
            size=info.size or 0,
            modified_at=info.modified_at,
            created_at=info.created_at,
            accessed_at=info.accessed_at,
            file_type=FileType.REGULAR_FILE,
            hidden=_hidden(path.name),
            symlink_target=None,
            mode=info.mode,
            identity=FileIdentity.from_stat(_StatShim(info), sha256=sha256),
            protected=protected,
            scan_status=status,
            skip_reason=reason,
        )


class _StatShim:
    """Adapts PathInfo to the st_* attribute surface of FileIdentity."""

    __slots__ = ("st_dev", "st_ino", "st_size", "st_mtime", "st_mode")

    def __init__(self, info) -> None:
        self.st_dev = info.device or 0
        self.st_ino = info.inode or 0
        self.st_size = info.size or 0
        self.st_mtime = info.modified_at or 0.0
        self.st_mode = _mode_for(info.file_type, info.mode)

    def matches_stat(self, other: "_StatShim") -> bool:
        return (
            self.st_dev == other.st_dev
            and self.st_ino == other.st_ino
            and self.st_size == other.st_size
            and self.st_mtime == other.st_mtime
            and self.st_mode == other.st_mode
        )


def _mode_for(file_type: FileType, mode: int | None) -> int:
    import stat as stat_module

    base = {
        FileType.REGULAR_FILE: stat_module.S_IFREG,
        FileType.DIRECTORY: stat_module.S_IFDIR,
        FileType.SYMLINK: stat_module.S_IFLNK,
    }.get(file_type, stat_module.S_IFREG)
    return base | ((mode or 0) & 0o7777)


def _hidden(name: str) -> bool:
    return name.startswith(".")


def _extension(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".tar.gz"):
        return ".tar.gz"
    dot = lowered.rfind(".")
    return lowered[dot:] if dot > 0 else ""
