"""Safe name construction for new directories.

Filenames come from the filesystem and user rules; both are data, never
code. Slugification keeps names readable while removing characters that
make paths awkward or dangerous (separators, control chars, traversal).
"""

from __future__ import annotations

import re
import unicodedata

_MAX_NAME = 64
_UNSAFE = re.compile(r"[^\w\s.-]", re.UNICODE)
_SPACES = re.compile(r"[\s_]+")


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKC", name)
    text = _UNSAFE.sub("", text)
    text = _SPACES.sub("-", text.strip())
    text = text.strip(".-")
    if not text:
        text = "unnamed"
    return text[:_MAX_NAME].rstrip(".-") or "unnamed"


def unique_destination(directory, name: str, taken: set[str]):
    """Return a path in *directory* that does not collide.

    Collisions get a numeric suffix (`report.pdf` -> `report-2.pdf`). The
    executor never overwrites; this is purely for planning clarity so two
    same-named files from different folders both get a home.
    """
    candidate = directory / name
    if str(candidate) not in taken:
        return candidate
    stem, dot, suffix = name.rpartition(".")
    base = stem if dot else name
    ext = f".{suffix}" if dot else ""
    counter = 2
    while True:
        candidate = directory / f"{base}-{counter}{ext}"
        if str(candidate) not in taken:
            return candidate
        counter += 1
