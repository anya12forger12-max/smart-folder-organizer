"""Preflight gate: everything that must pass before a single move happens.

Combines three defenses:

1. Plan validation against live filesystem state (planning.validation).
2. Per-action destination checks (no overwrite, inside root, unprotected).
3. An exclusive per-root lock so two SFO processes can never organize the
   same folder concurrently. The lock uses fcntl.flock, which the kernel
   releases automatically when a process dies - stale locks cannot outlive
   their owner, satisfying the "determine whether the lock is actually
   still active" requirement without age-based guessing.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from sfo.domain.plan import OrganizationPlan
from sfo.errors import DestinationExistsError, LockError, SecurityError, StalePlanError
from sfo.infrastructure.filesystem import FileSystem
from sfo.planning.validation import PlanValidationResult, validate_plan
from sfo.domain.rules import RuleSet


class RootLock:
    """Exclusive advisory lock for one organization root."""

    def __init__(self, lock_dir: Path, root: Path) -> None:
        digest = hashlib.sha256(str(Path(root).resolve(strict=False)).encode()).hexdigest()[:16]
        self.path = lock_dir / f"root-{digest}.lock"
        self._fd: int | None = None

    def __enter__(self) -> "RootLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise LockError(
                "another SFO process is organizing this folder",
                details=[str(self.path), str(exc)],
            ) from exc
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    problems: tuple[str, ...] = ()
    blocked_action_ids: frozenset[int] = field(default_factory=frozenset)


def run_preflight(
    plan: OrganizationPlan,
    fs: FileSystem,
    rules: RuleSet,
) -> PreflightResult:
    """Pure safety checks. Locking is the caller's (executor's) job so the
    lock can span preflight + execution as one critical section."""
    problems: list[str] = []
    blocked: set[int] = set()

    plan_result: PlanValidationResult = validate_plan(plan, fs, rules)
    if not plan_result.valid:
        problems.extend(plan_result.problems)
        raise StalePlanError(
            "plan no longer matches the current state of the folder",
            details=list(plan_result.problems),
        )

    for action in plan.moves:
        if action.destination.exists():
            if action.destination != action.source:
                blocked.add(action.action_id)
                problems.append(
                    f"destination appeared since preview: {action.destination.name}"
                )
        if not str(action.destination).startswith(str(plan.root)):
            blocked.add(action.action_id)
            problems.append(f"destination outside root: {action.destination}")

    if problems:
        destination_conflicts = [p for p in problems if "destination appeared" in p]
        if len(destination_conflicts) == len(problems):
            raise DestinationExistsError(
                "a planned destination already exists", details=problems
            )
        raise SecurityError("preflight failed", details=problems)

    return PreflightResult(ok=True, blocked_action_ids=frozenset(blocked))
