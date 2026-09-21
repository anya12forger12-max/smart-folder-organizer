"""Rule engine tests: deterministic priority-ordered matching."""

from __future__ import annotations

from pathlib import Path

from sfo.domain.records import FileRecord
from sfo.domain.fs_types import FileType
from sfo.rules.engine import detect_conflicts, evaluate_rules, first_matching_rule
from sfo.rules.models import (
    Condition,
    OrganizationRule,
    RuleAction,
    RuleContext,
    RuleField,
    RuleOperator,
)


def _rule(
    rule_id,
    priority,
    value="physics",
    destination="School/Physics",
    enabled=True,
    field=RuleField.FILENAME,
    operator=RuleOperator.CONTAINS,
):
    return OrganizationRule(
        id=rule_id,
        name=f"rule {rule_id}",
        priority=priority,
        action=RuleAction.PREFER_DIRECTORY,
        conditions=(Condition(field=field, operator=operator, value=value),),
        destination=destination,
        enabled=enabled,
    )


def _context(filename: str = "physics_notes.pdf", project=None) -> RuleContext:
    record = FileRecord(
        absolute_path=Path(f"/tmp/{filename}"),
        relative_path=Path(filename),
        name=filename,
        extension=Path(filename).suffix.lower(),
        size=100,
        modified_at=0.0,
        created_at=None,
        accessed_at=None,
        file_type=FileType.REGULAR_FILE,
        hidden=False,
        symlink_target=None,
        mode=None,
        identity=None,
    )
    return RuleContext(
        record=record,
        project_name=project,
        topic_name=None,
        is_duplicate=False,
        relative_path_posix=filename,
    )


def test_higher_priority_wins_deterministically():
    generic = _rule("R-1", 10)
    specific = _rule("R-2", 50)
    hits = evaluate_rules([generic, specific], _context())
    assert [rule.id for rule, _ in hits] == ["R-2", "R-1"]
    assert first_matching_rule([generic, specific], _context())[0].id == "R-2"


def test_ties_keep_declaration_order():
    a = _rule("R-A", 10)
    b = _rule("R-B", 10)
    hits = evaluate_rules([a, b], _context())
    assert [rule.id for rule, _ in hits] == ["R-A", "R-B"]


def test_disabled_rules_never_match():
    disabled = _rule("R-D", 99, enabled=False)
    assert evaluate_rules([disabled], _context()) == []
    assert first_matching_rule([disabled], _context()) is None


def test_non_matching_conditions_return_empty():
    rule = _rule("R-1", 10, value="chemistry")
    assert evaluate_rules([rule], _context()) == []


def test_identical_conflicting_rules_are_reported():
    a = _rule("R-1", 10)
    b = _rule("R-2", 10, destination="Elsewhere")
    problems = detect_conflicts([a, b])
    assert len(problems) == 1
    assert "R-1" in problems[0] and "R-2" in problems[0]


def test_same_destination_conflicts_are_not_flagged():
    a = _rule("R-1", 10)
    b = _rule("R-2", 10)
    assert detect_conflicts([a, b]) == []


def test_different_priorities_do_not_conflict():
    a = _rule("R-1", 10)
    b = _rule("R-2", 20, destination="Elsewhere")
    assert detect_conflicts([a, b]) == []


def test_extension_operator_matches_case_insensitively():
    rule = _rule(
        "R-PDF",
        30,
        value=".pdf",
        operator=RuleOperator.EQUALS,
        field=RuleField.EXTENSION,
        destination="Documents",
    )
    decision = first_matching_rule([rule], _context(filename="Report.PDF"))
    assert decision is not None
    assert decision[0].destination == "Documents"
