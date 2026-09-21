"""Plan validation tests: the last safety net before execution.

Every test here encodes one refusal reason. If any of these start passing
with a problem list, a safety guarantee has regressed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sfo.domain.confidence import Confidence
from sfo.domain.identity import FileIdentity
from sfo.domain.plan import (
    ActionStatus,
    OrganizationPlan,
    PlannedMove,
    PlanStatistics,
    Recommendation,
)
from sfo.domain.rules import PathRule, RuleSet
from sfo.errors import StalePlanError
from sfo.infrastructure.filesystem.linux import LinuxFileSystem
from sfo.planning.validation import require_valid, validate_plan


def _identity(path: Path) -> FileIdentity:
    return FileIdentity.from_stat(os.lstat(path))


def _move(
    action_id, source: Path, destination: Path, identity: FileIdentity | None = None
) -> PlannedMove:
    return PlannedMove(
        action_id=action_id,
        source=source,
        destination=destination,
        file_identity=identity if identity is not None else _identity(source),
        reason="test",
        reason_code="TEST",
        confidence=Confidence.HIGH,
        arrangement_value=Recommendation.RECOMMENDED,
        status=ActionStatus.MOVE,
    )


def _plan(root: Path, moves) -> OrganizationPlan:
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


@pytest.fixture()
def env(tmp_path: Path):
    (tmp_path / "a.txt").write_text("A")
    (tmp_path / "b.txt").write_text("B")
    (tmp_path / "dest").mkdir()
    return tmp_path, LinuxFileSystem()


def test_valid_plan_passes(env):
    root, fs = env
    result = validate_plan(
        _plan(root, [_move(1, root / "a.txt", root / "dest" / "a.txt")]), fs, RuleSet.EMPTY
    )
    assert result.valid


def test_missing_source_is_refused(env):
    root, fs = env
    ghost = root / "deleted.txt"
    plan = _plan(
        root,
        [
            PlannedMove(
                action_id=1,
                source=ghost,
                destination=root / "dest" / "x",
                file_identity=None,
                reason="t",
                reason_code="T",
                confidence=Confidence.HIGH,
                arrangement_value=Recommendation.RECOMMENDED,
                status=ActionStatus.MOVE,
            )
        ],
    )
    result = validate_plan(plan, fs, RuleSet.EMPTY)
    assert not result.valid and any("missing" in p for p in result.problems)


def test_changed_source_identity_is_refused(env):
    """The staleness guarantee: content changed after planning -> no move."""
    root, fs = env
    target = root / "a.txt"
    stale = _move(1, target, root / "dest" / "a.txt")
    os.utime(target, (0, 0))  # external modification after planning
    result = validate_plan(_plan(root, [stale]), fs, RuleSet.EMPTY)
    assert not result.valid and any("changed" in p for p in result.problems)


def test_destination_outside_root_is_refused(env, tmp_path_factory):
    root, fs = env
    outside = tmp_path_factory.mktemp("elsewhere")
    result = validate_plan(
        _plan(root, [_move(1, root / "a.txt", outside / "a.txt")]), fs, RuleSet.EMPTY
    )
    assert not result.valid and any("outside root" in p for p in result.problems)


def test_two_actions_one_destination_are_refused(env):
    root, fs = env
    dest = root / "dest" / "clash"
    result = validate_plan(
        _plan(
            root,
            [
                _move(1, root / "a.txt", dest),
                _move(2, root / "b.txt", dest),
            ],
        ),
        fs,
        RuleSet.EMPTY,
    )
    assert not result.valid and any("same destination" in p for p in result.problems)


def test_chained_moves_are_refused(env):
    """Moving a folder while also moving a file out of it would drag the
    file along; the second source vanishes mid-transaction."""
    root, fs = env
    (root / "bundle").mkdir()
    (root / "bundle" / "c.txt").write_text("C")
    result = validate_plan(
        _plan(
            root,
            [
                _move(1, root / "bundle", root / "dest" / "bundle"),
                _move(2, root / "bundle" / "c.txt", root / "elsewhere" / "c.txt"),
            ],
        ),
        fs,
        RuleSet.EMPTY,
    )
    assert not result.valid and any("chained move detected" in p for p in result.problems)


def test_protected_paths_are_refused_even_by_user_plans(env):
    root, fs = env
    rules = RuleSet(protected=(PathRule(path=Path("a.txt"), reason="keep"),))
    for target in ("source", "destination"):
        move = _move(1, root / "a.txt", root / "dest" / "a.txt")
        moves = (
            [move]
            if target == "source"
            else [
                PlannedMove(
                    action_id=1,
                    source=root / "b.txt",
                    destination=root / "a.txt",
                    file_identity=_identity(root / "b.txt"),
                    reason="t",
                    reason_code="T",
                    confidence=Confidence.HIGH,
                    arrangement_value=Recommendation.RECOMMENDED,
                    status=ActionStatus.MOVE,
                )
            ]
        )
        result = validate_plan(_plan(root, moves), fs, rules)
        assert not result.valid and any("protected" in p for p in result.problems)


def test_require_valid_raises_stale_plan(env):
    root, fs = env
    ghost = root / "ghost.txt"
    plan = _plan(
        root,
        [
            PlannedMove(
                action_id=1,
                source=ghost,
                destination=root / "dest" / "g",
                file_identity=None,
                reason="t",
                reason_code="T",
                confidence=Confidence.HIGH,
                arrangement_value=Recommendation.RECOMMENDED,
                status=ActionStatus.MOVE,
            )
        ],
    )
    with pytest.raises(StalePlanError):
        require_valid(plan, fs, RuleSet.EMPTY)


def test_validation_never_mutates(env):
    root, fs = env
    before = sorted(str(p) for p in root.rglob("*"))
    validate_plan(
        _plan(root, [_move(1, root / "a.txt", root / "dest" / "a.txt")]),
        fs,
        RuleSet.EMPTY,
    )
    assert sorted(str(p) for p in root.rglob("*")) == before
