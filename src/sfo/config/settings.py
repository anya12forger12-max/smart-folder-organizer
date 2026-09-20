"""User settings (JSON) plus protected/ignored path management.

Settings are strictly DATA. There is deliberately no setting that can enable
deletion, overwriting or content modification — those are not features.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sfo.config.paths import AppPaths
from sfo.domain.rules import PathRule, RuleSet
from sfo.errors import ConfigError

_SETTINGS_VERSION = 1


@dataclass(slots=True)
class UserConfig:
    default_root: Path | None = None
    protected: list[PathRule] = field(default_factory=list)
    ignored: list[PathRule] = field(default_factory=list)

    @classmethod
    def load(cls, paths: AppPaths) -> "UserConfig":
        file = paths.settings_path
        if not file.exists():
            return cls()
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
            cfg = cls(
                default_root=Path(raw["default_root"]) if raw.get("default_root") else None,
                protected=[PathRule(Path(p["path"]), p.get("reason")) for p in raw.get("protected", [])],
                ignored=[PathRule(Path(p["path"]), p.get("reason")) for p in raw.get("ignored", [])],
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ConfigError(f"invalid settings file {file}: {exc}") from exc
        return cfg

    def save(self, paths: AppPaths) -> None:
        paths.ensure()
        payload = {
            "version": _SETTINGS_VERSION,
            "default_root": str(self.default_root) if self.default_root else None,
            "protected": [{"path": str(r.path), "reason": r.reason} for r in self.protected],
            "ignored": [{"path": str(r.path), "reason": r.reason} for r in self.ignored],
        }
        paths.settings_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def ruleset(self) -> RuleSet:
        return RuleSet(protected=tuple(self.protected), ignored=tuple(self.ignored))

    def add_protected(self, path: Path, reason: str | None = None) -> bool:
        return self._add(self.protected, self.ignored, path, reason)

    def add_ignored(self, path: Path, reason: str | None = None) -> bool:
        return self._add(self.ignored, self.protected, path, reason)

    @staticmethod
    def _add(target: list[PathRule], other: list[PathRule], path: Path, reason: str | None) -> bool:
        key = str(path)
        if any(str(r.path) == key for r in target):
            return False
        target.append(PathRule(path, reason))
        other[:] = [r for r in other if str(r.path) != key]
        return True
