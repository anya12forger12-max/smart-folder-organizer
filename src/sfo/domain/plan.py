"""OrganizationPlan and its actions.

The plan is the ONLY artifact the arrangement engine produces. It proposes;
it never performs. Execution happens exclusively in sfo.execution after a
security gate, revalidation and explicit user confirmation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from sfo.domain.confidence import Confidence
from sfo.domain.identity import FileIdentity


class ActionStatus(str, Enum):
    MOVE = "MOVE"
    KEEP = "KEEP"
    SKIP = "SKIP"
    CONFLICT = "CONFLICT"
    PROTECTED = "PROTECTED"
    UNCERTAIN = "UNCERTAIN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class Recommendation(str, Enum):
    """Internal arrangement-value categories. Never shown as raw numbers."""

    STRONGLY_RECOMMENDED = "STRONGLY_RECOMMENDED"
    RECOMMENDED = "RECOMMENDED"
    OPTIONAL = "OPTIONAL"
    LOW_VALUE = "LOW_VALUE"
    DO_NOT_MOVE = "DO_NOT_MOVE"

    @classmethod
    def executable(cls) -> tuple["Recommendation", ...]:
        return (cls.STRONGLY_RECOMMENDED, cls.RECOMMENDED)


@dataclass(frozen=True, slots=True)
class PlannedMove:
    action_id: int
    source: Path
    destination: Path  # == source for non-move statuses
    file_identity: FileIdentity | None
    reason: str  # human-readable explanation
    reason_code: str  # e.g. PROJECT_MATCH, ALREADY_ORGANIZED, INSUFFICIENT_EVIDENCE
    confidence: Confidence
    arrangement_value: Recommendation
    status: ActionStatus
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class DirectoryCreation:
    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class PlanStatistics:
    total_files: int
    moves: int
    unchanged: int
    skipped: int
    conflicts: int
    protected: int
    uncertain: int
    directories_created: int


@dataclass(frozen=True, slots=True)
class OrganizationPlan:
    # NOTE: fields without defaults must precede defaulted fields.
    root: Path
    statistics: PlanStatistics
    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_snapshot: str = ""
    rules_fingerprint: str = ""
    actions: tuple[PlannedMove, ...] = ()
    directory_creations: tuple[DirectoryCreation, ...] = ()
    warnings: tuple[str, ...] = ()
    fingerprint: str = ""

    @property
    def moves(self) -> tuple[PlannedMove, ...]:
        return tuple(a for a in self.actions if a.status is ActionStatus.MOVE)

    @property
    def keeps(self) -> tuple[PlannedMove, ...]:
        return tuple(a for a in self.actions if a.status is ActionStatus.KEEP)

    @property
    def conflicts(self) -> tuple[PlannedMove, ...]:
        return tuple(
            a
            for a in self.actions
            if a.status in (ActionStatus.CONFLICT, ActionStatus.REVIEW_REQUIRED)
        )

    @property
    def uncertain_actions(self) -> tuple[PlannedMove, ...]:
        return tuple(a for a in self.actions if a.status is ActionStatus.UNCERTAIN)

    @property
    def protected_actions(self) -> tuple[PlannedMove, ...]:
        return tuple(a for a in self.actions if a.status is ActionStatus.PROTECTED)
