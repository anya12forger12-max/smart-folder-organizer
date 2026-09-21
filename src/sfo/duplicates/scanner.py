"""Staged, read-only duplicate detection.

Pipeline (cheapest test first; full hash only where it can confirm a group):

1. walk the root without following symlinks
2. drop non-regular files (counted) and VCS/dependency trees (.git, ...)
3. hard-link pre-grouping by (device, inode): same object, not duplicates
4. size grouping: different sizes can never be exact duplicates
5. full streaming sha256 of remaining candidates (bounded memory)
6. re-inspect after hashing; changed files are excluded as STALE

The final decision always uses the complete content hash. No sampling
shortcuts exist because the FileSystem interface deliberately exposes no
way to open files partially - and correctness beats speed here.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from sfo.domain.fs_types import FileType
from sfo.domain.rules import RuleSet
from sfo.duplicates.models import DupFile, DuplicateGroup, DuplicateReport
from sfo.infrastructure.filesystem import FileSystem

# Directories whose contents are machinery, not user files. Never treated as
# duplicate candidates and never modified anywhere in SFO.
VCS_DIRS = frozenset({".git", "__pycache__", "node_modules", ".venv", "venv"})

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class DuplicateScanner:
    def __init__(self, fs: FileSystem, rules: RuleSet | None = None) -> None:
        self._fs = fs
        self._rules = rules or RuleSet.EMPTY

    # ------------------------------------------------------------------
    def scan(self, root: Path, project_of=None, cancelled=None) -> DuplicateReport:
        """Analyze root without changing anything.

        ``project_of(path)`` may supply a project name for context; it must
        be a pure read-only function.
        """
        started = time.monotonic()
        root = Path(root)
        skipped_symlinks = skipped_special = skipped_vcs = 0
        problems: list[str] = []
        files: list[DupFile] = []

        for entry, info in self._walk(root, problems, cancelled):
            if info.file_type is FileType.DIRECTORY:
                # VCS/dependency trees are machinery, not user folders.
                if _in_vcs(entry.relative_to(root)):
                    skipped_vcs += 1
                continue
            if info.file_type is FileType.SYMLINK:
                skipped_symlinks += 1
                continue
            if info.file_type is not FileType.REGULAR_FILE:
                skipped_special += 1
                continue
            if _in_vcs(entry.relative_to(root)):
                # e.g. a ".git" git-worktree pointer file
                skipped_vcs += 1
                continue
            files.append(
                DupFile(
                    path=entry,
                    size=info.size or 0,
                    modified_at=info.modified_at or 0.0,
                    device=info.device or 0,
                    inode=info.inode or 0,
                    protected=self._rules.is_protected(root, entry),
                    ignored=self._rules.is_ignored(root, entry),
                    project=project_of(entry) if project_of else None,
                )
            )

        groups, hash_warnings = self._group(files)
        warnings = problems + hash_warnings
        elapsed = f"scan completed in {time.monotonic() - started:.2f}s"

        return DuplicateReport(
            root=root,
            scanned_files=len(files),
            skipped_symlinks=skipped_symlinks,
            skipped_special=skipped_special,
            skipped_vcs=skipped_vcs,
            unreadable=sum(1 for w in problems if "cannot" in w),
            stale=len(hash_warnings),
            incomplete=bool(warnings),
            groups=tuple(groups),
            warnings=tuple(warnings + [elapsed]),
        )

    # ------------------------------------------------------------------
    def _walk(self, root: Path, problems: list[str], cancelled=None):
        """Yield (path, PathInfo) for every entry below root in sorted order
        so results are deterministic. Unreadable directories produce a
        problem note instead of failing the whole scan."""
        stack = [root]
        while stack:
            if cancelled is not None and cancelled():
                break
            current = stack.pop()
            try:
                entries = sorted(self._fs.list_directory(current))
            except OSError as exc:
                problems.append(f"cannot read directory {current.name}: {exc.strerror or exc}")
                continue
            for entry in entries:
                try:
                    info = self._fs.inspect(entry)
                except OSError as exc:
                    problems.append(f"cannot inspect {entry.name}: {exc.strerror or exc}")
                    continue
                yield entry, info
                if info.file_type is FileType.DIRECTORY and entry.name not in VCS_DIRS:
                    stack.append(entry)

    # ------------------------------------------------------------------
    def _group(self, files: list[DupFile]) -> tuple[list[DuplicateGroup], list[str]]:
        warnings: list[str] = []
        groups: list[DuplicateGroup] = []

        # Hard links first: identical (device, inode) means ONE object with
        # several names. Reporting that as redundant copies would be wrong.
        identity_groups: dict[tuple[int, int], list[DupFile]] = {}
        for f in files:
            identity_groups.setdefault((f.device, f.inode), []).append(f)
        candidates: list[DupFile] = []
        for members in identity_groups.values():
            if len(members) > 1:
                groups.append(
                    DuplicateGroup(
                        group_id="",
                        kind="HARDLINKS",
                        files=tuple(sorted(members, key=lambda f: str(f.path))),
                    )
                )
            else:
                candidates.extend(members)

        # Empty files are trivially content-identical; no hashing needed.
        empties = [f for f in candidates if f.size == 0]
        candidates = [f for f in candidates if f.size > 0]
        if len(empties) > 1:
            groups.append(
                DuplicateGroup(
                    group_id="",
                    kind="EMPTY",
                    files=tuple(sorted(empties, key=lambda f: str(f.path))),
                    sha256=_EMPTY_SHA256,
                )
            )

        # Size grouping: exact duplicates must have equal sizes, so unique
        # sizes are never hashed at all.
        by_size: dict[int, list[DupFile]] = {}
        for f in candidates:
            by_size.setdefault(f.size, []).append(f)

        for size in sorted(by_size):
            bucket = by_size[size]
            if len(bucket) < 2:
                continue
            hashed: dict[str, list[DupFile]] = {}
            for f in sorted(bucket, key=lambda x: str(x.path)):
                digest = self._hash_stale_safe(f)
                if digest is None:
                    warnings.append(
                        f"file changed or became unreadable while being "
                        f"analyzed; excluded from this report: {f.path.name}"
                    )
                    continue
                hashed.setdefault(digest, []).append(f)
            for digest in sorted(hashed):
                members = hashed[digest]
                if len(members) > 1:
                    groups.append(
                        DuplicateGroup(
                            group_id="",
                            kind="CONFIRMED",
                            files=tuple(members),
                            sha256=digest,
                        )
                    )

        # Deterministic presentation: biggest recoverable savings first;
        # ties broken by path so identical inputs give identical group IDs.
        groups.sort(key=lambda g: (-g.redundant_bytes, g.kind, str(g.files[0].path)))
        return [
            DuplicateGroup(
                group_id=f"DUP-{index:04d}",
                kind=g.kind,
                files=g.files,
                sha256=g.sha256,
            )
            for index, g in enumerate(groups, start=1)
        ], warnings

    # ------------------------------------------------------------------
    def _hash_stale_safe(self, f: DupFile) -> str | None:
        """Hash a file, refusing results that could describe mixed state.

        If the file changes between the pre-hash and post-hash inspection,
        the digest might span two versions of the content; SFO excludes the
        file instead of risking a false confirmation.
        """
        before = self._safe_inspect(f.path)
        if before is None or (before.device, before.inode) != (f.device, f.inode):
            return None
        try:
            digest = self._fs.hash_file(f.path)
        except OSError:
            return None
        after = self._safe_inspect(f.path)
        same_state = (
            after is not None
            and after.inode == before.inode
            and after.device == before.device
            and after.size == before.size == (f.size or 0)
            and after.modified_at == before.modified_at
        )
        return digest if same_state else None

    def _safe_inspect(self, path: Path):
        try:
            info = self._fs.inspect(path)
        except OSError:
            return None
        if not info.exists or info.file_type is not FileType.REGULAR_FILE:
            return None
        return info


def _in_vcs(relative: Path) -> bool:
    return any(part in VCS_DIRS for part in relative.parts)
