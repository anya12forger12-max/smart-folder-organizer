"""Observability contract: crash records, correlation ids, private storage.

SFO has no logging framework by design. The durable diagnostic surface is:
journals (JSONL), the history database, and bounded local crash records.
These tests pin that surface down.
"""

from __future__ import annotations

import json
import re
import stat

from sfo import __version__
from sfo.cli import commands
from sfo.cli.app import main
from sfo.cli.crash import recent_crashes, record_crash
from sfo.config.paths import AppPaths
from sfo.persistence.database import Database


_OP_ID = re.compile(r"SFO-\d{4}-[0-9a-f]+")


def test_unexpected_error_writes_local_crash_record(iso_env, monkeypatch, capsys):
    def boom(args, style):
        raise RuntimeError("boom-canary")

    monkeypatch.setattr(commands, "cmd_status", boom)
    assert main(["status"]) == 1

    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert "Diagnostic record" in err

    records = recent_crashes(AppPaths.default().data_dir)
    assert len(records) == 1
    mode = stat.S_IMODE(records[0].stat().st_mode)
    assert mode == 0o600  # crash records hold argv: always private
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["exception_type"] == "RuntimeError"
    assert "boom-canary" in record["message"]
    assert record["version"] == __version__
    assert isinstance(record["argv"], list)


def test_crash_records_are_bounded(iso_env):
    state = AppPaths.default().data_dir
    for i in range(12):
        record_crash(state, [f"call-{i}"], RuntimeError(f"e{i}"))
    records = recent_crashes(state)
    assert len(records) == 10  # newest kept only


def test_hostile_argv_stays_valid_json(iso_env):
    state = AppPaths.default().data_dir
    path = record_crash(state, ["--name", "bad\nnewline\x07bell"], RuntimeError("x"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["argv"][1] == "bad\nnewline\x07bell"


def test_diagnostic_failure_does_not_mask_exit_code(iso_env, monkeypatch, capsys):
    def broken_record(state_dir, argv, exc):
        raise OSError("simulated unwritable diagnostics")

    def real_failure(args, style):
        raise ValueError("real failure")

    monkeypatch.setattr(commands, "cmd_status", real_failure)
    import sfo.cli.crash as crash_module

    monkeypatch.setattr(crash_module, "record_crash", broken_record)
    code = main(["status"])
    assert code == 1
    err = capsys.readouterr().err
    assert "Unexpected error (ValueError)" in err
    assert "Diagnostic record" not in err


def test_operation_id_correlates_journal_database_and_cli(iso_env, capsys):
    root = iso_env.root
    (root / "report.pdf").write_bytes(b"%PDF-1.4 " + b"x" * 100)
    (root / "notes.txt").write_text("hello")

    assert main(["organize", str(root), "--yes"]) == 0
    capsys.readouterr()
    assert main(["undo", "--list"]) == 0
    out = capsys.readouterr().out
    op_ids = _OP_ID.findall(out)
    assert op_ids, f"no operation id in undo listing: {out!r}"
    operation_id = op_ids[0]

    paths = AppPaths.default()
    journal = paths.journal_dir / f"{operation_id}.jsonl"
    assert journal.exists(), "journal file must carry the same operation id"

    rows = Database(paths.database_path).list_transactions(limit=10)
    assert any(row["operation_id"] == operation_id for row in rows), (
        "history row must reference the same operation id"
    )


def test_history_database_is_always_private(iso_env, capsys):
    root = iso_env.root
    (root / "a.txt").write_text("data")
    assert main(["organize", str(root), "--yes"]) == 0
    capsys.readouterr()

    db_path = AppPaths.default().database_path
    mode = stat.S_IMODE(db_path.stat().st_mode)
    assert mode == 0o600, f"history db must be 0600, got {oct(mode)}"


def test_doctor_reports_healthy_install(iso_env, capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "[ok]" in out
    assert "interrupted" in out  # recovery check present


def test_doctor_detects_corrupt_database(iso_env, capsys):
    paths = AppPaths.default().ensure()
    db_path = paths.database_path
    db_path.write_bytes(b"this is not a sqlite database at all" * 20)

    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "history database error" in out
