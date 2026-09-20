"""UndoService: user-facing Undo built on top of the executor.

Undo reuses every safety mechanism of a normal run: root lock, preflight,
journal and no-overwrite moves. It refuses to touch operations whose journal
is missing/unreadable, and tracks completed undos in the history database so
a second `sfo undo` can never silently reverse an unrelated older run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sfo.errors import JournalError, SfoError
from sfo.execution.engine import ExecutionResult, Executor, new_operation_id
from sfo.execution.journal import JournalState, load_journal
from sfo.infrastructure.filesystem import FileSystem
from sfo.persistence.database import Database
from sfo.undo.reverse_plan import build_reverse_plan


@dataclass(frozen=True)
class UndoCandidate:
    operation_id: str
    journal_path: Path
    root: Path
    restorable: int
    status: str


class UndoService:
    def __init__(self, fs: FileSystem, paths: AppPathsLike) -> None:  # noqa: ANN001 - AppPaths
        self._fs = fs
        self._paths = paths

    # ------------------------------------------------------------------
    def list_candidates(self, limit: int = 10) -> list[UndoCandidate]:
        db = Database(self._paths.database_path)
        candidates: list[UndoCandidate] = []
        journal_dir = self._paths.journal_dir
        if not journal_dir.is_dir():
            return candidates
        # Order by modification time (newest first). Lexical order would be
        # misleading: operation IDs contain a random suffix, not a sequence.
        journals = sorted(
            journal_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]
        for path in journals:
            entries = load_journal(path)
            verified = [e for e in entries if e.state is JournalState.VERIFIED]
            if not verified:
                continue
            operation_id = path.stem
            root = _root_of(path) or Path("/")
            already = db.is_undone(operation_id)
            # Honest count: only moves whose recorded destination still
            # exists right now can even be considered for reversal. The
            # executor's preflight remains the final authority.
            restorable = sum(1 for e in verified if self._fs.exists(Path(e.destination)))
            candidates.append(
                UndoCandidate(
                    operation_id=operation_id,
                    journal_path=path,
                    root=root,
                    restorable=restorable,
                    status="undone" if already else "available",
                )
            )
        return candidates

    # ------------------------------------------------------------------
    def execute_undo(self, operation_id: str) -> ExecutionResult:
        db = Database(self._paths.database_path)
        journal_path = self._paths.journal_dir / f"{operation_id}.jsonl"
        if not journal_path.exists():
            raise JournalError(f"no journal found for {operation_id}")
        if db.is_undone(operation_id):
            raise SfoError(f"operation {operation_id} has already been undone")
        root = _root_of(journal_path)
        if root is None:
            raise JournalError("journal does not record an organization root")

        undo_op_id = f"{new_operation_id()}-undo"
        txn_id = db.record_transaction(
            kind="UNDO", root=root, external_id=undo_op_id
        )
        db.set_transaction_status(txn_id, "EXECUTING")

        reverse = build_reverse_plan(journal_path, root, self._fs)
        executor = Executor(self._fs, self._paths.data_dir)
        result = executor.execute(reverse)

        db.set_transaction_status(
            txn_id, "COMPLETED" if result.failed == 0 else ("PARTIAL" if result.moved else "FAILED")
        )
        seq = 0
        for action in reverse.moves:
            seq += 1
            failure = next((f for f in result.failures if f.action_id == action.action_id), None)
            db.record_operation(
                txn_id=txn_id,
                seq=seq,
                op_kind="UNDO",
                source=action.source,
                destination=action.destination,
                expected_identity=None,
                result_identity=None,
                status=("VERIFIED" if failure is None else f"FAILED:{failure.reason_code}"),
                error=(failure.message if failure else None),
            )
        if result.moved > 0:
            db.mark_undone(operation_id)
        return result


# Alias keeps the type annotation readable without importing AppPaths here.
AppPathsLike = object


def _root_of(journal_path: Path) -> Path | None:
    import json

    try:
        text = journal_path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("kind") == "OPERATION" and entry.get("root"):
            return Path(entry["root"])
    return None
