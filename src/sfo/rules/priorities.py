"""Rule priorities and immutable built-in constraints.

Priority ladder (higher wins):

    100 PROTECTED            safety: never move
     90 IGNORED              safety: never analyze/move
     80 EXISTING_STRUCTURE   strong preference to keep organized folders
     70 USER_RULES           explicit user organization preferences
     60 PROJECT detection
     50 TOPIC detection
     30 extension-style fallbacks (not enabled by default)

IMMUTABLE_SAFETY_CONSTRAINTS are NOT rules. They sit above the entire ladder
and no user rule, flag or configuration can disable them.
"""

from __future__ import annotations

BUILTIN_PRIORITIES: dict[str, int] = {
    "PROTECTED": 100,
    "IGNORED": 90,
    "EXISTING_STRUCTURE": 80,
    "USER_RULES": 70,
    "PROJECT": 60,
    "TOPIC": 50,
}

USER_RULE_DEFAULT_PRIORITY = 70
MIN_PRIORITY = 1
MAX_PRIORITY = 100

IMMUTABLE_SAFETY_CONSTRAINTS: tuple[str, ...] = (
    "NO_DELETE",
    "NO_OVERWRITE",
    "NO_CONTENT_MODIFICATION",
    "ROOT_CONTAINMENT",
    "PROTECTED_PATHS",
    "IGNORED_PATHS",
    "EXPLICIT_CONFIRMATION",
    "STALE_PLAN_PROTECTION",
)
