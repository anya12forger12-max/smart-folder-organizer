"""Standard XDG-style locations for SFO's own data.

    config:  ~/.config/sfo        settings.json, rules.toml
    state:   ~/.local/share/sfo   history database, journals, locks
    cache:   ~/.cache/sfo         bounded scan/hash caches

SFO never writes outside these directories plus the single user-selected
organization root. All are user-local; no root required. Environment
overrides (XDG_*) are honoured but are never security boundaries.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "sfo"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "sfo"


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "sfo"


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Concrete locations for one installation."""

    config_dir: Path
    data_dir: Path
    cache_dir: Path

    @classmethod
    def default(cls) -> "AppPaths":
        return cls(config_dir=config_dir(), data_dir=state_dir(), cache_dir=cache_dir())

    # -- files ----------------------------------------------------------
    @property
    def settings_path(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def rules_path(self) -> Path:
        return self.config_dir / "rules.toml"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "history.db"

    @property
    def journal_dir(self) -> Path:
        return self.data_dir / "journal"

    @property
    def lock_dir(self) -> Path:
        return self.data_dir / "locks"

    @property
    def undone_path(self) -> Path:
        return self.data_dir / "undone.json"

    # -- lifecycle --------------------------------------------------------
    def ensure(self) -> "AppPaths":
        from sfo.security.permissions import ensure_private_dir

        # SFO-owned storage is always private (0700): journals and history
        # contain file paths, which must not leak to other local users.
        for directory in (self.config_dir, self.data_dir, self.cache_dir):
            ensure_private_dir(directory)
        for directory in (self.journal_dir, self.lock_dir):
            ensure_private_dir(directory)
        return self
