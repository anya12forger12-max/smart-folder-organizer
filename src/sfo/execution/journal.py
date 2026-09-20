"""Transaction journal: the authoritative record of filesystem mutations.

Every executor action transitions through explicit journal states:

    PLANNED -> VALIDATED -> STARTED -> COMPLETED -> VERIFIED
                                     |-> FAILED

plus RECOVERY_REQUIRED when a crash/interrupt leaves ambiguity. State is
written BEFORE the corresponding filesystem call and re-written after,
with flush+fsync on every transition, so an interrupted process leaves a
durable trace. The journal never contains file contents and never becomes
a second mutation system: it records, it does not act.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from sfo.errors import JournalError


class JournalState(str, Enum):
    PLANNED = "PLANNED"
    VALIDATED = "VALIDATED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class OpStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True, slots=True)
class JournalEntry:
    state: JournalState
    action_id: int
    source: str
    destination: str
    timestamp: str
    detail: str = ""


class TransactionJournal:
    """Append-only, fsync-per-transition JSONL journal for one operation."""

    def __init__(self, path: Path, operation_id: str, root: Path) -> None:
        self.path = path
        self.operation_id = operation_id
        self.root = root
        self._states: dict[int, JournalState] = {}
        self._header_written = False

    # -- lifecycle -----------------------------------------------------
    def open(self, plan_id: str, total_actions: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self._header_written:
            self._append(
                {
                    "kind": "OPERATION",
                    "operation_id": self.operation_id,
                    "plan_id": plan_id,
                    "root": str(self.root),
                    "status": OpStatus.IN_PROGRESS.value,
                    "total_actions": total_actions,
                    "timestamp": _now(),
                }
            )
            self._header_written = True

    def close(self, status: OpStatus, moved: int, verified: int, failed: int) -> None:
        self._append(
            {
                "kind": "SUMMARY",
                "operation_id": self.operation_id,
                "status": status.value,
                "moved": moved,
                "verified": verified,
                "failed": failed,
                "timestamp": _now(),
            }
        )

    # -- per-action transitions ----------------------------------------
    def record(
        self,
        state: JournalState,
        action_id: int,
        source: Path,
        destination: Path,
        detail: str = "",
    ) -> None:
        self._append(
            {
                "kind": "ACTION",
                "operation_id": self.operation_id,
                "action_id": action_id,
                "state": state.value,
                "source": source.as_posix(),
                "destination": destination.as_posix(),
                "detail": detail,
                "timestamp": _now(),
            }
        )
        self._states[action_id] = state

    def state_of(self, action_id: int) -> JournalState | None:
        return self._states.get(action_id)

    @property
    def states(self) -> dict[int, JournalState]:
        return dict(self._states)

    def requires_recovery(self) -> bool:
        """True when any action ended in a non-terminal, non-success state."""
        ambiguous = {JournalState.STARTED, JournalState.FAILED}
        recovery = any(s in ambiguous for s in self._states.values())
        if not recovery and self._header_written:
            recovery = not any(
                e.get("kind") == "SUMMARY" for e in self._read_entries()
            )
        return recovery

    # -- io --------------------------------------------------------------
    def _append(self, payload: dict) -> None:
        line = json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n"
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

    def _read_entries(self) -> list[dict]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return []
        entries = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # torn tail write from a crash: ignore partial line
        return entries


def load_journal(path: Path) -> list[JournalEntry]:
    """Reconstruct ordered action entries from a journal file.

    Journals are append-only with one fsynced line per event, so a torn
    tail write (crash mid-append) can only ever damage the FINAL line -
    that case is tolerated. Corruption anywhere else means the journal
    was truncated or tampered with and undo must refuse rather than
    silently act on a partial view. Unreadable journals are also refused.
    """
    entries: list[JournalEntry] = []
    latest: dict[int, JournalEntry] = {}
    op_path = Path(path)
    try:
        raw = op_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise JournalError(f"journal {op_path.name} cannot be read: {exc}") from exc
    lines = raw.splitlines()
    for number, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            if number == len(lines) - 1:
                continue  # torn final write from a crash: safe to ignore
            raise JournalError(
                f"journal {op_path.name} is corrupted at line {number + 1}; "
                "refusing to interpret a damaged transaction record"
            ) from exc
        if data.get("kind") != "ACTION":
            continue
        try:
            entry = JournalEntry(
                state=JournalState(data["state"]),
                action_id=int(data["action_id"]),
                source=data["source"],
                destination=data["destination"],
                timestamp=data.get("timestamp", ""),
                detail=data.get("detail", ""),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise JournalError(
                f"journal {op_path.name} contains an invalid ACTION entry "
                f"(line {number + 1}): {exc}"
            ) from exc
        latest[entry.action_id] = entry  # last state wins
    for action_id in sorted(latest):
        entries.append(latest[action_id])
    return entries
