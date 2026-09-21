"""Command handlers for the SFO CLI.

Every handler is a thin translation layer between parsed arguments and the
session/pipeline/services. Handlers never touch the filesystem directly:
organization goes through Session.run_pipeline + execute_plan (which lock,
preflight, journal and verify); configuration commands only rewrite SFO's
own config files.
"""

from __future__ import annotations

import json as jsonlib
import os
import sys
from datetime import datetime
from pathlib import Path

from sfo import __version__
from sfo.analysis.engine import AnalysisEngine
from sfo.cli.exit_codes import (
    GENERAL_FAILURE,
    PARTIAL,
    RECOVERY_REQUIRED,
    SUCCESS,
)
from sfo.cli.render import Style, confidence_label, rel_display, safe_text
from sfo.config.loader import config_locations, load_user_config
from sfo.config.paths import AppPaths
from sfo.errors import UsageError
from sfo.persistence.database import Database
from sfo.rules.matcher import describe
from sfo.rules.parser import load_rules as _load_rules_file
from sfo.rules.parser import save_rules
from sfo.rules.validator import validate_rules
from sfo.scanning.scanner import Scanner
from sfo.undo.service import UndoService

_CONFIRM_YES = ("y", "yes")


def cmd_organize(args, style: Style) -> int:  # noqa: ANN001
    session = _session(args)
    root = session.validate_root(args.folder)

    if not args.dry_run:
        pending = session.pending_recoveries()
        if pending:
            print("An incomplete transaction requires recovery.")
            for item in pending:
                print(f"  {getattr(item, 'operation_id', item)}")
            print("Run: sfo recover")
            return RECOVERY_REQUIRED

    artifacts = session.run_pipeline(
        root,
        progress=_progress_printer(args, style),
    )
    for problem in artifacts.rule_problems:
        print(style.yellow(f"rule problem: {safe_text(problem)}"), file=sys.stderr)

    if args.json:
        print(jsonlib.dumps(_plan_json(artifacts), indent=2))
    else:
        _render_preview(artifacts, style, details=getattr(args, "details", False) or args.verbose)

    if args.dry_run:
        print()
        print("Dry run complete. Nothing was changed.")
        return SUCCESS

    if not args.yes:
        if not sys.stdin.isatty():
            print()
            print("No interactive terminal detected; nothing was changed.")
            print("Use --yes to confirm a non-interactive organization.")
            return SUCCESS
        answer = input("\nConfirm? [y/N] ").strip().lower()
        if answer not in _CONFIRM_YES:
            print("Cancelled. No files were changed.")
            return SUCCESS

    result = session.execute_plan(artifacts)

    if not args.json:
        print()
        print(f"Operation: {result.operation_id}")
        print(f"Moved and verified: {result.moved}")
        if result.failed or result.status.value != "COMPLETED":
            print(f"Failed/skipped: {result.failed}")
            for failure in result.failures[:10]:
                print(f"  - {failure.message}")
        if result.status.value == "PARTIAL":
            print("Some operations did not complete. Run `sfo history` for details.")
        elif result.status.value != "COMPLETED":
            print("The operation did not complete. Run `sfo recover`.")
    return _exit_for(result)


def cmd_preview(args, style: Style) -> int:  # noqa: ANN001
    session = _session(args)
    root = session.validate_root(args.folder)
    artifacts = session.run_pipeline(root, progress=_progress_printer(args, style))
    for problem in artifacts.rule_problems:
        print(style.yellow(f"rule problem: {safe_text(problem)}"), file=sys.stderr)
    if args.json:
        print(jsonlib.dumps(_plan_json(artifacts), indent=2))
    else:
        _render_preview(artifacts, style, details=args.details or args.verbose)
    print("\nNothing has been changed." if not args.json else "", end="" if args.json else "\n")
    return SUCCESS


def cmd_undo(args, style: Style) -> int:  # noqa: ANN001
    session = _session(args)
    service = UndoService(session.fs, session.paths)

    if args.list_ops:
        candidates = service.list_candidates()
        if not candidates:
            print("No undoable transactions found.")
            return SUCCESS
        print("Undoable transactions:")
        for c in candidates:
            state = "already undone" if c.status == "undone" else f"{c.restorable} moves"
            print(f"  {c.operation_id}  root={c.root.name}  ({state})")
        return SUCCESS

    if args.operation:
        target_op = args.operation
        candidates = [c for c in service.list_candidates(limit=50) if c.operation_id == target_op]
        candidate = candidates[0] if candidates else None
    else:
        available = [c for c in service.list_candidates() if c.status == "available"]
        if not available:
            print("No undoable transactions found.")
            return SUCCESS
        candidate = available[0]
        target_op = candidate.operation_id

    if candidate is None:
        raise UsageError(f"unknown or non-undoable operation: {target_op}")
    if candidate.status == "undone":
        print(f"Operation {candidate.operation_id} has already been undone.")
        return SUCCESS
    if candidate.restorable == 0:
        print(
            f"Nothing to restore for {candidate.operation_id}: none of its "
            "recorded destinations exist anymore. The files have likely been "
            "moved again by a later organization run."
        )
        print("Run 'sfo undo --list' to see which transactions can still be reversed.")
        return SUCCESS

    print(f"Transaction {candidate.operation_id}")
    print(f"Root: {candidate.root}")
    print(f"Files that can be restored: {candidate.restorable}")
    print("SFO will move files back. It will not delete, overwrite, or modify file contents.")

    if not args.yes:
        if not sys.stdin.isatty():
            print("No interactive terminal; nothing was changed. Use --yes to confirm.")
            return SUCCESS
        answer = input("\nConfirm undo? [y/N] ").strip().lower()
        if answer not in _CONFIRM_YES:
            print("Cancelled. No files were changed.")
            return SUCCESS

    result = service.execute_undo(candidate.operation_id)
    print()
    print(f"Restored: {result.moved}   Blocked/failed: {result.failed}")
    for failure in result.failures[:10]:
        print(f"  - {failure.message}")
    return _exit_for(result)


def cmd_history(args, style: Style) -> int:  # noqa: ANN001
    db = Database(AppPaths.default().ensure().database_path)
    if args.operation:
        txn = db.get_transaction(args.operation)
        if txn is None:
            print("No such transaction.")
            return GENERAL_FAILURE
        print(f"#{txn['id']}  {txn.get('operation_id', '')}")
        print(f"Kind: {txn['kind']}   Status: {txn['status']}")
        print(f"Root: {txn['root']}")
        print(f"Started: {_local(txn['created_at'])}")
        ops = db.transaction_operations(int(txn["id"]))
        print(f"Operations: {len(ops)}")
        for op in ops[:50]:
            status = "verified" if op["status"] == "VERIFIED" else op["status"]
            line = f"  {op['source']} -> {op['destination']}   [{status}]"
            if op.get("error"):
                line += f"  {op['error']}"
            print(safe_text(line))
        return SUCCESS

    rows = db.list_transactions(limit=args.limit, kinds=("ORGANIZE", "UNDO"))
    if not rows:
        print("No history yet. SFO records every organization here afterwards.")
        return SUCCESS
    print("Recent transactions:")
    for row in rows:
        op_id = row.get("operation_id", "")
        undone = "  [undone]" if op_id and db.is_undone(op_id) else ""
        root_name = Path(row["root"]).name or row["root"]
        print(
            f"  #{row['id']}  {_local(row['created_at'])}  {row['kind']:<8}"
            f"  {root_name:<20}  {row['status']:<10}  {op_id}{undone}"
        )
    return SUCCESS


def cmd_rules(args, style: Style) -> int:  # noqa: ANN001
    paths = AppPaths.default().ensure()
    rules, problems = _load_rules_file(paths.rules_path)

    action = args.action
    if action == "list" and args.target is None:
        if problems:
            for problem in problems:
                print(style.yellow(f"rule problem: {safe_text(problem)}"), file=sys.stderr)
        if not rules:
            print(
                "No rules defined.\n"
                "Create one with: sfo rules add\n"
                "Or edit: " + str(paths.rules_path)
            )
            return SUCCESS
        print("Rules:")
        for rule in rules:
            dest = rule.destination or "-"
            flag = "enabled " if rule.enabled else "DISABLED"
            print(
                f"  {rule.id}  {safe_text(rule.name)}\n"
                f"      when {' AND '.join(describe(c) for c in rule.conditions)}\n"
                f"      then {rule.action.value}"
                + (f" {dest}" if rule.destination else "")
                + f"\n      priority {rule.priority}  [{flag}]"
            )
        return SUCCESS

    if action == "enable" and args.target:
        return _set_rule_enabled(paths, rules, args.target, True, style)
    if action == "disable" and args.target:
        return _set_rule_enabled(paths, rules, args.target, False, style)
    if action == "delete" and args.target:
        remaining = [r for r in rules if r.id != args.target]
        if len(remaining) == len(rules):
            raise UsageError(f"no rule with id {args.target}")
        save_rules(paths.rules_path, remaining)
        print(f"Removed rule {args.target}.")
        print("No files were changed.")
        return SUCCESS
    if action == "test" and args.target:
        return _rules_test(args.target, style)
    raise UsageError("usage: sfo rules [list|enable|disable|delete|test] [target]")


def _set_rule_enabled(paths, rules, rule_id: str, enabled: bool, style) -> int:  # noqa: ANN001
    hit = False
    updated = []
    for rule in rules:
        if rule.id == rule_id:
            from dataclasses import replace

            updated.append(replace(rule, enabled=enabled))
            hit = True
        else:
            updated.append(rule)
    if not hit:
        raise UsageError(f"no rule with id {rule_id}")
    problems = validate_rules(updated)
    if problems:
        for problem in problems:
            print(style.yellow(f"rule problem: {safe_text(problem)}"), file=sys.stderr)
        return GENERAL_FAILURE
    save_rules(paths.rules_path, updated)
    print(f"{rule_id} is now {'enabled' if enabled else 'disabled'}.")
    print("This changes future planning only. No files were changed.")
    return SUCCESS


def _rules_test(folder_raw: str, style: Style) -> int:  # noqa: ANN001
    from sfo.cli.session import Session
    from sfo.rules.engine import first_matching_rule
    from sfo.rules.models import RuleContext

    session = Session(verbose=False)
    root = session.validate_root(folder_raw)
    user_rules, problems = session.organization_rules()
    if problems:
        for problem in problems:
            print(style.yellow(f"rule problem: {safe_text(problem)}"), file=sys.stderr)
        return GENERAL_FAILURE
    if not user_rules:
        print("No enabled rules to test. Create one with: sfo rules add")
        return SUCCESS

    scan = Scanner(session.fs, session.ruleset).scan(root)
    analysis = AnalysisEngine(session.fs).analyze(scan)

    shown = 0
    matched_count = 0
    for record in scan.files:
        path = record.absolute_path
        context = RuleContext(
            record=record,
            project_name=(analysis.project_for(path).name if analysis.project_for(path) else None),
            topic_name=analysis.topic_for(path),
            is_duplicate=False,
            relative_path_posix=str(path.relative_to(root)),
        )
        decision = first_matching_rule(user_rules, context)
        if decision is None:
            continue
        rule, matched = decision
        matched_count += 1
        if shown < 20:
            shown += 1
            dest = rule.destination or rule.action.value.lower()
            print(
                f"{safe_text(context.relative_path_posix)}\n  matched {rule.id}: {matched}\n  would go to: {dest}"
            )
    print(f"\n{matched_count} file(s) would be affected by rules. Nothing was changed.")
    return SUCCESS


def cmd_status(args, style: Style) -> int:  # noqa: ANN001
    paths = AppPaths.default().ensure()
    db = Database(paths.database_path)
    txns = db.list_transactions(limit=1000)
    journals = sorted(paths.journal_dir.glob("*.jsonl")) if paths.journal_dir.is_dir() else []
    print(f"SFO {__version__}")
    print(f"Settings: {paths.settings_path}")
    print(f"Rules:    {paths.rules_path}")
    print(f"History:  {paths.database_path} ({len(txns)} transactions)")
    print(f"Journals: {paths.journal_dir} ({len(journals)})")
    session = _session(args)
    pending = session.pending_recoveries()
    if pending:
        print(style.yellow(f"Incomplete operations requiring recovery: {len(pending)}"))
        print("Run: sfo recover")
    else:
        print("All recorded operations are consistent.")
    return SUCCESS


def cmd_diagnostics(args, style: Style) -> int:  # noqa: ANN001
    paths = AppPaths.default().ensure()
    if args.clear:
        if (
            input(
                "Delete SFO's local history and journals? This cannot be undone. Type 'yes': "
            ).strip()
            != "yes"
        ):
            print("Cancelled.")
            return SUCCESS
        if paths.journal_dir.is_dir():
            for entry in paths.journal_dir.iterdir():
                if entry.is_file():
                    entry.unlink()
        if paths.database_path.exists():
            paths.database_path.unlink()
        print("Local diagnostics cleared. No user files were touched.")
        return SUCCESS

    db = Database(paths.database_path)
    rows = db.list_transactions(limit=args.summary and 5 or 10, kinds=("ORGANIZE", "UNDO"))
    print("Diagnostic summary (local only):")
    print(f"  SFO version: {__version__}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Transactions recorded: {len(rows)}")
    for row in rows[:5]:
        print(f"    #{row['id']} {row['kind']} {row['status']} {_local(row['created_at'])}")
    journals = sorted(paths.journal_dir.glob("*.jsonl")) if paths.journal_dir.is_dir() else []
    print(f"  Journal files: {len(journals)}")
    return SUCCESS


def cmd_recover(args, style: Style) -> int:  # noqa: ANN001
    session = _session(args)
    items = session.pending_recoveries()
    if not items:
        print("Nothing to recover. All recorded operations are consistent.")
        return SUCCESS
    print("Incomplete operations detected:")
    for item in items:
        op_id = getattr(item, "operation_id", "?")
        cls = getattr(getattr(item, "classification", None), "name", "?")
        journal = getattr(item, "journal_path", "")
        print(f"  {op_id}  [{cls}]  {journal}")
    print()
    print("Inspect the journal files above. SFO will not guess what happened;")
    print("each operation lists the filesystem evidence it collected.")
    print("If an operation looks finished and correct, no action is needed:")
    print("completed moves are already verified and recorded.")
    return SUCCESS


def cmd_policy(args, protect: bool, add: bool) -> int:  # noqa: ANN001
    paths = AppPaths.default().ensure()
    config = load_user_config(paths)
    raw = Path(args.path).expanduser()
    resolved = raw.resolve(strict=True) if raw.exists() else raw.absolute()
    label = "protected" if protect else "ignored"
    if add:
        changed = (
            config.add_protected(resolved, reason="user command")
            if protect
            else config.add_ignored(resolved, reason="user command")
        )
        if changed:
            config.save(paths)
            print(f"{resolved} is now {label}.")
        else:
            print(f"{resolved} was already {label}.")
    else:
        key = str(resolved)
        bucket = config.protected if protect else config.ignored
        before = len(bucket)
        bucket[:] = [r for r in bucket if str(r.path) != key]
        if len(bucket) == before:
            print(f"{resolved} was not in the {label} list.")
        else:
            config.save(paths)
            print(f"{resolved} is no longer {label}.")
    print("No files were changed.")
    return SUCCESS


def cmd_policy_list(args, protected: bool) -> int:  # noqa: ANN001
    config = load_user_config(AppPaths.default().ensure())
    entries = config.protected if protected else config.ignored
    label = "Protected" if protected else "Ignored"
    if not entries:
        print(f"No {label.lower()} paths configured.")
        print(f"Add one with: sfo {'protect' if protected else 'ignore'} <path>")
        return SUCCESS
    print(f"{label} paths (never moved by SFO):" if protected else "Ignored paths (not scanned):")
    for entry in entries:
        reason = f"  ({entry.reason})" if entry.reason else ""
        print(f"  {entry.path}{reason}")
    return SUCCESS


def cmd_inspect(args, style: Style) -> int:  # noqa: ANN001
    from sfo.inspection.inspector import InspectionDeps, inspect_path

    session = _session(args)
    target = Path(args.path).expanduser()
    # lexists: a broken symlink still exists as an object worth inspecting.
    if not os.path.lexists(target):
        print(f"No such file or folder: {args.path}")
        return GENERAL_FAILURE

    deps = InspectionDeps(
        fs=session.fs,
        ruleset=session.ruleset,
        org_rules=session.organization_rules()[0],
        database=session.db,
    )
    report = inspect_path(
        target,
        deps,
        want_hash=args.hash,
        want_preview=args.preview,
        want_duplicates=args.duplicates,
    )

    if args.json:
        print(jsonlib.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return SUCCESS

    if report.state == "MISSING":
        print(f"The file disappeared before it could be inspected: {report.name}")
        return GENERAL_FAILURE

    print(f"{report.kind}\n{safe_text(report.name)}")
    print(f"\nLOCATION\n  absolute: {report.absolute_path}")
    print(f"  parent:   {report.parent}")
    if report.size_bytes is not None:
        print(
            f"\nSIZE\n  {_human_bytes(report.size_bytes)}"
            + (f"  ({report.size_bytes} bytes)" if args.verbose else "")
        )
    stamps = [t for t in (report.modified, report.created, report.accessed) if t]
    if stamps:
        print("\nTIMESTAMPS")
        for label, value in (
            ("modified", report.modified),
            ("created", report.created),
            ("accessed", report.accessed),
        ):
            print(f"  {label:>9}: {value or 'unavailable'}")
    if report.permissions:
        print(
            f"\nPERMISSIONS\n  {report.permissions}"
            + (f"  owner: {report.owner}" if report.owner else "")
        )
    print("\nTYPE")
    declared = report.extension_label or "unknown"
    detected = report.detected_label or "unavailable"
    print(f"  by extension: {declared}")
    print(f"  by content:   {detected}")
    if report.type_mismatch:
        print("  ! Extension and detected type may not match. SFO will not rename anything.")

    print(
        f"\nPROTECTION\n  {report.protection}"
        + (f"  ({report.protection_reason})" if report.protection_reason else "")
    )

    if report.project_name:
        print(f"\nPROJECT\n  {report.project_name}  [{report.project_confidence}]")
        print(f"  root: {report.project_root}")

    print("\nCLASSIFICATION")
    if report.rule_id:
        print(f"  source: explicit user rule {report.rule_id}")
        if report.rule_summary:
            print(f"  rule:   {safe_text(report.rule_summary)}")
        print(f"  result: would prefer {report.rule_destination}")
        print(f"  matched: {safe_text(report.rule_match)}")
    elif report.project_name and report.project_confidence == "Strong":
        print(f"  source: project detector -> stays with project '{report.project_name}'")
    else:
        print("  no strong classification; SFO would leave this file unchanged")

    print(f"\nDUPLICATES\n  {report.duplicate_status}")
    if report.duplicate_group:
        print(f"  group: {report.duplicate_group}")
        for copy in report.duplicate_copies[:5]:
            print(f"  copy:  {copy}")

    if report.symlink_target is not None:
        exists = "exists" if report.symlink_target_exists else "BROKEN"
        external = (
            "EXTERNAL TARGET - not followed" if report.symlink_external else "inside its folder"
        )
        print(f"\nSYMLINK\n  target: {report.symlink_target}  ({exists}, {external})")

    if report.directory_stats is not None:
        stats = report.directory_stats
        print(
            f"\nDIRECTORY\n  files: {stats['files']}   subfolders: {stats['subdirectories']}"
            f"   total size: {_human_bytes(stats['total_bytes'])}"
        )
        if stats["vcs_entries_skipped"]:
            print(f"  project-internal entries skipped from totals: {stats['vcs_entries_skipped']}")
        if stats["truncated"]:
            print("  (large folder; summary truncated)")
        if stats["tree"] and args.verbose:
            print("  tree:")
            for line in stats["tree"]:
                print(f"    {line}")

    if report.preview_text is not None or report.preview_note:
        print("\nPREVIEW")
        if report.preview_text:
            for line in report.preview_text.splitlines():
                print(f"  | {safe_text(line)}")
        if report.preview_note:
            print(f"  ({report.preview_note})")

    if report.hash_hex:
        print(f"\nSHA-256\n  {report.hash_hex}")

    if report.history:
        print("\nHISTORY (past transactions mentioning this path)")
        for event in report.history:
            when = str(event.get("date", ""))[:16].replace("T", " ")
            print(f"  {when}  {event.get('kind')}  {event.get('result')}")
            print(f"    {event.get('moved_from')} -> {event.get('moved_to')}")

    print("\nRead-only inspection. Nothing was changed.")
    return SUCCESS


def cmd_config(args, style: Style) -> int:  # noqa: ANN001
    for name, location in config_locations(AppPaths.default().ensure()).items():
        print(f"{name:>18}: {location}")
    return SUCCESS


def cmd_duplicates(args, style: Style) -> int:  # noqa: ANN001
    from sfo.duplicates.scanner import DuplicateScanner

    session = _session(args)
    root = Path(args.folder).expanduser()
    if not root.exists():
        raise UsageError(f"no such folder: {args.folder}")
    if not root.is_dir():
        raise UsageError(f"not a folder: {args.folder}")
    resolved = root.resolve(strict=False)

    if not args.json:
        print("Duplicate analysis (read-only). No files will be changed.")
        print(f"Root: {resolved}")

    scanner = DuplicateScanner(session.fs, session.ruleset)
    report = scanner.scan(resolved)

    if args.json:
        print(jsonlib.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return SUCCESS

    confirmed = report.confirmed_groups
    hardlinks = [g for g in report.groups if g.kind == "HARDLINKS"]
    print(
        f"\nScanned {report.scanned_files} files "
        f"(skipped: {report.skipped_symlinks} symlinks, "
        f"{report.skipped_special} special files, "
        f"{report.skipped_vcs} project-internal files)"
    )
    print(f"Confirmed duplicate groups: {len(confirmed)}")
    print(f"Hard-linked names (one file, several names): {len(hardlinks)}")
    print(f"Potentially reclaimable space: {_human_bytes(report.potentially_reclaimable)}")

    for group in report.groups[:20]:
        tags = (
            "CONFIRMED DUPLICATE"
            if group.kind == "CONFIRMED"
            else ("EMPTY FILES" if group.kind == "EMPTY" else "SAME FILE (hard links)")
        )
        extra = f", {_human_bytes(group.size)} each" if group.size else ""
        print(f"\n{group.group_id}  {tags}  {len(group.files)} files{extra}")
        if group.sha256:
            print(f"  content hash: {group.sha256[:16]}...")
        for f in group.files:
            marks = []
            if f.protected:
                marks.append("protected")
            if f.ignored:
                marks.append("ignored")
            if f.project:
                marks.append(f"project: {f.project}")
            suffix = f"  [{', '.join(marks)}]" if marks else ""
            print(f"  - {rel_display(resolved, f.path)}{suffix}")

    if len(report.groups) > 20:
        print(f"\n... and {len(report.groups) - 20} more groups.")
    if report.incomplete:
        print("\nNote: the scan was incomplete; this report may miss items.")
        for warning in report.warnings[:-1]:
            print(f"  - {safe_text(warning)}")
    print("\nNo files were changed. SFO never deletes duplicates automatically.")
    return SUCCESS


def _human_bytes(count: int) -> str:
    value = float(count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            whole = unit == "B"
            return f"{int(value)} {unit}" if whole else f"{value:.1f} {unit}"
        value /= 1024
    return f"{count} B"


def cmd_doctor(args, style: Style) -> int:  # noqa: ANN001
    paths = AppPaths.default().ensure()
    checks: list[tuple[bool, str]] = []
    for name in ("settings", "rules"):
        location = dict(config_locations(paths))[{"settings": "settings", "rules": "rules"}[name]]
        checks.append((location.parent.is_dir(), f"{name} directory exists"))
    try:
        Database(paths.database_path).list_transactions(limit=1)
        checks.append((True, "history database opens"))
    except Exception as exc:  # noqa: BLE001
        checks.append((False, f"history database error: {exc}"))
    rules, problems = _load_rules_file(paths.rules_path)
    checks.append((not problems, "rules parse cleanly" if not problems else problems[0]))
    checks.append((paths.journal_dir.is_dir(), "journal directory exists"))
    try:
        from sfo.infrastructure.filesystem.linux import LinuxFileSystem
        from sfo.recovery.reconciliation import pending_recoveries

        interrupted = pending_recoveries(paths.data_dir, LinuxFileSystem())
        checks.append(
            (
                not interrupted,
                "no interrupted transactions"
                if not interrupted
                else f"{len(interrupted)} interrupted transaction(s); run: sfo recover",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append((False, f"recovery scan failed: {exc}"))
    from sfo.cli.crash import recent_crashes

    crashes = recent_crashes(paths.data_dir)
    if crashes:
        checks.append(
            (True, f"{len(crashes)} diagnostic crash record(s) in {paths.data_dir / 'crashes'}")
        )
    ok = all(passed for passed, _ in checks)
    for passed, message in checks:
        marker = "[ok]" if passed else "[!!]"
        print(f"{marker} {message}")
    print("\nEverything looks good." if ok else "\nOne or more checks failed.")
    return SUCCESS if ok else GENERAL_FAILURE


# ---------------------------------------------------------------------------
def _session(args):
    from sfo.cli.session import Session

    return Session(verbose=bool(getattr(args, "verbose", False)))


def _progress_printer(args, style):  # noqa: ANN001
    if getattr(args, "json", False) or not sys.stdout.isatty():
        return None

    def show(message: str) -> None:
        print(style.dim(message))

    return show


def _render_preview(artifacts, style: Style, details: bool = False) -> None:  # noqa: ANN001
    plan = artifacts.plan
    analysis = artifacts.analysis
    stats = plan.statistics

    print("Smart Folder Organizer")
    print(f"Root: {plan.root}")
    print()
    print("Proposed organization\n")

    projects = analysis.projects
    if projects:
        print(style.bold("Projects"))
        for group in projects:
            organized = "(already organized)" if group.directory is not None else "(keep together)"
            print(
                f"  {safe_text(group.name)}  {len(group.members)} files  "
                f"{confidence_label(group.confidence.name)}  {organized}"
            )
        print()

    topics = analysis.topics
    if topics:
        print(style.bold("Topics"))
        for group in topics:
            print(f"  {safe_text(group.topic)}  {len(group.members)} files")
        print()

    print(style.bold("Summary"))
    print(f"  Files found:         {stats.total_files}")
    print(f"  To move:             {stats.moves}")
    print(f"  Already fine:        {stats.unchanged}")
    print(f"  Uncertain (untouched): {stats.uncertain}")
    print(f"  Conflicts:           {stats.conflicts}")
    print(f"  Protected:           {stats.protected}")
    print(f"  Skipped:             {stats.skipped}")
    print(
        f"  Directories created: {plan.directory_creations and len(plan.directory_creations) or 0}"
    )
    for warning in plan.warnings:
        print(style.yellow(f"  note: {safe_text(warning)}"))
    print()
    print("SFO never deletes, overwrites, or modifies file contents.")

    conflicts = plan.conflicts
    if conflicts:
        print()
        print(style.bold("Conflicts"))
        for action in conflicts[:8]:
            print(f"  {safe_text(rel_display(plan.root, action.source))}")
            print(f"    {action.reason}")
        if len(conflicts) > 8:
            print(f"  … and {len(conflicts) - 8} more")
        print("\n  No files will be overwritten.")

    uncertain = plan.uncertain_actions
    if uncertain:
        print()
        print(style.bold("Uncertain"))
        print(f"  {len(uncertain)} files will remain unchanged because evidence was too weak.")

    if details:
        moves = plan.moves
        if moves:
            print()
            print(style.bold("Planned moves"))
            for action in moves[:60]:
                arrow = f"{rel_display(plan.root, action.source)} -> {rel_display(plan.root, action.destination)}"
                print(f"  {safe_text(arrow)}")
                print(
                    style.dim(
                        f"    {action.reason_code}: {safe_text(action.reason)} "
                        f"[{confidence_label(action.confidence.name)}]"
                    )
                )
            if len(moves) > 60:
                print(f"  … and {len(moves) - 60} more (use --json for full output)")
        keeps = plan.keeps
        if keeps:
            sample = ", ".join(safe_text(rel_display(plan.root, k.source)) for k in keeps[:5])
            more = f" (+{len(keeps) - 5} more)" if len(keeps) > 5 else ""
            print()
            print(style.bold("Left unchanged"))
            print(f"  {sample}{more}")


def _plan_json(artifacts) -> dict:  # noqa: ANN001
    plan = artifacts.plan
    analysis = artifacts.analysis
    stats = plan.statistics
    return {
        "root": str(plan.root),
        "statistics": {
            "total_files": stats.total_files,
            "moves": stats.moves,
            "unchanged": stats.unchanged,
            "skipped": stats.skipped,
            "conflicts": stats.conflicts,
            "protected": stats.protected,
            "uncertain": stats.uncertain,
            "directories_created": stats.directories_created,
        },
        "projects": [
            {
                "name": g.name,
                "files": len(g.members),
                "confidence": g.confidence.name,
                "already_organized": g.directory is not None,
            }
            for g in analysis.projects
        ],
        "topics": [{"name": t.topic, "files": len(t.members)} for t in analysis.topics],
        "moves": [
            {
                "source_rel": rel_display(plan.root, a.source),
                "destination_rel": rel_display(plan.root, a.destination),
                "reason_code": a.reason_code,
                "reason": a.reason,
                "confidence": a.confidence.name,
                "rule_id": a.rule_id,
            }
            for a in plan.moves
        ],
        "warnings": list(plan.warnings),
    }


def _exit_for(result) -> int:  # noqa: ANN001
    if result.failed == 0 and result.status.value == "COMPLETED":
        return SUCCESS
    if result.status.value == "PARTIAL":
        return PARTIAL
    codes = {f.reason_code for f in result.failures}
    if result.moved == 0 and any("DESTINATION" in code for code in codes):
        from sfo.cli.exit_codes import CONFLICTS

        return CONFLICTS
    return GENERAL_FAILURE


def _local(iso: str) -> str:
    try:
        moment = datetime.fromisoformat(str(iso))
        return moment.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(iso)
