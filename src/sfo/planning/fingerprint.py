"""Plan fingerprinting: binds a plan to the filesystem state it was built on.

A plan is only valid while the world still looks the way it did when the
plan was made. We capture a lightweight snapshot fingerprint (paths +
size + mtime + inode for every scanned file) and compare it at
confirmation time. Any drift — new files, deletions, size/mtime changes,
swapped files (same path different inode) — invalidates the plan before
a single move happens.
"""

from __future__ import annotations

import hashlib

from sfo.domain.records import FileRecord


def snapshot_fingerprint(records: list[FileRecord]) -> str:
    """Deterministic digest over the scanned file inventory.

    Sorted by rel_path so identical states always produce identical
    digests regardless of directory iteration order.
    """
    lines = []
    for record in sorted(records, key=lambda r: r.relative_path):
        stat = record.identity.stat_after or record.identity.stat_before
        size = getattr(stat, "st_size", 0) if stat else 0
        mtime = getattr(stat, "st_mtime_ns", 0) if stat else 0
        inode = getattr(stat, "st_ino", 0) if stat else 0
        lines.append(
            f"{record.relative_path}\x1f{record.file_type.value}\x1f{size}\x1f{mtime}\x1f{inode}"
        )
    payload = "\x1e".join(lines).encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(payload).hexdigest()


def plans_match(current: str, recorded: str) -> bool:
    return bool(current) and bool(recorded) and current == recorded
