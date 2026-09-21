"""Startup reconciliation: detect interrupted operations, never auto-repair.

For every journal without a SUMMARY line, each recorded action is classified
against live filesystem state:

    both paths exist        -> NEEDS_REVIEW (never delete/overwrite either)
    only source exists      -> SAFE_TO_COMPLETE (move never committed)
    only destination exists -> needs identity verification by the user flow
    neither exists          -> UNKNOWN

Recovery is reported; it is never performed silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sfo.execution.journal import JournalState
from sfo.infrastructure.filesystem import FileSystem


class RecoveryClass(str, Enum):
    SAFE_TO_COMPLETE = "SAFE_TO_COMPLETE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNKNOWN = "UNKNOWN"
    CLEAN = "CLEAN"


@dataclass(frozen=True)
class ActionAssessment:
    action_id: int
    source: Path
    destination: Path
    state: JournalState
    classification: RecoveryClass
    detail: str


@dataclass(frozen=True)
class OperationAssessment:
    operation_id: str
    root: Path | None
    actions: tuple[ActionAssessment, ...]

    @property
    def interrupted(self) -> bool:
        return bool(self.actions)

    @property
    def worst(self) -> RecoveryClass:
        order = [
            RecoveryClass.UNKNOWN,
            RecoveryClass.NEEDS_REVIEW,
            RecoveryClass.SAFE_TO_COMPLETE,
            RecoveryClass.CLEAN,
        ]
        for cls in order:
            if any(a.classification is cls for a in self.actions):
                return cls
        return RecoveryClass.CLEAN


def assess_operation(journal_path: Path, fs: FileSystem) -> OperationAssessment | None:
    raw_entries = _raw_entries(journal_path)
    if not raw_entries:
        return None
    header = next((e for e in raw_entries if e.get("kind") == "OPERATION"), None)
    if header is None:
        return None
    if any(e.get("kind") == "SUMMARY" for e in raw_entries):
        return None  # completed cleanly (any outcome); nothing to reconcile

    root = Path(header["root"]) if header.get("root") else None
    latest: dict[int, dict] = {}
    for entry in raw_entries:
        if entry.get("kind") == "ACTION":
            aid = int(entry.get("action_id", 0))
            latest[aid] = entry  # last state wins

    assessments = []
    for aid in sorted(latest):
        entry = latest[aid]
        source = Path(entry["source"])
        destination = Path(entry["destination"])
        try:
            state = JournalState(entry.get("state", "FAILED"))
        except ValueError:
            state = JournalState.FAILED
        assessments.append(_classify(aid, source, destination, state, fs))
    return OperationAssessment(
        operation_id=journal_path.stem, root=root, actions=tuple(assessments)
    )


def _classify(
    action_id: int,
    source: Path,
    destination: Path,
    state: JournalState,
    fs: FileSystem,
) -> ActionAssessment:
    src_exists = fs.exists(source)
    dst_exists = fs.exists(destination)

    if src_exists and dst_exists:
        return ActionAssessment(
            action_id,
            source,
            destination,
            state,
            RecoveryClass.NEEDS_REVIEW,
            "source and destination both exist; nothing will be removed or "
            "overwritten - manual review required",
        )
    if not src_exists and not dst_exists:
        return ActionAssessment(
            action_id,
            source,
            destination,
            state,
            RecoveryClass.UNKNOWN,
            "neither path exists; state cannot be safely determined",
        )
    if dst_exists and not src_exists:
        return ActionAssessment(
            action_id,
            source,
            destination,
            state,
            RecoveryClass.SAFE_TO_COMPLETE,
            "move appears committed at the destination",
        )
    # source only
    return ActionAssessment(
        action_id,
        source,
        destination,
        state,
        RecoveryClass.SAFE_TO_COMPLETE,
        "move never started or was rolled back safely",
    )


def _raw_entries(path: Path) -> list[dict]:
    import json

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def pending_recoveries(state_dir: Path, fs: FileSystem) -> list[OperationAssessment]:
    results = []
    journal_dir = state_dir / "journal"
    if not journal_dir.is_dir():
        return results
    for path in sorted(journal_dir.glob("*.jsonl")):
        assessment = assess_operation(path, fs)
        if assessment is not None and assessment.interrupted:
            results.append(assessment)
    return results
