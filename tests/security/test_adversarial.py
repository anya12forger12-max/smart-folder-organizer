"""Adversarial security suite.

Every test here attacks an existing engine the way a hostile local
environment would: traversal destinations, wildcard tricks, symlinks
pointing out of the root, special files, races between plan and execute,
hostile filenames in journals, and direct journal tampering.

Expected outcome for every attack: safe refusal or correct containment -
never a mutation outside policy, never a crash leaking past SfoError.
"""

from __future__ import annotations

import json
import os
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
from sfo.domain.identity import FileIdentity
from sfo.errors import DestinationExistsError, JournalError, SfoError
from sfo.infrastructure.filesystem.linux import LinuxFileSystem
from sfo.execution.engine import Executor, new_operation_id
from sfo.execution.journal import load_journal
from sfo.planning.validation import require_valid
from sfo.rules.engine import first_matching_rule
from sfo.rules.matcher import matches
from sfo.rules.models import (
    Condition,
    OrganizationRule,
    RuleAction,
    RuleContext,
    RuleField,
    RuleOperator,
)
from sfo.rules.validator import validate_rules
from sfo.scanning.scanner import Scanner
from sfo.undo.service import UndoService


# ---------------------------------------------------------------------------
# helpers


def _rule(destination: str, rule_id: str = "R-ATTACK") -> OrganizationRule:
    return OrganizationRule(
        id=rule_id,
        name="attack",
        priority=10,
        action=RuleAction.PREFER_DIRECTORY,
        conditions=(Condition(field=RuleField.FILENAME,
                              operator=RuleOperator.CONTAINS, value="x"),),
        destination=destination,
        enabled=True,
    )


def _context(filename: str) -> RuleContext:
    from sfo.domain.records import FileRecord
    from sfo.domain.fs_types import FileType

    return RuleContext(
        record=FileRecord(
            absolute_path=Path(f"/tmp/{filename}"),
            relative_path=Path(filename),
            name=filename,
            extension=Path(filename).suffix.lower(),
            size=10,
            modified_at=0.0,
            created_at=None,
            accessed_at=None,
            file_type=FileType.REGULAR_FILE,
            hidden=False,
            symlink_target=None,
            mode=None,
            identity=None,
        ),
        project_name=None,
        topic_name=None,
        is_duplicate=False,
        relative_path_posix=filename,
    )


def _identity(path: Path) -> FileIdentity:
    return FileIdentity.from_stat(os.lstat(path))


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
            total_files=len(moves), moves=len(moves), unchanged=0,
            skipped=0, conflicts=0, protected=0, uncertain=0,
            directories_created=0,
        ),
        actions=tuple(moves),
        directory_creations=(),
        warnings=(),
    )


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


def _run(world, pairs) -> str:
    """Execute a real transaction and return its operation id."""
    root, paths, fs = world
    op = new_operation_id()
    Executor(fs, paths.data_dir).execute(_plan(root, pairs), operation_id=op)
    return op


# ---------------------------------------------------------------------------
# 1. hostile rule configuration


@pytest.mark.parametrize("destination", [
    "../escape",
    "/etc/passwd",
    "a/../../b",
    "~/secrets",
    "School/Physics; rm -rf /",
    "$(whoami)",
    "ok\n../evil",
])
def test_rule_destination_attacks_are_rejected(destination):
    assert validate_rules([_rule(destination)]), f"accepted: {destination!r}"


def test_glob_characters_match_literally_not_as_wildcards():
    ctx = _context("notes.pdf")
    assert not matches(Condition(field=RuleField.FILENAME,
                                 operator=RuleOperator.ENDS_WITH, value="*.pdf"), ctx)


def test_matcher_survives_control_character_filenames():
    ctx = _context("bad\x1b[31mname\ninjected.pdf")
    rule = _rule("School/X")
    decision = first_matching_rule([rule], ctx)
    # The hostile name simply does not contain 'x'; matcher must not raise
    # and must not match.
    assert decision is None


# ---------------------------------------------------------------------------
# 2. filesystem boundary attacks


def test_scanner_never_follows_symlinks_out_of_root(world, tmp_path):
    root, _paths, fs = world
    (root / "real.txt").write_text("keep")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("must not be touched")
    os.symlink(outside, root / "linkdir")

    result = Scanner(fs).scan(root)

    seen = {str(r.absolute_path) for r in result.iter_all()}
    assert any("real.txt" in p for p in seen)
    # Nothing outside the root was ever enumerated - the escape attempt is
    # surfaced as an error instead of being silently followed.
    assert not any("secret" in p for p in seen), seen
    assert len(result.symlinks) == 0
    assert any(
        "linkdir" in str(err.path) and "escaped root" in err.message
        for err in result.errors
    )


def test_fifo_is_counted_never_read(world):
    root, _paths, fs = world
    os.mkfifo(root / "pipe.fifo")  # opening this for reading would hang

    result = Scanner(fs).scan(root)  # must complete without blocking

    planned_paths = {str(r.absolute_path) for r in result.files}
    assert not any("pipe.fifo" in p for p in planned_paths)
    assert result.statistics.special >= 1


def test_toctou_source_swapped_for_symlink_after_planning(world):
    root, _paths, fs = world
    target = root / "a.txt"
    target.write_text("A")
    (root / "dest").mkdir()
    plan = _plan(root, [(target, root / "dest" / "a.txt")])

    # Attacker swaps the file between planning and execution.
    target.unlink()
    os.symlink("/etc/passwd", target)

    with pytest.raises(SfoError):
        require_valid(plan, fs, __import__("sfo.domain.rules", fromlist=["RuleSet"]).RuleSet.EMPTY)


def test_forward_collision_with_existing_file_refused(world):
    root, paths, fs = world
    (root / "a.txt").write_text("A")
    (root / "dest").mkdir()
    (root / "dest" / "a.txt").write_text("PRECIOUS EXISTING DATA")

    with pytest.raises(DestinationExistsError):
        Executor(fs, paths.data_dir).execute(
            _plan(root, [(root / "a.txt", root / "dest" / "a.txt")])
        )

    assert (root / "dest" / "a.txt").read_text() == "PRECIOUS EXISTING DATA"
    assert (root / "a.txt").read_text() == "A"


# ---------------------------------------------------------------------------
# 3. journal integrity under attack


HOSTILE_NAME = 'weird\nFAKE ERROR "quoted" \\..\\evil.txt'


def test_journal_stays_parseable_and_undo_works_with_hostile_filename(world):
    root, paths, fs = world
    source = root / HOSTILE_NAME
    source.write_text("content")
    op = _run(world, [(source, root / "kept" / HOSTILE_NAME)])

    raw = (paths.journal_dir / f"{op}.jsonl").read_text(encoding="utf-8")
    for line in raw.splitlines():  # every line stays one valid JSON object
        json.loads(line)

    undo = UndoService(fs, paths)
    undone = undo.execute_undo(op)
    assert undone.failed == 0
    restored = root / HOSTILE_NAME
    assert restored.read_text() == "content"


def test_tampered_journal_destination_outside_root_refused(world, tmp_path):
    root, paths, fs = world
    source = root / "report.txt"
    source.write_text("data")
    op = _run(world, [(source, root / "archived" / "report.txt")])

    journal = paths.journal_dir / f"{op}.jsonl"
    lines = [json.loads(line) for line in journal.read_text().splitlines()]
    forged = []
    for entry in lines:
        if entry.get("kind") == "ACTION" and entry.get("state") == "VERIFIED":
            entry["destination"] = str(tmp_path / "stolen-location.txt")
        forged.append(json.dumps(entry))
    journal.write_text("\n".join(forged) + "\n", encoding="utf-8")

    with pytest.raises(SfoError):
        UndoService(fs, paths).execute_undo(op)

    assert not (tmp_path / "stolen-location.txt").exists()
    assert (root / "archived" / "report.txt").exists()


def test_corrupt_midjournal_line_refuses_undo(world):
    root, paths, fs = world
    (root / "one.txt").write_text("1")
    (root / "two.txt").write_text("2")
    op = _run(world, [
        (root / "one.txt", root / "m1.txt"),
        (root / "two.txt", root / "m2.txt"),
    ])
    journal = paths.journal_dir / f"{op}.jsonl"
    lines = journal.read_text().splitlines()
    lines.insert(len(lines) // 2, '{"kind":"ACTION","state":"VERIFIED"')  # torn
    journal.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(JournalError):
        load_journal(journal)


def test_torn_final_line_from_crash_is_tolerated(world):
    root, paths, fs = world
    (root / "one.txt").write_text("1")
    op = _run(world, [(root / "one.txt", root / "m1.txt")])
    journal = paths.journal_dir / f"{op}.jsonl"
    with open(journal, "a", encoding="utf-8") as fh:
        fh.write('{"kind":"ACTION","sta')  # crash mid-append

    entries = load_journal(journal)  # completed moves remain usable
    assert entries

    undone = UndoService(fs, paths).execute_undo(op)
    assert undone.failed == 0
    assert (root / "one.txt").read_text() == "1"


def test_unknown_journal_state_value_refused(world):
    root, paths, fs = world
    (root / "one.txt").write_text("1")
    op = _run(world, [(root / "one.txt", root / "m1.txt")])
    journal = paths.journal_dir / f"{op}.jsonl"
    lines = [json.loads(line) for line in journal.read_text().splitlines()]
    for entry in lines:
        if entry.get("kind") == "ACTION":
            entry["state"] = "GRANTED_BY_ADMIN"
    journal.write_text("\n".join(json.dumps(e) for e in lines) + "\n",
                       encoding="utf-8")

    with pytest.raises(JournalError):
        load_journal(journal)


# ---------------------------------------------------------------------------
# 8. plan containment (independent of the planning suite)


def test_plan_destination_outside_root_refused(world):
    from sfo.domain.rules import RuleSet
    from sfo.planning.validation import validate_plan

    root, _paths, fs = world
    (root / "victim.txt").write_text("data")
    plan = _plan(root, [(root / "victim.txt", root.parent / "stolen.txt")])

    result = validate_plan(plan, fs, RuleSet.EMPTY)
    assert not result.valid
    assert any("outside root" in p for p in result.problems)

    # And execution behind require_valid refuses too; nothing is stolen.
    with pytest.raises(SfoError):
        require_valid(plan, fs, RuleSet.EMPTY)
    assert not (root.parent / "stolen.txt").exists()
    assert (root / "victim.txt").exists()


def test_plan_source_inside_other_actions_moved_directory_refused(world):
    from sfo.domain.rules import RuleSet
    from sfo.planning.validation import validate_plan

    root, _paths, fs = world
    folder = root / "batch"
    folder.mkdir()
    (folder / "inner.txt").write_text("x")
    loose = root / "loose.txt"
    loose.write_text("y")

    # Action 2's source lives inside the directory action 1 moves away.
    plan = _plan(root, [
        (folder, root / "moved-batch"),
        (folder / "inner.txt", root / "unpacked.txt"),
    ])

    result = validate_plan(plan, fs, RuleSet.EMPTY)
    assert not result.valid
    assert not (root / "unpacked.txt").exists()
    assert loose.exists()
