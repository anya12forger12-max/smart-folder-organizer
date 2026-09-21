"""Permission hygiene for SFO-owned directories.

SFO stores its own state under the user's home. Those directories must be
private (mode 0700, owned by the current user) because journals contain file
paths. This module validates that; it never changes permissions of USER files
— only of SFO's own storage directories, right after creating them.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from sfo.errors import UnsafePermissionsError


def validate_private_directory(path: Path) -> None:
    try:
        st = path.stat()
    except OSError as exc:
        raise UnsafePermissionsError(f"cannot stat {path}: {exc}") from exc
    if not stat.S_ISDIR(st.st_mode):
        raise UnsafePermissionsError(f"not a directory: {path}")
    if st.st_uid != os.geteuid():
        raise UnsafePermissionsError(f"{path} is owned by uid {st.st_uid}, not by the current user")
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise UnsafePermissionsError(
            f"{path} is accessible by group/others; expected private (0700)"
        )


def ensure_private_dir(path: Path) -> None:
    """Create path as a private directory owned by the current user."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    validate_private_directory(path)
