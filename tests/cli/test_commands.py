"""CLI contract suite: exit codes, JSON schemas, safety behavior.

Runs the real argparse entry point (sfo.cli.app.main) in-process against a
fully isolated XDG environment, so no developer state is ever touched.
Interactive prompts are avoided by using --yes / --dry-run / --json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from sfo.cli.app import main


_OP_ID = re.compile(r"SFO-\d{4}-[0-9a-f]+")


def _latest_operation(capsys) -> str:
    """Operation ids are minted inside the session; expose them via undo --list."""
    assert main(["undo", "--list"]) == 0
    out = capsys.readouterr().out
    ids = _OP_ID.findall(out)
    assert ids, f"no operation id found in: {out!r}"
    return ids[0]


PDF_BYTES = b"%PDF-1.4\n% synthetic document for SFO tests\n" + b"x" * 200


@pytest.fixture()
def cli_env(tmp_path: Path, monkeypatch) -> SimpleNamespace:
    home = tmp_path / "home"
    config = tmp_path / "xdg-config"
    state = tmp_path / "xdg-state"
    cache = tmp_path / "xdg-cache"
    for directory in (home, config, state, cache):
        directory.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))

    root = tmp_path / "Downloads"
    (root / "Course Material").mkdir(parents=True)
    (root / "physics_notes.pdf").write_bytes(PDF_BYTES)
    (root / "photo.JPG").write_bytes(b"\xff\xd8\xff\xe0" + b"y" * 120)
    (root / "unknown.xyz").write_text("mystery")
    (root / ".hidden.cfg").write_text("h=1")
    (root / "résumé.txt").write_text("unicode name")
    (root / "copy_a.txt").write_text("same content here")
    (root / "copy_b.txt").write_text("same content here")
    return SimpleNamespace(root=root, config=config, state=state)


def _run_json(capsys, *argv: str) -> tuple[int, dict]:
    code = main(list(argv))
    captured = capsys.readouterr()
    assert code == 0, f"exit={code} stdout={captured.out!r} stderr={captured.err!r}"
    return code, json.loads(captured.out)


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }


# ---------------------------------------------------------------------------
# argument handling


def test_version_flag_reports_version(cli_env, capsys):
    from sfo import __version__

    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help(cli_env, capsys):
    assert main([]) == 0
    assert "organize" in capsys.readouterr().out


def test_unknown_command_is_usage_error(cli_env):
    with pytest.raises(SystemExit) as exc:
        main(["frobnicate"])
    assert exc.value.code == 2


def test_missing_required_argument_is_usage_error(cli_env):
    with pytest.raises(SystemExit) as exc:
        main(["duplicates"])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# preview


def test_preview_json_contract_and_read_only(cli_env, capsys):
    before = _tree_snapshot(cli_env.root)
    code, payload = _run_json(capsys, "preview", str(cli_env.root), "--json")

    assert code == 0
    assert payload["root"] == str(cli_env.root)
    stats = payload["statistics"]
    assert set(stats) == {
        "total_files",
        "moves",
        "unchanged",
        "skipped",
        "conflicts",
        "protected",
        "uncertain",
        "directories_created",
    }
    assert stats["moves"] > 0
    assert stats["total_files"] >= stats["moves"]
    for move in payload["moves"]:
        assert set(move) >= {"source_rel", "destination_rel", "confidence"}
        # every planned destination stays inside the root: containment proof
        assert not Path(move["destination_rel"]).is_absolute()
        assert ".." not in Path(move["destination_rel"]).parts
    assert _tree_snapshot(cli_env.root) == before  # read-only proof


def test_preview_on_empty_folder_plans_nothing(cli_env, capsys):
    empty = cli_env.root / "empty-dir"
    empty.mkdir()
    code, payload = _run_json(capsys, "preview", str(empty), "--json")
    assert code == 0
    assert payload["statistics"]["moves"] == 0


# ---------------------------------------------------------------------------
# organize / undo / history lifecycle


def test_organize_executes_moves_and_is_idempotent(cli_env, capsys):
    before = _tree_snapshot(cli_env.root)

    code, payload = _run_json(capsys, "organize", str(cli_env.root), "--yes", "--json")
    assert code == 0
    moved = payload["statistics"]["moves"]
    assert moved > 0
    after = _tree_snapshot(cli_env.root)
    assert len(after) == len(before)  # nothing lost
    assert after != before  # something actually moved

    # Repeat runs must CONVERGE: move counts never increase and reach a
    # stable zero (duplicate splitting can take more than one pass).
    counts = [moved]
    for _ in range(4):
        code, payload = _run_json(capsys, "organize", str(cli_env.root), "--yes", "--json")
        assert code == 0
        n = payload["statistics"]["moves"]
        assert n <= counts[-1], f"move count increased across runs: {counts + [n]}"
        counts.append(n)
        if n == 0:
            break
    assert counts[-1] == 0, f"did not converge within 5 runs: {counts}"

    # Fixpoint: one further run still finds nothing to do.
    code, final = _run_json(capsys, "organize", str(cli_env.root), "--yes", "--json")
    assert code == 0
    assert final["statistics"]["moves"] == 0


def test_undo_cli_restores_original_tree(cli_env, capsys):
    before = _tree_snapshot(cli_env.root)
    code, payload = _run_json(capsys, "organize", str(cli_env.root), "--yes", "--json")
    assert payload["statistics"]["moves"] > 0
    operation_id = _latest_operation(capsys)

    assert main(["undo", "--yes"]) == 0
    capsys.readouterr()
    assert _tree_snapshot(cli_env.root) == before

    assert main(["undo", "--list"]) == 0
    out = capsys.readouterr().out
    assert operation_id in out
    assert "undone" in out.lower()


def test_history_records_operation(cli_env, capsys):
    code, payload = _run_json(capsys, "organize", str(cli_env.root), "--yes", "--json")
    operation_id = _latest_operation(capsys)

    assert main(["history"]) == 0
    out = capsys.readouterr().out
    assert operation_id in out
    assert "ORGANIZE" in out.upper()


# ---------------------------------------------------------------------------
# hostile configuration through the CLI


def test_hostile_rules_cannot_influence_plan(cli_env, capsys):
    rules_file = cli_env.config / "sfo" / "rules.toml"
    rules_file.parent.mkdir(parents=True)
    # A well-formed TOML file whose destination escapes the root.
    rules_file.write_text(
        "config_version = 1\n"
        "[[rules]]\n"
        'id = "R-EVIL"\n'
        'name = "escape"\n'
        "priority = 99\n"
        'action = "prefer_directory"\n'
        'destination = "../../outside"\n'
        'conditions = [{ field = "filename", operator = "contains", value = "." }]\n',
        encoding="utf-8",
    )

    assert main(["preview", str(cli_env.root), "--json"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)  # stdout stayed pure JSON despite rejection
    for move in payload["moves"]:
        dest = Path(move["destination_rel"])
        assert not dest.is_absolute() and ".." not in dest.parts
        assert "outside" not in dest.as_posix()
    assert "R-EVIL" in captured.err  # the problem was reported, on stderr

    # A syntactically broken rules file must not crash planning either.
    rules_file.write_text("not toml at all [[[")
    code, payload = _run_json(capsys, "preview", str(cli_env.root), "--json")
    assert code == 0
    assert payload["statistics"]["total_files"] > 0


# ---------------------------------------------------------------------------
# read-only analysis commands


def test_duplicates_json_schema_and_read_only(cli_env, capsys):
    target = cli_env.root / "dups"
    target.mkdir()
    (target / "x.txt").write_text("A" * 300)
    (target / "y.txt").write_text("A" * 300)
    (target / "z.txt").write_text("B" * 50)

    mtimes_before = {p: p.stat().st_mtime_ns for p in target.rglob("*")}
    code, payload = _run_json(capsys, "duplicates", str(target), "--json")
    assert code == 0
    assert payload["scanned_files"] == 3
    assert payload["incomplete"] is False
    groups = [g for g in payload["groups"] if g["kind"] == "CONFIRMED"]
    assert len(groups) == 1
    group = groups[0]
    assert group["group_id"] == "DUP-0001"
    assert {Path(f["path"]).name for f in group["files"]} == {"x.txt", "y.txt"}
    assert group["redundant_bytes"] == 300
    for path, mtime in mtimes_before.items():
        assert path.stat().st_mtime_ns == mtime  # read-only proof


def test_inspect_json_contract(cli_env, capsys):
    pdf = cli_env.root / "physics_notes.pdf"
    code, payload = _run_json(capsys, "inspect", str(pdf), "--hash", "--json")
    assert code == 0
    assert payload["schema_version"] == 1
    assert payload["path"] == str(pdf)
    sniffed = payload["type"]
    assert sniffed["detected"] == sniffed["declared"]
    assert "PDF" in sniffed["declared"].upper()
    assert sniffed["mismatch"] is False
    assert len(payload["hash_sha256"]) == 64


def test_inspect_missing_file_fails_cleanly(cli_env, capsys):
    ghost = cli_env.root / "ghost.txt"
    assert main(["inspect", str(ghost), "--json"]) == 1
    out = capsys.readouterr().out
    assert str(ghost) in out
    assert "No such file or folder" in out


# ---------------------------------------------------------------------------
# informational commands on a pristine isolated installation


@pytest.mark.parametrize(
    "command",
    [
        ("status",),
        ("doctor",),
        ("config",),
        ("recover",),
        ("protected",),
        ("ignored",),
        ("diagnostics", "--summary"),
    ],
)
def test_informational_commands_succeed_on_clean_install(cli_env, capsys, command):
    assert main(list(command)) == 0
    assert capsys.readouterr().out  # produces human-readable output


def test_protect_unprotect_roundtrip(cli_env, capsys):
    secret = cli_env.root / "invoice.pdf"

    assert main(["protect", str(secret)]) == 0
    capsys.readouterr()
    assert main(["protected"]) == 0
    assert "invoice.pdf" in capsys.readouterr().out

    # A protected source is never organized away.
    secret.write_bytes(PDF_BYTES)
    code, payload = _run_json(capsys, "preview", str(cli_env.root), "--json")
    sources = {move["source_rel"] for move in payload["moves"]}
    assert not any("invoice.pdf" in s for s in sources)

    assert main(["unprotect", str(secret)]) == 0
    capsys.readouterr()
    assert main(["protected"]) == 0
    assert "invoice.pdf" not in capsys.readouterr().out
