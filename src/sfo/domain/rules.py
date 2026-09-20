"""Protected / ignored path rules.

Protected means: ANALYZE yes, MOVE never.
Ignored means:   ANALYZE no,  MOVE never.

Matching uses resolved paths (never naive string prefixes) so that ``..``,
relative rules and symlinks cannot smuggle a path out of its intended scope.
Protected wins over ignored when both match.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class PathRule:
    """A protected or ignored path. Relative paths resolve against the root."""

    path: Path
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RuleSet:
    protected: tuple[PathRule, ...] = ()
    ignored: tuple[PathRule, ...] = ()

    EMPTY: ClassVar["RuleSet"]

    @staticmethod
    def _resolved(rule_path: Path, root: Path) -> Path:
        if rule_path.is_absolute():
            candidate = rule_path
        else:
            candidate = root / rule_path
        # resolve() collapses '..' and follows symlinks where they exist.
        return candidate.resolve(strict=False)

    def _matches(self, rules: tuple[PathRule, ...], root: Path, path: Path) -> bool:
        target = path.resolve(strict=False)
        for rule in rules:
            base = self._resolved(rule.path, root)
            if target == base or base in target.parents:
                return True
        return False

    def is_protected(self, root: Path, path: Path) -> bool:
        return self._matches(self.protected, root, path)

    def is_ignored(self, root: Path, path: Path) -> bool:
        if self.is_protected(root, path):
            return False
        return self._matches(self.ignored, root, path)


RuleSet.EMPTY = RuleSet()
