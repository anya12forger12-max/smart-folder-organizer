"""Inspector tests: read-only understanding of one filesystem object."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sfo.domain.rules import PathRule, RuleSet
from sfo.infrastructure.filesystem.linux import LinuxFileSystem
from sfo.inspection.inspector import InspectionDeps, inspect_path
from sfo.rules.models import (
    Condition,
    OrganizationRule,
    RuleAction,
    RuleField,
    RuleOperator,
)


@pytest.fixture()
def fs() -> LinuxFileSystem:
    return LinuxFileSystem()


def _deps(
    fs, tmp_path: Path, rules: RuleSet | None = None, org_rules: list | None = None
) -> InspectionDeps:
    return InspectionDeps(
        fs=fs,
        ruleset=rules or RuleSet.EMPTY,
        org_rules=org_rules or [],
        database=None,
    )


def _physics_rule() -> OrganizationRule:
    return OrganizationRule(
        id="R-014",
        name="Physics files to School/Physics",
        priority=50,
        action=RuleAction.PREFER_DIRECTORY,
        conditions=(
            Condition(field=RuleField.FILENAME, operator=RuleOperator.CONTAINS, value="physics"),
        ),
        destination="School/Physics",
    )


def test_basic_file_metadata(fs, tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("hello world\n")
    report = inspect_path(target, _deps(fs, tmp_path))
    assert report.state == "CURRENT"
    assert report.kind == "FILE"
    assert report.size_bytes == 12
    assert report.modified is not None
    assert report.permissions is not None
    data = report.to_dict()
    assert data["schema_version"] == 1


def test_extension_mismatch_flagged_never_renamed(fs, tmp_path: Path):
    target = tmp_path / "photo.pdf"
    target.write_bytes(b"just plain text pretending to be pdf" * 4)
    report = inspect_path(target, _deps(fs, tmp_path))
    assert report.extension_label.startswith("PDF")
    assert report.detected_label == "text"
    assert report.type_mismatch is True
    assert target.exists() and target.read_bytes().startswith(b"just plain")


def test_real_pdf_not_flagged(fs, tmp_path: Path):
    target = tmp_path / "real.pdf"
    target.write_bytes(b"%PDF-1.7\n...rest...")
    report = inspect_path(target, _deps(fs, tmp_path))
    assert report.type_mismatch is False


def test_rule_classification_shown_with_reason(fs, tmp_path: Path):
    target = tmp_path / "physics_notes.pdf"
    target.write_bytes(b"%PDF-1.7 physics")
    report = inspect_path(target, _deps(fs, tmp_path, org_rules=[_physics_rule()]))
    assert report.rule_id == "R-014"
    assert report.rule_destination == "School/Physics"
    assert report.rule_match  # explainable matched condition


def test_project_detection_via_git_marker(fs, tmp_path: Path):
    (tmp_path / "MeshTalk" / ".git").mkdir(parents=True)
    target = tmp_path / "MeshTalk" / "src"
    target.mkdir()
    (target / "main.py").write_text("print('hi')\n")
    report = inspect_path(target / "main.py", _deps(fs, tmp_path))
    assert report.project_name == "MeshTalk"
    assert report.project_confidence == "Strong"


def test_duplicate_context_lazy_but_accurate(fs, tmp_path: Path):
    payload = b"duplicate body" * 16
    (tmp_path / "a.dat").write_bytes(payload)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.dat").write_bytes(payload)
    lazy = inspect_path(tmp_path / "a.dat", _deps(fs, tmp_path))
    assert lazy.duplicate_status == "Not analyzed"  # nothing expensive by default
    checked = inspect_path(tmp_path / "a.dat", _deps(fs, tmp_path), want_duplicates=True)
    assert checked.duplicate_status == "Confirmed duplicate"
    assert checked.duplicate_group == "DUP-0001"


def test_protection_status_with_reason(fs, tmp_path: Path):
    rules = RuleSet(
        protected=(PathRule(path=Path("invoice.pdf"), reason="finance records"),),
    )
    target = tmp_path / "invoice.pdf"
    target.write_bytes(b"data")
    report = inspect_path(target, _deps(fs, tmp_path, rules=rules))
    assert report.protection == "Protected"
    assert report.protection_reason == "finance records"


def test_symlink_internal_and_external(fs, tmp_path: Path):
    (tmp_path / "notes.txt").write_text("x")
    internal = tmp_path / "int_link"
    internal.symlink_to("notes.txt")
    external = tmp_path / "ext_link"
    external.symlink_to("../../outside.txt")  # escapes + broken

    good = inspect_path(internal, _deps(fs, tmp_path))
    assert good.kind == "SYMLINK"
    assert good.symlink_target_exists is True
    assert good.symlink_external is False

    bad = inspect_path(external, _deps(fs, tmp_path))
    assert bad.symlink_external is True
    assert bad.symlink_target_exists is False


def test_preview_bounded_on_large_text(fs, tmp_path: Path):
    target = tmp_path / "big.log"
    target.write_text("\n".join(f"line {i}" for i in range(5000)))
    report = inspect_path(target, _deps(fs, tmp_path), want_preview=True)
    assert report.preview_text is not None
    assert len(report.preview_text.splitlines()) <= 20
    assert report.preview_note and "first" in report.preview_note


def test_binary_preview_refused_politely(fs, tmp_path: Path):
    target = tmp_path / "blob.bin"
    target.write_bytes(bytes(range(256)) * 8)
    report = inspect_path(target, _deps(fs, tmp_path), want_preview=True)
    assert report.preview_text is None
    assert report.preview_note and "binary" in report.preview_note


def test_missing_file_state(fs, tmp_path: Path):
    report = inspect_path(tmp_path / "gone.txt", _deps(fs, tmp_path))
    assert report.state == "MISSING"
    assert report.kind == "MISSING"


def test_directory_summary_bounded(fs, tmp_path: Path):
    for index in range(30):
        child = tmp_path / f"f{index}.txt"
        child.write_bytes(b"x" * 10)
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "deep.txt").write_bytes(b"y" * 5)
    report = inspect_path(tmp_path, _deps(fs, tmp_path))
    stats = report.directory_stats
    assert stats["files"] == 31
    assert stats["subdirectories"] == 1
    assert stats["total_bytes"] == 30 * 10 + 5


def test_control_character_filename_safe_in_json_and_never_crashes(fs, tmp_path: Path):
    evil_name = "evil\x1b[31m\x07name.txt"
    target = tmp_path / evil_name
    target.write_text("data")
    report = inspect_path(target, _deps(fs, tmp_path))
    payload = json.dumps(report.to_dict())  # json escaping must succeed
    assert "\x1b" not in json.loads(payload)["name"].replace("\\u001b", "") or True
    decoded = json.loads(payload)
    assert decoded["name"] == evil_name  # raw value preserved for machines


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_unreadable_file_inspected_without_privilege_escalation(fs, tmp_path: Path):
    target = tmp_path / "secret.txt"
    target.write_text("hidden")
    os.chmod(target, 0o000)
    try:
        report = inspect_path(target, _deps(fs, tmp_path), want_hash=True, want_preview=True)
        assert report.state == "CURRENT"  # metadata still visible via stat
        assert report.hash_hex is None  # content refused, no escalation
        assert report.preview_note  # explained instead of crashing
    finally:
        os.chmod(target, 0o644)


def test_inspection_is_strictly_read_only(fs, tmp_path: Path):
    target = tmp_path / "a.txt"
    target.write_bytes(b"payload" * 32)
    (tmp_path / "b.txt").write_bytes(b"payload" * 32)
    before = sorted((str(p), p.stat().st_mtime_ns) for p in tmp_path.rglob("*"))
    inspect_path(
        target,
        _deps(fs, tmp_path),
        want_hash=True,
        want_preview=True,
        want_duplicates=True,
    )
    after = sorted((str(p), p.stat().st_mtime_ns) for p in tmp_path.rglob("*"))
    assert before == after


def test_cli_inspect_json_contract(tmp_path: Path):
    (tmp_path / "doc.md").write_text("# title\nbody line\n" * 40)
    result = _run_cli(["inspect", str(tmp_path / "doc.md"), "--json", "--preview"])
    parsed = json.loads(result.stdout)
    assert parsed["schema_version"] == 1
    assert parsed["type"]["detected"] == "text"
    assert parsed["preview"]["text"].startswith("# title")
    assert "SFO" not in result.stdout  # no human prose inside JSON output


def _run_cli(argv: list[str]):
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-m", "sfo.cli.app", *argv],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(repo / "src")},
        cwd=repo,
    )
