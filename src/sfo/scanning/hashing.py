"""Local streaming hashes.

Hashing is strictly read-only and bounded in memory: files are processed in
fixed-size chunks, so a multi-gigabyte file never loads into RAM. Hashes are
used only for identity/duplicate detection — never as permission to modify
a file — and never leave the machine.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 128 * 1024


def sha256_file(path: Path, algorithm: str = "sha256") -> str:
    if algorithm != "sha256":
        raise ValueError(f"unsupported hash algorithm: {algorithm}")
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
