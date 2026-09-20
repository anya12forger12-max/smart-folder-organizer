"""Configuration facade: settings (JSON) + rules (TOML), both validated.

Thin, single entry point for the rest of the app. Parsing/validation live in
sfo.config.settings and sfo.rules.parser; this module only wires them to the
standard AppPaths and guarantees that a broken file yields a clear error,
never partial adoption.
"""

from __future__ import annotations

from pathlib import Path

from sfo.config.paths import AppPaths
from sfo.config.settings import UserConfig
from sfo.rules.models import OrganizationRule
from sfo.rules.parser import load_rules as _load_rules_file
from sfo.rules.validator import validate_rules


def load_user_config(paths: AppPaths) -> UserConfig:
    return UserConfig.load(paths)


def load_organization_rules(paths: AppPaths) -> tuple[list[OrganizationRule], list[str]]:
    """Returns (enabled rules, validation problems). Missing file is fine."""
    rules, parse_errors = _load_rules_file(paths.rules_path)
    problems = list(parse_errors)
    if not problems:
        problems = validate_rules(rules)
        if problems:
            return [], problems  # refuse partial adoption of an invalid rule set
    enabled = [r for r in rules if r.enabled]
    return enabled, problems


def save_user_config(paths: AppPaths, config: UserConfig) -> None:
    config.save(paths)


def config_locations(paths: AppPaths) -> dict[str, Path]:
    return {
        "settings": paths.settings_path,
        "rules": paths.rules_path,
        "history_database": paths.database_path,
        "journals": paths.journal_dir,
        "locks": paths.lock_dir,
    }
