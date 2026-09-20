"""Read-only file inspection: what SFO knows about one filesystem object.

The inspector answers "what is this and how does SFO see it?" It never
mutates anything: expensive context (hashes, duplicate groups, previews)
is computed lazily and only when explicitly requested by flags.

All information flows FROM existing components - the FileSystem boundary,
the duplicate scanner, the rule engine, user configuration and the
history database - so there is exactly one implementation of each concept.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sfo.domain.fs_types import FileType
from sfo.domain.records import FileRecord
from sfo.duplicates.scanner import VCS_DIRS, DuplicateScanner
from sfo.inspection.filetype import TEXT_EXTENSIONS, describe_extension, sniff
from sfo.rules.engine import first_matching_rule
from sfo.rules.models import RuleContext

SCHEMA_VERSION = 1

# Bounded project-marker walk-up: nearest directory carrying these wins.
_STRONG_MARKERS = frozenset({".git"})
_MODERATE_MARKERS = frozenset(
    {"pyproject.toml", "package.json", "Cargo.toml", "setup.py",
     "requirements.txt", "go.mod", "Makefile"}
)
_WEAK_MARKERS = frozenset({"README.md", "README.txt", "README"})

_PREVIEW_BYTES = 2048
_PREVIEW_LINES = 20
_TREE_MAX_ENTRIES = 40


@dataclass(frozen=True, slots=True)
class InspectionDeps:
    """Everything the inspector reads from; injected for testability."""

    fs: object                      # FileSystem
    ruleset: object                 # domain RuleSet (protected/ignored)
    org_rules: list                 # user OrganizationRules
    database: object | None = None  # history Database or None


@dataclass(frozen=True, slots=True)
class InspectionReport:
    schema_version: int
    state: str                       # CURRENT / MISSING / ...
    kind: str                        # FILE / DIRECTORY / SYMLINK / SPECIAL
    absolute_path: str
    name: str
    parent: str
    size_bytes: int | None = None
    modified: str | None = None
    created: str | None = None
    accessed: str | None = None
    permissions: str | None = None
    owner: str | None = None
    extension: str = ""
    extension_label: str = ""
    detected_label: str = ""
    detected_mime: str | None = None
    type_mismatch: bool = False
    protection: str = "Normal"
    protection_reason: str | None = None
    project_name: str | None = None
    project_root: str | None = None
    project_confidence: str | None = None
    rule_id: str | None = None
    rule_summary: str | None = None
    rule_destination: str | None = None
    rule_match: str | None = None
    duplicate_status: str = "Not analyzed"
    duplicate_group: str | None = None
    duplicate_copies: tuple[str, ...] = ()
    hash_hex: str | None = None
    preview_text: str | None = None
    preview_note: str | None = None
    symlink_target: str | None = None
    symlink_target_exists: bool | None = None
    symlink_external: bool | None = None
    directory_stats: dict | None = None
    history: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "state": self.state,
            "kind": self.kind,
            "path": self.absolute_path,
            "name": self.name,
            "parent": self.parent,
            "size_bytes": self.size_bytes,
            "timestamps": {
                "modified": self.modified,
                "created": self.created,
                "accessed": self.accessed,
            },
            "permissions": self.permissions,
            "owner": self.owner,
            "type": {
                "extension": self.extension,
                "declared": self.extension_label,
                "detected": self.detected_label,
                "mime": self.detected_mime,
                "mismatch": self.type_mismatch,
            },
            "protection": {
                "status": self.protection,
                "reason": self.protection_reason,
            },
            "project": {
                "name": self.project_name,
                "root": self.project_root,
                "confidence": self.project_confidence,
            },
            "rule": {
                "id": self.rule_id,
                "summary": self.rule_summary,
                "destination": self.rule_destination,
                "matched_condition": self.rule_match,
            },
            "duplicates": {
                "status": self.duplicate_status,
                "group": self.duplicate_group,
                "copies": list(self.duplicate_copies),
            },
            "hash_sha256": self.hash_hex,
            "preview": (
                {"text": self.preview_text, "note": self.preview_note}
                if self.preview_text is not None or self.preview_note else None
            ),
            "symlink": (
                {
                    "target": self.symlink_target,
                    "target_exists": self.symlink_target_exists,
                    "external": self.symlink_external,
                }
                if self.kind == "SYMLINK" else None
            ),
            "directory": self.directory_stats,
            "history": [dict(item) for item in self.history],
        }


def _iso(timestamp: float | None) -> str | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _permission_string(mode: int) -> str:
    return f"{oct(mode & 0o777)[2:]} ({stat.filemode(mode)})"


def _owner_of(target: Path) -> str | None:
    try:
        uid = os.lstat(target).st_uid
        import pwd

        return pwd.getpwuid(uid).pw_name
    except (ImportError, KeyError, OSError):
        return None


def detect_project(path: Path, is_dir: bool) -> tuple[str, Path, str] | None:
    """Conservative upward marker walk (max 4 levels). Returns
    (name, root, confidence) or None."""
    start = path if is_dir else path.parent
    current = start
    for _level in range(4):
        names = {entry.name for entry in _safe_iterdir(current)}
        confidence = None
        if names & _STRONG_MARKERS:
            confidence = "Strong"
        elif names & _MODERATE_MARKERS:
            confidence = "Moderate"
        elif names & _WEAK_MARKERS and current != start:
            confidence = "Weak"
        if confidence:
            return current.name, current, confidence
        if current.parent == current:
            break
        current = current.parent
    return None


def _safe_iterdir(directory: Path) -> list[Path]:
    try:
        return sorted(directory.iterdir())
    except OSError:
        return []


def inspect_path(
    target: Path,
    deps: InspectionDeps,
    *,
    want_hash: bool = False,
    want_preview: bool = False,
    want_duplicates: bool = False,
) -> InspectionReport:
    fs = deps.fs
    info = fs.inspect(target)

    if not info.exists:
        return InspectionReport(
            schema_version=SCHEMA_VERSION,
            state="MISSING",
            kind="MISSING",
            absolute_path=str(target),
            name=target.name,
            parent=str(target.parent),
        )

    kind = {
        FileType.REGULAR_FILE: "FILE",
        FileType.DIRECTORY: "DIRECTORY",
        FileType.SYMLINK: "SYMLINK",
    }.get(info.file_type, "SPECIAL")

    extension_label, extension_mime = describe_extension(target)
    sniffed = sniff(target) if kind == "FILE" else None
    mismatch = bool(
        sniffed is not None
        and extension_mime
        and sniffed.mime
        and sniffed.mime.split("/")[0] != extension_mime.split("/")[0]
        and not (sniffed.mime == "text/plain" and extension_mime.startswith("text/"))
        and not (sniffed.label == "ZIP-based archive or document" and extension_mime.startswith("application/"))
    )
    # A text-sniffed file with a document/archive extension is suspicious too
    # (e.g. photo.pdf that is really plain text).
    if (
        not mismatch
        and sniffed is not None
        and sniffed.label == "text"
        and extension_mime
        and not extension_mime.startswith("text/")
    ):
        mismatch = True

    protection, protection_reason = _protection_of(deps, target)

    project: tuple[str, Path, str] | None = None
    rule_id = rule_summary = rule_destination = rule_match = None
    if kind in ("FILE", "DIRECTORY"):
        project = detect_project(target, kind == "DIRECTORY")
        record = FileRecord(
            absolute_path=target,
            relative_path=Path(target.name),
            name=target.name,
            extension=target.suffix.lower(),
            size=info.size or 0,
            modified_at=info.modified_at,
            created_at=info.created_at,
            accessed_at=info.accessed_at,
            file_type=info.file_type,
            hidden=target.name.startswith("."),
            symlink_target=info.symlink_target,
            mode=info.mode,
            identity=None,
        )
        context = RuleContext(
            record=record,
            project_name=project[0] if project else None,
            topic_name=None,
            is_duplicate=False,
            relative_path_posix=target.name,
        )
        decision = first_matching_rule(list(deps.org_rules), context)
        if decision is not None:
            rule, matched = decision
            rule_id = rule.id
            rule_summary = rule.name
            rule_destination = rule.destination
            rule_match = matched

    hash_hex = None
    hash_error: str | None = None
    if want_hash and kind == "FILE":
        try:
            hash_hex = fs.hash_file(target)
        except OSError as exc:
            hash_hex = None
            hash_error = exc.strerror or str(exc)

    preview_text = preview_note = None
    if want_preview:
        preview_text, preview_note = _make_preview(target, kind, sniffed, info.size or 0)

    dup_status, dup_group, dup_copies = "Not analyzed", None, ()
    if want_duplicates:
        dup_status, dup_group, dup_copies = _duplicate_context(target, deps)

    return InspectionReport(
        schema_version=SCHEMA_VERSION,
        state="CURRENT",
        kind=kind,
        absolute_path=os.path.abspath(target),
        name=target.name,
        parent=str(target.parent),
        size_bytes=info.size,
        modified=_iso(info.modified_at),
        created=_iso(info.created_at),
        accessed=_iso(info.accessed_at),
        permissions=_permission_string(info.mode) if info.mode is not None else None,
        owner=_owner_of(target),
        extension=target.suffix.lower(),
        extension_label=extension_label,
        detected_label=sniffed.label if sniffed else ("directory" if kind == "DIRECTORY" else ""),
        detected_mime=sniffed.mime if sniffed else None,
        type_mismatch=mismatch,
        protection=protection,
        protection_reason=protection_reason,
        project_name=project[0] if project else None,
        project_root=str(project[1]) if project else None,
        project_confidence=project[2] if project else None,
        rule_id=rule_id,
        rule_summary=rule_summary,
        rule_destination=rule_destination,
        rule_match=rule_match,
        duplicate_status=dup_status,
        duplicate_group=dup_group,
        duplicate_copies=dup_copies,
        hash_hex=hash_hex,
        preview_text=preview_text,
        preview_note=(
            preview_note
            or (str(hash_error) if want_hash and kind == "FILE" and hash_hex is None else None)
        ),
        symlink_target=(info.symlink_target if kind == "SYMLINK" else None),
        symlink_target_exists=(
            _target_exists(target, info.symlink_target) if kind == "SYMLINK" else None
        ),
        symlink_external=(
            _symlink_external(target, info.symlink_target) if kind == "SYMLINK" else None
        ),
        directory_stats=(
            _directory_stats(fs, target) if kind == "DIRECTORY" else None
        ),
        history=tuple(_history_for(deps, target)),
    )


# ----------------------------------------------------------------------
def _protection_of(deps: InspectionDeps, target: Path) -> tuple[str, str | None]:
    ruleset = deps.ruleset
    try:
        if ruleset.is_protected(target.parent, target):
            reason = next(
                (rule.reason for rule in getattr(ruleset, "protected", ())
                 if rule.reason), None
            )
            return "Protected", reason
        if ruleset.is_ignored(target.parent, target):
            reason = next(
                (rule.reason for rule in getattr(ruleset, "ignored", ())
                 if rule.reason), None
            )
            return "Ignored", reason
    except Exception:  # noqa: BLE001 - protection display must never crash inspect
        pass
    return "Normal", None


def _make_preview(target: Path, kind: str, sniffed, size: int) -> tuple[str | None, str | None]:
    if kind != "FILE":
        return None, "preview is only available for regular files"
    if size == 0:
        return "", "empty file"
    if sniffed is None:
        return None, "content could not be read safely"
    looks_text = sniffed.is_text or target.suffix.lower() in TEXT_EXTENSIONS
    if not looks_text:
        return None, f"binary content ({sniffed.label}); no text preview"
    try:
        with open(target, "rb") as handle:  # read-only, bounded
            chunk = handle.read(_PREVIEW_BYTES + 1)
    except OSError as exc:
        return None, f"unreadable: {exc.strerror or exc}"
    truncated_bytes = len(chunk) > _PREVIEW_BYTES or size > _PREVIEW_BYTES
    text = chunk[:_PREVIEW_BYTES].decode("utf-8", errors="replace")
    lines = text.splitlines()
    note = None
    if len(lines) > _PREVIEW_LINES:
        lines = lines[:_PREVIEW_LINES]
        note = f"showing first {_PREVIEW_LINES} lines"
    elif truncated_bytes:
        note = f"showing first {_PREVIEW_BYTES} bytes of {size}"
    return "\n".join(lines), note


def _duplicate_context(target: Path, deps: InspectionDeps):
    """Scan the containing folder tree (lazy: only on explicit request)."""
    scanner = DuplicateScanner(deps.fs, deps.ruleset)
    scope = target if target.is_dir() else target.parent
    try:
        report = scanner.scan(scope)
    except OSError:
        return "Not analyzed", None, ()
    resolved = target.resolve(strict=False)
    info = deps.fs.inspect(target)
    for group in report.groups:
        for member in group.files:
            same_object = (
                member.inode == info.inode and member.device == info.device
                and info.inode is not None
            )
            if member.path.resolve(strict=False) == resolved or same_object:
                copies = [
                    str(f.path) for f in group.files
                    if f.path.resolve(strict=False) != resolved
                ]
                label = {
                    "CONFIRMED": "Confirmed duplicate",
                    "EMPTY": "Duplicate (empty files)",
                    "HARDLINKS": "Same underlying file (hard links)",
                }[group.kind]
                return label, group.group_id, tuple(copies)
    return "Unique (within its folder)", None, ()


def _history_for(deps: InspectionDeps, target: Path) -> list[dict]:
    if deps.database is None:
        return []
    needle = str(target.resolve(strict=False))
    events: list[dict] = []
    try:
        transactions = deps.database.list_transactions(limit=30)
    except Exception:  # noqa: BLE001 - history is context, never a failure
        return []
    for txn in transactions:
        try:
            ops = deps.database.transaction_operations(int(txn["id"]))
        except Exception:  # noqa: BLE001
            continue
        for op in ops:
            if str(op.get("source")) == needle or str(op.get("destination")) == needle:
                events.append(
                    {
                        "transaction": txn.get("external_id") or txn.get("id"),
                        "kind": txn.get("kind"),
                        "date": txn.get("created_at"),
                        "result": op.get("status"),
                        "moved_from": op.get("source"),
                        "moved_to": op.get("destination"),
                    }
                )
                break  # one line per transaction keeps output readable
        if len(events) >= 3:
            break
    return events


def _target_exists(link: Path, target: str | None) -> bool | None:
    if target is None:
        return None
    candidate = Path(target) if os.path.isabs(target) else _join_parent(link, target)
    try:
        return candidate.exists()
    except OSError:
        return None


def _symlink_external(link: Path, target: str | None) -> bool | None:
    if target is None:
        return None
    candidate = Path(target) if os.path.isabs(target) else _join_parent(link, target)
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return None
    return not resolved.is_relative_to(link.parent.resolve(strict=False))


def _join_parent(link: Path, target: str) -> Path:
    base = link.parent
    for part in Path(target).parts:
        if part == "..":
            base = base.parent
        elif part not in (".", "/"):
            base = base / part
    return base


def _directory_stats(fs, root: Path) -> dict:  # noqa: ANN001
    """Bounded summary: counts and total size, VCS trees excluded from the
    totals (counted separately). Never descends into symlinks."""
    files = subdirs = vcs_entries = 0
    total = 0
    truncated = False
    stack: list[tuple[Path, int]] = [(root, 0)]
    tree: list[str] = []
    while stack and not truncated:
        current, depth = stack.pop()
        try:
            entries = sorted(fs.list_directory(current))
        except OSError:
            continue
        for entry in entries:
            if len(tree) < _TREE_MAX_ENTRIES and depth <= 1:
                tree.append(("  " * depth) + entry.name + ("/" if entry.is_dir() else ""))
            try:
                info = fs.inspect(entry)
            except OSError:
                continue
            if info.file_type is FileType.DIRECTORY:
                if entry.name in VCS_DIRS:
                    vcs_entries += 1
                    continue
                subdirs += 1
                stack.append((entry, depth + 1))
            elif info.file_type is FileType.REGULAR_FILE:
                files += 1
                total += info.size or 0
            if files + subdirs > 50_000:
                truncated = True
                break
    return {
        "files": files,
        "subdirectories": subdirs,
        "total_bytes": total,
        "vcs_entries_skipped": vcs_entries,
        "truncated": truncated,
        "tree": tree[:_TREE_MAX_ENTRIES],
    }
