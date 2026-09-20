"""Symlink policy.

SFO treats symlinks conservatively:

* a symlink is recorded as a symlink, never as the object it points to;
* symlinked directories are NEVER traversed during scanning, even when the
  target is inside the root — recursion follows real directories only;
* symlinks whose target resolves outside the selected root are flagged
  SYMLINK_OUTSIDE_ROOT and are never candidates for movement.
"""

from __future__ import annotations

from enum import Enum


class SymlinkPolicy(str, Enum):
    SKIP_ALWAYS = "SKIP_ALWAYS"


DEFAULT_SYMLINK_POLICY = SymlinkPolicy.SKIP_ALWAYS
