"""Rule evaluation: deterministic priority-ordered matching.

Evaluation is pure: rules (data) + a RuleContext (scan metadata) -> decisions.
Nothing here touches the filesystem. Ties on priority keep list order, so
identical inputs always yield identical outcomes; genuinely ambiguous
equal-priority conflicts are surfaced by detect_conflicts() instead of being
silently resolved.
"""

from __future__ import annotations

from sfo.rules.matcher import describe, matches
from sfo.rules.models import (
    OrganizationRule,
    RuleAction,
    RuleContext,
)


def evaluate_rules(
    rules: list[OrganizationRule], context: RuleContext
) -> list[tuple[OrganizationRule, str]]:
    """All matching enabled rules, best-first (priority desc, then order)."""
    hits: list[tuple[int, int, OrganizationRule, str]] = []
    for index, rule in enumerate(rules):
        if not rule.enabled:
            continue
        for condition in rule.conditions:
            if matches(condition, context):
                hits.append((-rule.priority, index, rule, describe(condition)))
                break  # first matching condition decides this rule's hit
    hits.sort(key=lambda item: (item[0], item[1]))
    return [(rule, matched) for _, _, rule, matched in hits]


def first_matching_rule(
    rules: list[OrganizationRule], context: RuleContext
) -> tuple[OrganizationRule, str] | None:
    evaluated = evaluate_rules(rules, context)
    return evaluated[0] if evaluated else None


def detect_conflicts(rules: list[OrganizationRule]) -> list[str]:
    """Structural conflicts detectable without a file: identical condition
    sets at equal priority but different destinations."""
    problems: list[str] = []
    seen: dict[tuple, tuple[str, str | None]] = {}
    for rule in rules:
        if not rule.enabled or rule.action is not RuleAction.PREFER_DIRECTORY:
            continue
        key = (
            tuple(sorted((c.field.value, c.operator.value, str(c.value)) for c in rule.conditions)),
            rule.priority,
        )
        if key in seen:
            other_id, other_dest = seen[key]
            if rule.destination != other_dest:
                problems.append(
                    f"rules '{other_id}' and '{rule.id}' have identical "
                    f"conditions and priority but different destinations "
                    f"({other_dest!r} vs {rule.destination!r})"
                )
        else:
            seen[key] = (rule.id, rule.destination)
    return problems
