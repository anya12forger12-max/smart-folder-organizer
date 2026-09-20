"""Rules subsystem public API.

Rules are pure DATA (conditions -> safe action preferences). Parsing,
validation and evaluation are deterministic; nothing in this package can
execute code or touch the filesystem.
"""

from sfo.rules.engine import (
    detect_conflicts,
    evaluate_rules,
    first_matching_rule,
)
from sfo.rules.models import (
    Condition,
    OrganizationRule,
    RuleAction,
    RuleContext,
    RuleDecision,
    RuleField,
    RuleOperator,
)
from sfo.rules.priorities import MAX_PRIORITY, MIN_PRIORITY
from sfo.rules.validator import validate_rules

__all__ = [
    "MAX_PRIORITY",
    "MIN_PRIORITY",
    "Condition",
    "OrganizationRule",
    "RuleAction",
    "RuleContext",
    "RuleDecision",
    "RuleField",
    "RuleOperator",
    "detect_conflicts",
    "evaluate_rules",
    "first_matching_rule",
    "validate_rules",
]
