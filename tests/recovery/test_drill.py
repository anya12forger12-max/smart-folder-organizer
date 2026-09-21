"""Disaster-recovery drill: crash mid-transaction, detect, report, re-run.

SFO's recovery policy is report-never-repair: interrupted operations are
classified against filesystem truth and surfaced; nothing is mutated
automatically. These tests pin the drill end to end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sfo.cli.app import main
from sfo.domain.confidence import Confidence
from sfo.domain.plan import (
    ActionStatus,
    OrganizationPlan,
    PlannedMove,
    PlanStatistics,
    Recommendation,
)
from sfo.execution.engine import Executor, new_operation_id
from sfo.infrastructure.filesystem.linux import LinuxFileSystem
from sfo.recovery.reconciliation import (
    RecoveryClass,
    assess_operation,
    pending_recoveries,
)


def _identity(path: Path):
    import os

    from sfo.domain.identity import FileIdentity

    return FileIdentity.from_stat(os.lstat(path))


def _plan(root: Path, pairs) -> OrganizationPlan:
    moves = [
        PlannedMove(
            action_id=index,
            source=source,
            destination=destination,
            file_identity=_identity(source),
            reason="drill",
            reason_code="DRILL",
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


def _tree(root: Path) -> dict[str, int]:
    return {
        str(p.relative_to(root)): p.stat().st_size
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }


@pytest.fixture()
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Full XDG isolation: AppPaths.default() inside main() must resolve to
    # the same state root the Executor writes to, otherwise recover would
    # silently inspect the developer's real SFO state.
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_STATE_HOME", str(xdg / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg / "cache"))
    root = tmp_path / "Downloads"
    root.mkdir()
    for name in ("a.txt", "b.txt", "c.txt", "d.txt"):
        (root / name).write_text(f"content-{name}")
    state_dir = xdg / "state" / "sfo"  # == AppPaths.default().data_dir
    state_dir.mkdir(parents=True)
    return root, state_dir, LinuxFileSystem()


def test_crash_midway_is_detected_and_reported_never_auto_repaired(world, capsys):
    root, state_dir, fs = world
    op = new_operation_id()
    pairs = [
        (root / "a.txt", root / "archived" / "a.txt"),
        (root / "b.txt", root / "archived" / "b.txt"),
        (root / "c.txt", root / "archived" / "c.txt"),
    ]
    (root / "archived").mkdir()

    real_move = fs.move
    done = {"n": 0}

    def crashing_move(src, dst):
        if done["n"] == 1:
            # A bare OSError would be contained per-action by the engine
            # (correct production behavior); simulate abrupt termination
            # with an exception the engine does not intercept.
            raise RuntimeError("simulated abrupt termination")
        done["n"] += 1
        return real_move(src, dst)

    # Plain assignment, NOT monkeypatch: calling monkeypatch.undo() later
    # would also revert the fixture's XDG isolation and send the CLI's
    # recover() at the developer's real state directory.
    fs.move = crashing_move
    try:
        with pytest.raises(RuntimeError):
            Executor(fs, state_dir).execute(_plan(root, pairs), operation_id=op)
    finally:
        fs.move = real_move

    # Journal exists but never reached a terminal summary.
    journal = state_dir / "journal" / f"{op}.jsonl"
    assert journal.exists()
    entries = [json.loads(line) for line in journal.read_text().splitlines()]
    kinds = {entry.get("kind") for entry in entries}
    assert "OPERATION" in kinds and "SUMMARY" not in kinds

    # Reconciliation classifies every action against live filesystem truth.
    assessment = assess_operation(journal, fs)
    assert assessment is not None and assessment.interrupted
    classes = [action.classification for action in assessment.actions]
    # b committed (destination only); a/c never moved (source only).
    assert all(c is RecoveryClass.SAFE_TO_COMPLETE for c in classes)

    before = _tree(root)
    assert main(["recover"]) == 0
    out = capsys.readouterr().out
    assert op in out
    assert "Incomplete operations" in out or "SAFE_TO_COMPLETE" in out
    assert _tree(root) == before  # recovery reports; it does not mutate


def test_recovery_scan_and_cli_are_idempotent(world, capsys):
    root, state_dir, fs = world
    op = new_operation_id()
    (root / "solo.txt").write_text("keep")
    plan = _plan(root, [(root / "solo.txt", root / "kept" / "solo.txt")])

    def crashing_move(src, dst):
        raise RuntimeError("crash before first move")

    fs.move = crashing_move
    with pytest.raises(RuntimeError):
        Executor(fs, state_dir).execute(plan, operation_id=op)

    pending = pending_recoveries(state_dir, fs)
    assert len(pending) == 1
    again = pending_recoveries(state_dir, fs)
    assert len(again) == 1  # detection itself changes nothing

    first_tree = _tree(root)
    assert main(["recover"]) == 0
    capsys.readouterr()
    second_tree = _tree(root)
    assert first_tree == second_tree
    assert (root / "solo.txt").read_text() == "keep"

    assert main(["recover"]) == 0  # repeated runs stay safe and stable


def test_completed_operations_are_not_flagged_for_recovery(world):
    root, state_dir, fs = world
    op = new_operation_id()
    (root / "done.txt").write_text("x")
    Executor(fs, state_dir).execute(
        _plan(root, [(root / "done.txt", root / "out" / "done.txt")]),
        operation_id=op,
    )
    assert pending_recoveries(state_dir, fs) == []
