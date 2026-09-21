"""Undo service tests: reversal through the same safety machinery.

Isolation: every test builds its own root + SFO state directory, so the
developer's real history/journals are never touched.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from sfo.domain.confidence import Confidence
from sfo.domain.plan import (
    ActionStatus,
    OrganizationPlan,
    PlannedMove,
    PlanStatistics,
    Recommendation,
)
from sfo.errors import DestinationExistsError, SfoError
from sfo.infrastructure.filesystem.linux import LinuxFileSystem
from sfo.persistence.database import Database
from sfo.undo.service import UndoService
from sfo.execution.engine import Executor, new_operation_id


@pytest.fixture()
def world(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    state = tmp_path / "sfo-state"
    paths = SimpleNamespace(
        database_path=state / "history.db",
        journal_dir=state / "journal",
        data_dir=state,
    )
    return root, paths, LinuxFileSystem()


def _identity(path: Path):
    from sfo.domain.identity import FileIdentity

    return FileIdentity.from_stat(path.stat())


def _plan(root: Path, pairs) -> OrganizationPlan:
    moves = [
        PlannedMove(
            action_id=index,
            source=source,
            destination=destination,
            file_identity=_identity(source),
            reason="test",
            reason_code="TEST",
            confidence=Confidence.HIGH,
            arrangement_value=Recommendation.RECOMMENDED,
            status=ActionStatus.MOVE,
        )
        for index, (source, destination) in enumerate(pairs, start=1)
    ]
    return OrganizationPlan(
        root=root,
        statistics=PlanStatistics(
            total_files=len(moves),
            moves=len(moves),
            unchanged=0,
            skipped=0,
            conflicts=0,
            protected=0,
            uncertain=0,
            directories_created=0,
        ),
        actions=tuple(moves),
        directory_creations=(),
        warnings=(),
    )


def test_undo_roundtrip_restores_original_structure(world):
    root, paths, fs = world
    (root / "a.txt").write_text("A")
    (root / "b.txt").write_text("B")
    dest = root / "sorted"
    plan = _plan(
        root,
        [
            (root / "a.txt", dest / "a.txt"),
            (root / "b.txt", dest / "b.txt"),
        ],
    )
    result = Executor(fs, paths.data_dir).execute(plan)
    assert result.failed == 0 and result.moved == 2

    undo = UndoService(fs, paths)
    candidates = undo.list_candidates()
    assert len(candidates) == 1 and candidates[0].restorable == 2

    undone = undo.execute_undo(candidates[0].operation_id)
    assert undone.failed == 0 and undone.moved == 2
    assert (root / "a.txt").read_text() == "A"
    assert (root / "b.txt").read_text() == "B"
    assert not (dest / "a.txt").exists()


def test_double_undo_is_refused(world):
    root, paths, fs = world
    (root / "one.txt").write_text("1")
    plan = _plan(root, [(root / "one.txt", root / "moved.txt")])
    Executor(fs, paths.data_dir).execute(plan)
    undo = UndoService(fs, paths)
    op = undo.list_candidates()[0].operation_id
    undo.execute_undo(op)
    with pytest.raises(SfoError, match="already been undone"):
        undo.execute_undo(op)


def test_undo_refuses_when_original_location_now_occupied(world):
    """No-overwrite applies to undo as well: a user-created file at the
    original path must never be clobbered by a restoration. Preflight
    aborts the entire reversal instead of partially restoring."""
    root, paths, fs = world
    source = root / "report.txt"
    source.write_text("original")
    plan = _plan(root, [(source, root / "archived" / "report.txt")])
    executor = Executor(fs, paths.data_dir)
    forward_op = new_operation_id()
    executor.execute(plan, operation_id=forward_op)
    assert not source.exists()

    # The user creates an unrelated file exactly where the undo wants to go.
    source.write_text("user's newer file")

    undo = UndoService(fs, paths)
    with pytest.raises(DestinationExistsError):
        undo.execute_undo(forward_op)
    assert source.read_text() == "user's newer file"
    assert (root / "archived" / "report.txt").exists()


def test_stale_journal_entries_are_not_restorable(world):
    """Only VERIFIED journal entries may be reversed."""
    root, paths, fs = world
    (root / "x.txt").write_text("X")
    plan = _plan(root, [(root / "x.txt", root / "y.txt")])
    Executor(fs, paths.data_dir).execute(plan)
    undo = UndoService(fs, paths)
    candidate = undo.list_candidates()[0]
    assert candidate.restorable == 1
    # Simulate a vanished destination: restorable must drop to zero.
    (root / "y.txt").unlink()
    assert undo.list_candidates()[0].restorable == 0


def test_history_records_undo_operations(world):
    """The CLI session records ORGANIZE transactions; the undo service
    records UNDO transactions. Together the history must show both and
    mark the forward operation as undone."""
    root, paths, fs = world
    (root / "doc.txt").write_text("D")
    plan = _plan(root, [(root / "doc.txt", root / "kept.txt")])

    forward_op = new_operation_id()
    db = Database(paths.database_path)
    txn_id = db.record_transaction(
        kind="ORGANIZE",
        root=root,
        plan_fingerprint="test",
        external_id=forward_op,
    )
    db.set_transaction_status(txn_id, "EXECUTING")
    Executor(fs, paths.data_dir).execute(plan, operation_id=forward_op)
    db.set_transaction_status(txn_id, "COMPLETED")

    undo = UndoService(fs, paths)
    undo.execute_undo(undo.list_candidates()[0].operation_id)

    txns = db.list_transactions(limit=10, kinds=("ORGANIZE", "UNDO"))
    kinds = {t["kind"] for t in txns}
    assert {"ORGANIZE", "UNDO"} <= kinds
    assert db.is_undone(forward_op) is True


def test_list_candidates_newest_first(world):
    root, paths, fs = world
    (root / "n1.txt").write_text("1")
    first = _plan(root, [(root / "n1.txt", root / "m1.txt")])
    executor = Executor(fs, paths.data_dir)
    executor.execute(first)
    (root / "n2.txt").write_text("2")
    second = _plan(root, [(root / "n2.txt", root / "m2.txt")])
    executor.execute(second)

    candidates = UndoService(fs, paths).list_candidates()
    ids = [c.operation_id for c in candidates]
    assert len(ids) == 2
    # Newest journal has the later mtime; ordering must reflect that.
    mtimes = [(paths.journal_dir / f"{op}.jsonl").stat().st_mtime for op in ids]
    assert mtimes == sorted(mtimes, reverse=True)
