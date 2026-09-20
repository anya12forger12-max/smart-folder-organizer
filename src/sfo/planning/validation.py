"""Plan validation: the last safety net before execution.

Runs immediately before any move is attempted and again per-action in the
executor. Every planned action is checked against *live* filesystem state,
not the state captured during scanning. Validation failures are collected,
never partially applied.
"""

from __future__ import annotations

from dataclasses import dataclass

from sfo.domain.fs_types import FileType
from sfo.domain.plan import ActionStatus, OrganizationPlan
from sfo.errors import StalePlanError
from sfo.infrastructure.filesystem import FileSystem
from sfo.domain.rules import RuleSet


@dataclass(frozen=True)
class PlanValidationResult:
    valid: bool
    problems: tuple[str, ...]


def validate_plan(
    plan: OrganizationPlan,
    fs: FileSystem,
    rules: RuleSet,
) -> PlanValidationResult:
    problems: list[str] = []

    seen_destinations: set[str] = set()
    for action in plan.moves:
        src = action.source
        dst = action.destination

        try:
            rel = src.relative_to(plan.root)
        except ValueError:
            problems.append(f"source outside root: {action.source.name}")
            continue

        try:
            dst.relative_to(plan.root)
        except ValueError:
            problems.append(f"destination outside root: {action.destination}")
            continue

        if not fs.exists(src):
            problems.append(f"source missing: {rel.as_posix()}")
        elif action.file_identity is not None:
            info = fs.inspect(src)
            ident = action.file_identity
            changed = (
                not info.exists
                or info.device != ident.device
                or info.inode != ident.inode
                or info.size != ident.size
                or (info.modified_at is not None and info.modified_at != ident.modified_at)
            )
            if changed:
                problems.append(f"source changed since scan: {rel.as_posix()}")

        key = str(dst)
        if key in seen_destinations:
            problems.append(f"two actions target the same destination: {dst.name}")
        seen_destinations.add(key)

        if rules.is_protected(plan.root, dst):
            problems.append(f"destination is protected: {dst}")
        if rules.is_protected(plan.root, src):
            problems.append(f"source became protected: {rel.as_posix()}")

    # A move whose source sits inside another move's destination would drag
    # an already-relocated file along; detect nested chains up front.
    destinations = {a.destination for a in plan.moves}
    # A move of a directory D makes every planned source inside D vanish
    # mid-transaction (order-dependent execution); refuse those too.
    moved_dirs = [
        a.source
        for a in plan.moves
        if fs.inspect(a.source).file_type is FileType.DIRECTORY
    ]
    for action in plan.moves:
        ancestors = (*destinations, *moved_dirs)
        for container in ancestors:
            if container != action.source and container in action.source.parents:
                problems.append(
                    f"chained move detected: {action.destination.name} is "
                    f"inside another planned destination"
                )
                break

    return PlanValidationResult(valid=not problems, problems=tuple(problems))


def require_valid(plan: OrganizationPlan, fs: FileSystem, rules: RuleSet) -> None:
    result = validate_plan(plan, fs, rules)
    if not result.valid:
        raise StalePlanError(
            "plan no longer matches the current state of the folder",
            details=list(result.problems),
        )


def assert_actionable(action) -> None:  # noqa: ANN001 - PlannedMove
    if action.status is not ActionStatus.MOVE:
        raise StalePlanError(f"action {action.action_id} is not a move")
