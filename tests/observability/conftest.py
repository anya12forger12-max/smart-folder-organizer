"""Shared isolation for observability tests: XDG-separated fake home."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture()
def iso_env(tmp_path: Path, monkeypatch) -> SimpleNamespace:
    home = tmp_path / "home"
    config = tmp_path / "xdg-config"
    state = tmp_path / "xdg-state"
    cache = tmp_path / "xdg-cache"
    for directory in (home, config, state, cache):
        directory.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))

    root = tmp_path / "Downloads"
    root.mkdir()
    return SimpleNamespace(root=root, config=config, state=state)
