"""Reverse-plan construction for Undo.

An undo is just a normal validated plan whose sources are the destinations
recorded in a verified transaction journal and vice versa. It flows through
exactly the same preflight, locking and executor path as a forward run -
Undo is never a privileged bypass. Actions that did not reach VERIFIED
state are excluded automatically.
"""

from __future__ import annotations

from pathlib import Path

from sfo.domain.confidence import Confidence
from sfo.domain.plan import (
    ActionStatus,
    OrganizationPlan,
    PlannedMove,
    PlanStatistics,
    Recommendation,
)
from sfo.errors import JournalError
from sfo.execution.journal import JournalState, load_journal


def reverse_actions(journal_path: Path) -> tuple[PlannedMove, ...]:
    entries = load_journal(journal_path)
    verified = [e for e in entries if e.state is JournalState.VERIFIED]
    if not verified:
        raise JournalError("no verified moves found in this journal; nothing can be undone")
    reversed_moves = []
    for index, entry in enumerate(verified, start=1):
        # Identity is deliberately re-established from LIVE state by the
        # caller (see attach_identity); journal metadata is data, never
        # instructions - see docs/threat-model.md.
        reversed_moves.append(
            PlannedMove(
                action_id=index,
                source=Path(entry.destination),
                destination=Path(entry.source),
                file_identity=None,
                reason=f"undo of operation move #{entry.action_id}",
                reason_code="UNDO",
                confidence=Confidence.HIGH,
                arrangement_value=Recommendation.RECOMMENDED,
                status=ActionStatus.MOVE,
            )
        )
    return tuple(reversed_moves)


def attach_identity(actions: tuple[PlannedMove, ...], fs) -> tuple[PlannedMove, ...]:  # noqa: ANN001
    """Re-record identity for each undo source from the CURRENT filesystem.

    This gives the executor's verification step something truthful to check
    against: the object as it exists right now, not as the journal remembers
    it. Sources that vanished are left untouched - preflight refuses them.
    """
    from sfo.domain.identity import FileIdentity

    refreshed: list[PlannedMove] = []
    for index, action in enumerate(actions, start=1):
        try:
            info = fs.inspect(action.source)
        except Exception:  # noqa: BLE001 - unreadable source: let preflight refuse it
            info = None
        identity = None
        if info is not None and info.exists and info.inode:
            identity = FileIdentity(
                device=info.device or 0,
                inode=info.inode,
                size=info.size or 0,
                modified_at=info.modified_at or 0.0,
                file_type=info.file_type,
            )
        refreshed.append(
            PlannedMove(
                action_id=index,
                source=action.source,
                destination=action.destination,
                file_identity=identity,
                reason=action.reason,
                reason_code=action.reason_code,
                confidence=action.confidence,
                arrangement_value=action.arrangement_value,
                status=action.status,
            )
        )
    return tuple(refreshed)


def build_reverse_plan(journal_path: Path, root: Path, fs=None) -> OrganizationPlan:  # noqa: ANN001
    actions = reverse_actions(journal_path)
    if fs is not None:
        actions = attach_identity(actions, fs)
    statistics = PlanStatistics(
        total_files=len(actions),
        moves=len(actions),
        unchanged=0,
        skipped=0,
        conflicts=0,
        protected=0,
        uncertain=0,
        directories_created=0,
    )
    return OrganizationPlan(
        root=root,
        statistics=statistics,
        actions=actions,
        directory_creations=(),
        warnings=("undo operation: restoring files to their previous locations",),
    )
