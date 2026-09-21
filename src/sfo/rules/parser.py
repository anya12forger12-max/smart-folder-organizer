"""Rule file parsing.

Rules live in ~/.config/sfo/rules.toml and are parsed with tomllib as pure
DATA. There is no expression language, no eval/exec, no shell, no imports —
a rule file that is not exactly the expected shape is rejected, never
interpreted creatively.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from sfo.errors import RuleConfigError
from sfo.rules.models import (
    Condition,
    OrganizationRule,
    RuleAction,
    RuleField,
    RuleOperator,
)
from sfo.rules.priorities import MAX_PRIORITY, MIN_PRIORITY, USER_RULE_DEFAULT_PRIORITY

_MAX_RULES = 200
_MAX_CONDITIONS_PER_RULE = 8


def parse_rules(data: bytes) -> list[OrganizationRule]:
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RuleConfigError(f"rules.toml could not be parsed: {exc}") from exc

    unknown = set(document) - {"config_version", "rules"}
    if unknown:
        raise RuleConfigError(f"unknown top-level keys in rules.toml: {sorted(unknown)}")
    version = document.get("config_version", 1)
    if version != 1:
        raise RuleConfigError(f"unsupported rules config_version: {version}")

    entries = document.get("rules", [])
    if not isinstance(entries, list):
        raise RuleConfigError("'rules' must be an array of tables")
    if len(entries) > _MAX_RULES:
        raise RuleConfigError(f"too many rules (limit {_MAX_RULES})")

    rules: list[OrganizationRule] = []
    for index, entry in enumerate(entries):
        rules.append(_parse_rule(entry, index))
    return rules


def serialize_rules(rules: list[OrganizationRule]) -> bytes:
    """Emit rules back to TOML. Data-only; mirrors parse_rules exactly."""
    lines = ["config_version = 1", ""]
    for rule in rules:
        lines.append("[[rules]]")
        lines.append(f"id = {_toml_str(rule.id)}")
        lines.append(f"name = {_toml_str(rule.name)}")
        lines.append(f"enabled = {'true' if rule.enabled else 'false'}")
        lines.append(f"priority = {int(rule.priority)}")
        lines.append(f"action = {_toml_str(rule.action.value)}")
        if rule.destination is not None:
            lines.append(f"destination = {_toml_str(rule.destination)}")
        if rule.explanation:
            lines.append(f"explanation = {_toml_str(rule.explanation)}")
        for condition in rule.conditions:
            lines.append("")
            lines.append("[[rules.conditions]]")
            lines.append(f"field = {_toml_str(condition.field.value)}")
            lines.append(f"operator = {_toml_str(condition.operator.value)}")
            lines.append(f"value = {_toml_value(condition.value)}")
            if condition.value2 is not None:
                lines.append(f"value2 = {_toml_value(condition.value2)}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def save_rules(path: Path, rules: list[OrganizationRule]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialize_rules(rules))


def _toml_str(value: str) -> str:
    out = value.replace("\\", "\\\\").replace('"', '\\"')
    out = "".join(f"\\u{ord(ch):04X}" if ord(ch) < 32 else ch for ch in out)
    return f'"{out}"'


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return _toml_str(str(value))


def load_rules(path: Path) -> tuple[list[OrganizationRule], list[str]]:
    """Returns (rules, errors). Never raises for a missing file."""
    if not path.exists():
        return [], []
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RuleConfigError(f"cannot read {path}: {exc}") from exc
    if not data.strip():
        return [], []
    try:
        return parse_rules(data), []
    except RuleConfigError as exc:
        return [], [str(exc)]


_ALLOWED_KEYS = {
    "id",
    "name",
    "enabled",
    "priority",
    "action",
    "destination",
    "explanation",
    "conditions",
}


def _parse_rule(entry: object, index: int) -> OrganizationRule:
    if not isinstance(entry, dict):
        raise RuleConfigError(f"rule #{index + 1} must be a table")
    unknown = set(entry) - _ALLOWED_KEYS
    if unknown:
        raise RuleConfigError(f"rule #{index + 1}: unknown keys {sorted(unknown)}")

    rule_id = entry.get("id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise RuleConfigError(f"rule #{index + 1}: 'id' is required")

    action_raw = entry.get("action", "")
    try:
        action = RuleAction(str(action_raw).upper())
    except ValueError as exc:
        raise RuleConfigError(
            f"rule '{rule_id}': unsupported action '{action_raw}'. "
            f"Allowed: {sorted(a.value for a in RuleAction.allowed())}. "
            "Destructive actions do not exist in SFO."
        ) from exc

    priority = entry.get("priority", USER_RULE_DEFAULT_PRIORITY)
    if not isinstance(priority, int) or not (MIN_PRIORITY <= priority <= MAX_PRIORITY):
        raise RuleConfigError(
            f"rule '{rule_id}': priority must be an integer in [{MIN_PRIORITY}, {MAX_PRIORITY}]"
        )

    conditions_raw = entry.get("conditions", [])
    if not isinstance(conditions_raw, list) or not conditions_raw:
        raise RuleConfigError(f"rule '{rule_id}': at least one condition is required")
    if len(conditions_raw) > _MAX_CONDITIONS_PER_RULE:
        raise RuleConfigError(
            f"rule '{rule_id}': too many conditions (limit {_MAX_CONDITIONS_PER_RULE})"
        )

    conditions = tuple(_parse_condition(rule_id, c) for c in conditions_raw)

    destination = entry.get("destination")
    if destination is not None and not isinstance(destination, str):
        raise RuleConfigError(f"rule '{rule_id}': destination must be a string")

    return OrganizationRule(
        id=rule_id,
        name=str(entry.get("name", rule_id)),
        priority=priority,
        action=action,
        conditions=conditions,
        destination=destination,
        enabled=bool(entry.get("enabled", True)),
        explanation=str(entry.get("explanation", "")),
    )


def _parse_condition(rule_id: str, raw: object) -> Condition:
    if not isinstance(raw, dict):
        raise RuleConfigError(f"rule '{rule_id}': each condition must be a table")
    unknown = set(raw) - {"field", "operator", "value", "value2"}
    if unknown:
        raise RuleConfigError(f"rule '{rule_id}': unknown condition keys {sorted(unknown)}")
    try:
        field = RuleField(str(raw["field"]).lower())
        operator = RuleOperator(str(raw["operator"]).lower())
    except KeyError as exc:
        raise RuleConfigError(f"rule '{rule_id}': condition missing {exc}") from exc
    except ValueError as exc:
        raise RuleConfigError(f"rule '{rule_id}': unknown condition field/operator: {exc}") from exc
    if "value" not in raw:
        raise RuleConfigError(f"rule '{rule_id}': condition requires a value")
    value = raw["value"]
    value2 = raw.get("value2")
    valid_ops = operators_for_field_checked(field)
    if operator not in valid_ops:
        raise RuleConfigError(
            f"rule '{rule_id}': operator '{operator.value}' is not valid for field "
            f"'{field.value}' (allowed: {sorted(o.value for o in valid_ops)})"
        )
    if operator.value == "between" and value2 is None:
        raise RuleConfigError(f"rule '{rule_id}': 'between' requires value2")
    return Condition(field=field, operator=operator, value=value, value2=value2)


def operators_for_field_checked(field: RuleField):
    from sfo.rules.models import operators_for_field

    return operators_for_field(field)
