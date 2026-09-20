"""Staged duplicate detection: size groups -> content hash candidates only.

Exact duplicates are found by grouping records by size first; hashing runs
only within same-size candidate groups. The final decision always uses the
full SHA-256 of both files - partial hashes never decide equality.
"""

from __future__ import annotations

from collections import defaultdict

from sfo.domain.analysis import DuplicateGroup
from sfo.infrastructure.filesystem import FileSystem
from sfo.scanning.hashing import sha256_file


def find_duplicate_groups(records, fs: FileSystem) -> list[DuplicateGroup]:  # noqa: ANN001 - FileRecord list
    by_size: dict[int, list] = defaultdict(list)
    for record in records:
        if record.identity is None or record.size <= 0:
            continue
        by_size[record.size].append(record)

    groups: list[DuplicateGroup] = []
    for size in sorted(by_size):
        candidates = by_size[size]
        if len(candidates) < 2:
            continue
        hashes: dict[str, list] = defaultdict(list)
        for record in sorted(candidates, key=lambda r: r.relative_path.as_posix()):
            try:
                digest = sha256_file(record.absolute_path)
            except OSError:
                continue  # unreadable during analysis: skip silently, planner keeps it
            hashes[digest].append(record.absolute_path)
        for digest in sorted(hashes):
            members = hashes[digest]
            if len(members) >= 2:
                groups.append(
                    DuplicateGroup(sha256=digest, size=size, members=tuple(sorted(members)))
                )
    return groups
