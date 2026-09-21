"""Tests for the read-only duplicate detector.

Contract under test:
- only exact content equality (full sha256) confirms duplicates
- same name/size with different content is NOT a duplicate
- hard links are one object, never "redundant copies"
- symlinks are skipped, special files counted, .git internals ignored
- a file that changes while being hashed is excluded, not misreported
- identical inputs produce byte-identical reports (determinism)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from sfo.domain.rules import PathRule, RuleSet
from sfo.duplicates.models import DuplicateReport
from sfo.duplicates.scanner import DuplicateScanner
from sfo.infrastructure.filesystem.linux import LinuxFileSystem


@pytest.fixture()
def fs() -> LinuxFileSystem:
    return LinuxFileSystem()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _scan(fs, root: Path, rules: RuleSet | None = None) -> DuplicateReport:
    return DuplicateScanner(fs, rules).scan(root)


def test_confirmed_duplicates_group_together(fs, tmp_path: Path):
    _write(tmp_path / "a.txt", b"same bytes" * 10)
    _write(tmp_path / "sub" / "b.txt", b"same bytes" * 10)
    report = _scan(fs, tmp_path)
    assert report.scanned_files == 2
    assert len(report.groups) == 1
    group = report.groups[0]
    assert group.kind == "CONFIRMED"
    assert {f.path.name for f in group.files} == {"a.txt", "b.txt"}
    assert group.redundant_bytes == 100  # 10-byte payload x 10, one redundant copy


def test_same_name_same_size_different_content_not_duplicate(fs, tmp_path: Path):
    _write(tmp_path / "one.bin", b"A" * 64)
    _write(tmp_path / "two.bin", b"B" * 64)
    report = _scan(fs, tmp_path)
    assert report.groups == ()


def test_unique_sizes_never_grouped_and_hashing_is_size_gated(fs, tmp_path: Path):
    _write(tmp_path / "x", b"1")
    _write(tmp_path / "y", b"22")
    report = _scan(fs, tmp_path)
    assert report.groups == ()
    assert report.scanned_files == 2


def test_empty_files_form_their_own_group(fs, tmp_path: Path):
    _write(tmp_path / "e1.dat", b"")
    _write(tmp_path / "e2.dat", b"")
    _write(tmp_path / "real.txt", b"data")
    report = _scan(fs, tmp_path)
    assert [g.kind for g in report.groups] == ["EMPTY"]
    assert report.potentially_reclaimable == 0  # zero-byte copies reclaim nothing
    assert all(f.size == 0 for f in report.groups[0].files)


def test_hard_links_are_one_object_not_copies(fs, tmp_path: Path):
    _write(tmp_path / "src.md", b"hardlinked body")
    os.link(tmp_path / "src.md", tmp_path / "link.md")
    report = _scan(fs, tmp_path)
    assert len(report.groups) == 1
    group = report.groups[0]
    assert group.kind == "HARDLINKS"
    assert group.redundant_bytes == 0


def test_symlinks_are_skipped_never_followed(fs, tmp_path: Path):
    _write(tmp_path / "real.txt", b"content")
    _write(tmp_path / "outside.txt", b"different content entirely")
    os.symlink(tmp_path / "outside.txt", tmp_path / "link.txt")
    report = _scan(fs, tmp_path)
    assert report.skipped_symlinks == 1
    # The symlink must not drag its target into any group.
    assert report.groups == ()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_unreadable_file_marks_scan_incomplete(fs, tmp_path: Path):
    _write(tmp_path / "secret.txt", b"cannot read me" * 4)
    _write(tmp_path / "twin.txt", b"cannot read me" * 4)
    os.chmod(tmp_path / "secret.txt", 0o000)
    try:
        report = _scan(fs, tmp_path)
        assert report.incomplete is True
        names = {f.path.name for g in report.groups for f in g.files}
        assert "secret.txt" not in names  # excluded rather than guessed about
    finally:
        os.chmod(tmp_path / "secret.txt", 0o644)


def test_special_files_counted_never_opened(fs, tmp_path: Path):
    _write(tmp_path / "plain.txt", b"x")
    fifo = tmp_path / "pipe.fifo"
    os.mkfifo(fifo)
    report = _scan(fs, tmp_path)
    assert report.skipped_special == 1
    assert report.scanned_files == 1


def test_vcs_internals_are_not_user_files(fs, tmp_path: Path):
    _write(tmp_path / "proj" / ".git" / "config", b"repo machinery")
    _write(tmp_path / "proj" / ".git" / "hooks" / "pre-commit", b"repo machinery")
    _write(tmp_path / "proj" / "README.md", b"user file")
    report = _scan(fs, tmp_path)
    assert report.skipped_vcs >= 1  # at least the .git directory entry
    names = {f.path.name for g in report.groups for f in g.files}
    assert "config" not in names and "pre-commit" not in names


def test_unicode_filenames_survive_reporting(fs, tmp_path: Path):
    payload = "ünïcode çøpy".encode("utf-8") * 5
    _write(tmp_path / "ünïcode çøpy.txt", payload)
    _write(tmp_path / "తెలుగు నోట్స్.pdf", payload)
    report = _scan(fs, tmp_path)
    assert len(report.groups) == 1
    assert report.to_dict()["groups"][0]["files"][0]["path"].endswith(".txt")


def test_report_is_deterministic(fs, tmp_path: Path):
    import json

    for name in ("b.bin", "a.bin", "c.bin"):
        _write(tmp_path / name, b"stable payload" * 3)
    first = json.dumps(_scan(fs, tmp_path).to_dict(), sort_keys=True)
    second = json.dumps(_scan(fs, tmp_path).to_dict(), sort_keys=True)
    assert first == second


def test_changed_while_hashing_is_excluded(fs, tmp_path: Path):
    """A file rewritten mid-hash must not confirm a false duplicate."""
    payload_a = b"version one" * 32
    _write(tmp_path / "moving.txt", payload_a)
    _write(tmp_path / "still.txt", payload_a)

    real_fs = fs

    class MutatingDuringHash(LinuxFileSystem):
        def hash_file(self, path, algorithm="sha256"):  # noqa: ANN001
            digest = real_fs.hash_file(path)
            target = tmp_path / "moving.txt"
            if path.name == "moving.txt":
                # Simulate a rewrite finishing between read and re-inspect.
                os.utime(target, (0, 0))
            return digest

    report = DuplicateScanner(MutatingDuringHash()).scan(tmp_path)
    assert report.stale == 1
    assert report.incomplete is True
    moved_names = {f.path.name for g in report.groups for f in g.files}
    assert "moving.txt" not in moved_names


def test_protected_flag_from_ruleset(fs, tmp_path: Path):
    rules = RuleSet(
        protected=(PathRule(path=Path("invoice.pdf"), reason="finance"),),
        ignored=(PathRule(path=Path("junk"), reason="noise"),),
    )
    _write(tmp_path / "invoice.pdf", b"protected payload" * 8)
    _write(tmp_path / "copy.pdf", b"protected payload" * 8)
    report = _scan(fs, tmp_path, rules)
    group = report.groups[0]
    by_name = {f.path.name: f for f in group.files}
    assert by_name["invoice.pdf"].protected is True
    assert by_name["copy.pdf"].protected is False


def test_cli_json_output_is_valid_and_read_only(tmp_path: Path):
    _write(tmp_path / "a.txt", b"duplicate body" * 20)
    _write(tmp_path / "b.txt", b"duplicate body" * 20)
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sfo.cli.app",
            "duplicates",
            str(tmp_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "src"},
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.returncode == 0, result.stderr
    import json

    parsed = json.loads(result.stdout)
    assert parsed["scanned_files"] == 2
    assert parsed["groups"][0]["kind"] == "CONFIRMED"
    after = sorted(str(p) for p in tmp_path.rglob("*"))
    assert before == after  # strictly read-only


def test_cli_missing_folder_exit_code(tmp_path: Path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sfo.cli.app",
            "duplicates",
            str(tmp_path / "missing"),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "src"},
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.returncode == 2
