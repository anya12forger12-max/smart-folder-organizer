"""Stable CLI exit codes. Never renumber; scripts depend on these."""

SUCCESS = 0                 # completed (or clean preview/cancel)
GENERAL_FAILURE = 1         # unexpected internal error
INVALID_USAGE = 2           # bad arguments/paths
SAFETY_BLOCKED = 3          # security gate / protected path refusal
CONFLICTS = 4               # destination conflicts prevented completion
RECOVERY_REQUIRED = 5       # interrupted operation needs attention
STALE_PLAN = 6              # folder changed after preview; refresh needed
PARTIAL = 7                 # some moves succeeded, some failed

NAMES = {
    SUCCESS: "success",
    GENERAL_FAILURE: "general_failure",
    INVALID_USAGE: "invalid_usage",
    SAFETY_BLOCKED: "safety_blocked",
    CONFLICTS: "conflicts",
    RECOVERY_REQUIRED: "recovery_required",
    STALE_PLAN: "stale_plan",
    PARTIAL: "partial",
}
