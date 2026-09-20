"""SFO command-line interface.

Commands: organize, preview, undo, history, rules, status, diagnostics,
recover, protect/unprotect/ignore/unignore, config, doctor, help.

Design contract: the ONLY mutating command is `organize` (and `undo`), both
of which require explicit confirmation unless --yes is passed -- and --yes
skips nothing except the interactive prompt; every security check still
runs. All other commands are read-only or touch only SFO's own config.
"""

from __future__ import annotations

import argparse
import sys

from sfo import __version__
from sfo.cli.exit_codes import (
    CONFLICTS,
    GENERAL_FAILURE,
    INVALID_USAGE,
    RECOVERY_REQUIRED,
    SAFETY_BLOCKED,
    STALE_PLAN,
    SUCCESS,
)
from sfo.cli.render import Style
from sfo.errors import SfoError

_BANNER = "Smart Folder Organizer (SFO)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sfo",
        description=(
            "Organize a folder safely: SFO groups related files into projects "
            "and topics, previews every move, and never deletes, overwrites "
            "or modifies file contents."
        ),
        epilog="Start with: sfo organize ~/Downloads   (preview first with: sfo preview ~/Downloads)",
    )
    parser.add_argument("--version", action="version", version=f"{_BANNER} {__version__}")
    parser.add_argument("--debug", action="store_true", help="show technical diagnostics")
    parser.add_argument("--no-color", action="store_true", help="disable colored output")
    sub = parser.add_subparsers(dest="command")

    p_org = sub.add_parser("organize", help="organize a folder (preview + confirm)")
    p_org.add_argument("folder")
    p_org.add_argument("--yes", action="store_true", help="skip the confirmation prompt; all safety checks still run")
    p_org.add_argument("--dry-run", action="store_true", help="plan and preview without any changes")
    p_org.add_argument("--json", action="store_true", help="machine-readable output")
    p_org.add_argument("--details", action="store_true", help="list every planned move")
    _common(p_org)

    p_prev = sub.add_parser("preview", help="show what would be organized; changes nothing")
    p_prev.add_argument("folder")
    p_prev.add_argument("--details", action="store_true", help="list individual moves")
    p_prev.add_argument("--json", action="store_true", help="machine-readable output")
    _common(p_prev)

    p_undo = sub.add_parser("undo", help="safely reverse a previous organization")
    p_undo.add_argument("operation", nargs="?", help="operation id (default: most recent)")
    p_undo.add_argument("--list", dest="list_ops", action="store_true")
    p_undo.add_argument("--yes", action="store_true")
    _common(p_undo)

    p_hist = sub.add_parser("history", help="show recent operations")
    p_hist.add_argument("operation", nargs="?")
    p_hist.add_argument("--limit", type=int, default=10)

    p_rules = sub.add_parser("rules", help="manage organization rules")
    p_rules.add_argument("action", nargs="?", default="list", choices=["list", "enable", "disable", "delete", "test"])
    p_rules.add_argument("target", nargs="?", help="rule id (or folder for 'test')")

    p_dup = sub.add_parser(
        "duplicates",
        help="find duplicate files (read-only; never changes anything)",
    )
    p_dup.add_argument("folder")
    p_dup.add_argument("--json", action="store_true", help="machine-readable output")
    _common(p_dup)

    p_inspect = sub.add_parser(
        "inspect",
        help="show what SFO knows about one file or folder (read-only)",
    )
    p_inspect.add_argument("path")
    p_inspect.add_argument("--hash", action="store_true", help="compute the SHA-256 content hash")
    p_inspect.add_argument("--preview", action="store_true", help="bounded text preview")
    p_inspect.add_argument("--duplicates", action="store_true", help="check its folder for duplicate copies")
    p_inspect.add_argument("--json", action="store_true", help="machine-readable output")
    _common(p_inspect)

    for name, helptext in (
        ("status", "show installation and safety status"),
        ("doctor", "diagnose configuration, permissions and storage"),
        ("recover", "inspect interrupted operations"),
        ("config", "show configuration locations"),
    ):
        sub.add_parser(name, help=helptext)

    p_diag = sub.add_parser("diagnostics", help="local diagnostic summary")
    p_diag.add_argument("--summary", action="store_true")
    p_diag.add_argument("--clear", action="store_true", help="clear journals/history metadata (asks to confirm)")

    for name in ("protect", "unprotect", "ignore", "unignore"):
        p = sub.add_parser(name, help=f"{name} a path (configuration change only)")
        p.add_argument("path")

    sub.add_parser("protected", help="list protected paths")
    sub.add_parser("ignored", help="list ignored paths")

    return parser


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--verbose", action="store_true")


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    style = Style(enabled=None if not args.no_color else False)

    if args.command is None:
        parser.print_help()
        return SUCCESS

    try:
        from sfo.cli import commands

        handler = {
            "organize": commands.cmd_organize,
            "preview": commands.cmd_preview,
            "undo": commands.cmd_undo,
            "history": commands.cmd_history,
            "rules": commands.cmd_rules,
            "status": commands.cmd_status,
            "diagnostics": commands.cmd_diagnostics,
            "recover": commands.cmd_recover,
            "protect": lambda a, s: commands.cmd_policy(a, protect=True, add=True),
            "unprotect": lambda a, s: commands.cmd_policy(a, protect=True, add=False),
            "ignore": lambda a, s: commands.cmd_policy(a, protect=False, add=True),
            "unignore": lambda a, s: commands.cmd_policy(a, protect=False, add=False),
            "protected": lambda a, s: commands.cmd_policy_list(a, protected=True),
            "ignored": lambda a, s: commands.cmd_policy_list(a, protected=False),
            "config": commands.cmd_config,
            "duplicates": commands.cmd_duplicates,
            "inspect": commands.cmd_inspect,
            "doctor": commands.cmd_doctor,
        }[args.command]
        return int(handler(args, style))
    except KeyboardInterrupt:
        print("\nCancelled safely. No new filesystem changes were started.")
        return SUCCESS
    except SfoError as exc:
        code = _exit_code_for(exc)
        print(f"Error: {exc}", file=sys.stderr)
        if getattr(args, "debug", False) and getattr(exc, "details", None):
            for line in exc.details:
                print(f"  - {line}", file=sys.stderr)
        return code
    except Exception as exc:  # unexpected: keep details out of normal output
        hint = ""
        try:
            from sfo.cli.crash import record_crash
            from sfo.config.paths import AppPaths

            location = record_crash(
                AppPaths.default().data_dir, sys.argv[1:], exc
            )
            hint = f" Diagnostic record: {location}"
        except Exception:
            pass  # diagnostics must never mask the original failure
        print(
            f"Unexpected error ({type(exc).__name__}).{hint} "
            "Run with --debug for details.",
            file=sys.stderr,
        )
        if getattr(args, "debug", False):
            raise
        return GENERAL_FAILURE


def _exit_code_for(exc: SfoError) -> int:
    name = type(exc).__name__
    return {
        "UsageError": INVALID_USAGE,
        "SecurityError": SAFETY_BLOCKED,
        "PathOutsideRootError": SAFETY_BLOCKED,
        "DestinationExistsError": CONFLICTS,
        "StalePlanError": STALE_PLAN,
        "LockError": RECOVERY_REQUIRED,
        "JournalError": RECOVERY_REQUIRED,
        "ConfigError": INVALID_USAGE,
        "RuleConfigError": INVALID_USAGE,
        "SchemaMismatchError": GENERAL_FAILURE,
    }.get(name, GENERAL_FAILURE)


if __name__ == "__main__":
    sys.exit(main())
