"""Path containment: every path SFO touches must live inside one root.

Containment is decided on *resolved* paths, never string prefixes, so that
``..`` segments, relative paths and symlinks cannot smuggle a path outside
the selected root. Known limitation (documented in SECURITY.md): between
resolution and use there is a theoretical TOCTOU window if another process
re-points a symlink; the executor re-validates immediately before each move.
"""

from __future__ import annotations

from pathlib import Path

from sfo.errors import PathOutsideRootError


def is_within(root: Path, candidate: Path) -> bool:
    resolved_root = Path(root).resolve(strict=False)
    resolved = Path(candidate).resolve(strict=False)
    return resolved == resolved_root or resolved_root in resolved.parents


def resolve_within(root: Path, candidate: Path) -> Path:
    """Return the resolved path, raising if it escapes the root."""
    resolved_root = Path(root).resolve(strict=False)
    resolved = Path(candidate).resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise PathOutsideRootError(
            f"path {candidate} resolves outside selected root {root}"
        )
    return resolved
