"""SafetyPolicy: the immutable safety constraints.

These are NOT user-configurable rules. No CLI flag, config value or rule file
can enable deletion, overwriting, content modification or execution. The
policy object exists so tests and code can assert against a single source of
truth for what SFO will never do.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

FORBIDDEN_OPERATIONS = frozenset(
    {
        "delete",
        "unlink",
        "remove",
        "rmdir",
        "rmtree",
        "truncate",
        "overwrite",
        "write_file",
        "modify_content",
        "execute",
        "chmod_user_file",
        "chown_user_file",
    }
)


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    allow_delete: bool = False
    allow_overwrite: bool = False
    allow_content_modification: bool = False
    allow_execute: bool = False
    allow_outside_root: bool = False
    require_confirmation: bool = True
    uncertain_default: str = "skip"

    @classmethod
    def default(cls) -> "SafetyPolicy":
        return cls()

    def assert_forbidden(self, operation: str) -> None:
        if operation in FORBIDDEN_OPERATIONS:
            raise PermissionError(f"operation '{operation}' is permanently forbidden in SFO")

    def to_lines(self) -> list[str]:
        labels = {
            "allow_delete": "Deletion",
            "allow_overwrite": "Overwriting",
            "allow_content_modification": "Content modification",
            "allow_execute": "File execution",
            "require_confirmation": "Confirmation required",
        }
        lines = []
        for f in fields(self):
            value = getattr(self, f.name)
            label = labels.get(f.name)
            if label is None:
                continue
            state = "enabled" if value else "disabled permanently"
            if f.name == "require_confirmation":
                state = "required" if value else "disabled"
            lines.append(f"{label}: {state}")
        return lines
