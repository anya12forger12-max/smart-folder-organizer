"""Executor: the ONLY component that mutates user files, and only moves.

Execution contract, in order:
    lock root -> preflight -> create directories -> per action:
        journal VALIDATED -> journal STARTED -> move (refuses overwrite)
        -> journal COMPLETED -> verify identity at destination
        -> journal VERIFIED | FAILED(RECOVERY_REQUIRED)
    -> summary -> release lock

Failure policy: a failed action never stops safe ones; results are PARTIAL,
never silently successful. Nothing is deleted, overwritten or retried in a
loop. Cross-filesystem moves are refused outright (rename semantics cannot
be guaranteed without copy+delete, which is prohibited).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sfo.domain.plan import ActionStatus, OrganizationPlan
from sfo.errors import (
    CrossFilesystemMoveError,
    DestinationExistsError,
    LockError,
    SfoError,
)
from sfo.execution.journal import JournalState, OpStatus, TransactionJournal
from sfo.execution.preflight import RootLock, run_preflight
from sfo.infrastructure.filesystem import FileSystem
from sfo.domain.rules import RuleSet


@dataclass(frozen=True)
class ExecutionFailure:
    action_id: int
    name: str
    reason_code: str
    message: str


@dataclass(frozen=True)
class ExecutionResult:
    operation_id: str
    plan_id: str
    status: OpStatus
    moved: int = 0
    verified: int = 0
    failed: int = 0
    failures: tuple[ExecutionFailure, ...] = ()
    journal_path: Path | None = None


def new_operation_id() -> str:
    year = datetime.now(timezone.utc).year
    return f"SFO-{year}-{uuid.uuid4().hex[:6]}"


class Executor:
    def __init__(self, fs: FileSystem, state_dir: Path) -> None:
        self._fs = fs
        self._journal_dir = state_dir / "journal"
        self._lock_dir = state_dir / "locks"

    # ------------------------------------------------------------------
    def execute(
        self,
        plan: OrganizationPlan,
        rules: RuleSet = RuleSet.EMPTY,
        operation_id: str | None = None,
    ) -> ExecutionResult:
        operation_id = operation_id or new_operation_id()
        journal = TransactionJournal(
            self._journal_dir / f"{operation_id}.jsonl", operation_id, plan.root
        )

        lock = RootLock(self._lock_dir, plan.root)
        try:
            lock.acquire()  # raises LockError when another run owns the root
        except LockError as exc:
            raise SfoError(str(exc)) from exc

        try:
            return self._execute_locked(plan, rules, journal, operation_id)
        finally:
            lock.release()

    # ------------------------------------------------------------------
    def _execute_locked(
        self,
        plan: OrganizationPlan,
        rules: RuleSet,
        journal: TransactionJournal,
        operation_id: str,
    ) -> ExecutionResult:
        run_preflight(plan, self._fs, rules)  # raises on stale/conflicts
        journal.open(plan_id=plan.plan_id, total_actions=len(plan.moves))

        for creation in plan.directory_creations:
            self._fs.create_directory(creation.path)

        moved = verified = failed = 0
        failures: list[ExecutionFailure] = []

        for action in plan.moves:
            if action.status is not ActionStatus.MOVE:
                continue
            journal.record(JournalState.VALIDATED, action.action_id, action.source, action.destination)
            journal.record(JournalState.STARTED, action.action_id, action.source, action.destination)

            try:
                self._fs.move(action.source, action.destination)
            except DestinationExistsError as exc:
                failed += 1
                journal.record(
                    JournalState.FAILED, action.action_id, action.source, action.destination,
                    detail="destination exists; nothing was overwritten",
                )
                failures.append(ExecutionFailure(action.action_id, action.destination.name, "CONFLICT", str(exc)))
                continue
            except CrossFilesystemMoveError as exc:
                failed += 1
                journal.record(
                    JournalState.FAILED, action.action_id, action.source, action.destination,
                    detail="cross-filesystem move blocked",
                )
                failures.append(ExecutionFailure(action.action_id, action.source.name, "CROSS_FILESYSTEM", str(exc)))
                continue
            except OSError as exc:
                failed += 1
                journal.record(
                    JournalState.FAILED, action.action_id, action.source, action.destination,
                    detail=f"filesystem error: {exc.strerror or exc}",
                )
                failures.append(ExecutionFailure(action.action_id, action.source.name, "FILESYSTEM_ERROR", str(exc)))
                continue

            journal.record(JournalState.COMPLETED, action.action_id, action.source, action.destination)
            moved += 1

            if self._verify(action):
                journal.record(JournalState.VERIFIED, action.action_id, action.source, action.destination)
                verified += 1
            else:
                journal.record(
                    JournalState.RECOVERY_REQUIRED,
                    action.action_id, action.source, action.destination,
                    detail="verification could not confirm the moved file",
                )
                failures.append(
                    ExecutionFailure(action.action_id, action.destination.name, "VERIFICATION_FAILED", "")
                )
                failed += 1

        status = OpStatus.COMPLETED
        if failed and moved:
            status = OpStatus.PARTIAL
        elif failed and not moved:
            status = OpStatus.FAILED
        journal.close(status=status, moved=moved, verified=verified, failed=failed)

        return ExecutionResult(
            operation_id=operation_id,
            plan_id=plan.plan_id,
            status=status,
            moved=moved,
            verified=verified,
            failed=failed,
            failures=tuple(failures),
            journal_path=journal.path,
        )

    # ------------------------------------------------------------------
    def _verify(self, action) -> bool:  # noqa: ANN001 - PlannedMove
        info = self._fs.inspect(action.destination)
        ident = action.file_identity
        if info is None or not info.exists or ident is None:
            return False
        same_object = (
            info.device == ident.device
            and info.inode == ident.inode
            and info.size == ident.size
        )
        source_gone = not self._fs.exists(action.source)
        return same_object and source_gone
