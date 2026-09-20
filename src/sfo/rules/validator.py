"""Rule validation: the gate between user-authored data and the planner.

Rules are untrusted configuration. Everything here runs BEFORE planning so
an invalid or malicious rule can only produce an error message - never a
filesystem action. Destinations must be relative POSIX paths inside the
selected root. Destructive "actions" do not exist in the model at all; any
configuration containing them is rejected outright.
"""

from __future__ import annotations

from sfo.rules.models import (
    FORBIDDEN_ACTIONS,
    OrganizationRule,
    RuleAction,
    operators_for_field,
)
from sfo.rules.priorities import MAX_PRIORITY, MIN_PRIORITY

_DANGEROUS_SUBSTRINGS = (
    ";", "&", "|", "$(", "${", "`", "\n", "\r", "\x00",
    "eval(", "exec(", "__import__", "system(", "popen(", "subprocess",
    "../", "..\\", "~/",
)
_MAX_COMPONENT_LEN = 64
_MAX_DEPTH = 6


def validate_rules(rules: list[OrganizationRule]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()

    for rule in rules:
        label = f"rule '{rule.id}'"
        if rule.id in seen_ids:
            errors.append(f"{label}: duplicate rule id")
            continue
        seen_ids.add(rule.id)

        for attr_name in ("id", "name", "explanation"):
            value = getattr(rule, attr_name)
            problems = _dangerous(value)
            if problems:
                errors.append(
                    f"{label}: {attr_name} contains forbidden content ({problems}); "
                    "rules are data and must not contain shell or code syntax"
                )

        if not (MIN_PRIORITY <= rule.priority <= MAX_PRIORITY):
            errors.append(f"{label}: priority out of range")

        if rule.action.value in FORBIDDEN_ACTIONS:
            errors.append(f"{label}: action '{rule.action.value}' does not exist in SFO")

        needs_destination = rule.action in {
            RuleAction.PREFER_DIRECTORY,
            RuleAction.PREFER_PROJECT,
            RuleAction.PREFER_TOPIC,
        }
        if needs_destination and not rule.destination:
            errors.append(f"{label}: action {rule.action.value} requires 'destination'")
        elif rule.destination:
            errors.extend(_validate_destination(label, rule.destination))

        for condition in rule.conditions:
            allowed = operators_for_field(condition.field)
            if condition.operator not in allowed:
                errors.append(
                    f"{label}: operator {condition.operator.value} is not valid "
                    f"for field {condition.field.value}"
                )
    return errors


def _validate_destination(label: str, destination: str) -> list[str]:
    problems = _dangerous(destination)
    if problems:
        return [f"{label}: destination contains forbidden content ({problems})"]
    if destination.startswith("/") or ":" in destination.split("/")[0]:
        return [f"{label}: destination must be relative to the selected root"]
    parts = [p for p in destination.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return [f"{label}: path traversal ('..') is not allowed in destinations"]
    if len(parts) > _MAX_DEPTH:
        return [f"{label}: destination deeper than {_MAX_DEPTH} levels"]
    for part in parts:
        if len(part) > _MAX_COMPONENT_LEN:
            return [f"{label}: destination component too long"]
        if part.startswith("."):
            return [f"{label}: unsafe destination component '{part}'"]
    return []


def _dangerous(text: str | None) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for needle in _DANGEROUS_SUBSTRINGS:
        if needle.lower() in lowered:
            return needle
    if any(ord(ch) < 32 for ch in text):
        return "control characters"
    return None
