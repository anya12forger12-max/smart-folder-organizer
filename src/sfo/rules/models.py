"""Rule models.

Rules are strictly DATA describing organization preferences. There is no
expression language and no execution: conditions are structured field /
operator / value triples evaluated against scan metadata by sfo.rules.matcher.

Actions are limited to safe organization preferences. Destructive actions
(DELETE, OVERWRITE, ...) do not exist and any configuration containing them
is rejected by the validator before planning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sfo.domain.records import FileRecord

FORBIDDEN_ACTIONS = frozenset(
    {"DELETE", "OVERWRITE", "EXECUTE", "SHELL", "UPLOAD", "MODIFY", "COPY_AND_DELETE", "TRUNCATE"}
)


class RuleField(str, Enum):
    FILENAME = "filename"
    EXTENSION = "extension"
    DIRECTORY = "directory"
    PATH = "path"
    SIZE = "size"
    MODIFIED_DATE = "modified_date"
    PROJECT = "project"
    TOPIC = "topic"
    DUPLICATE = "duplicate"
    HIDDEN = "hidden"


class RuleOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    BETWEEN = "between"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"


class RuleAction(str, Enum):
    PREFER_DIRECTORY = "PREFER_DIRECTORY"
    PREFER_PROJECT = "PREFER_PROJECT"
    PREFER_TOPIC = "PREFER_TOPIC"
    KEEP = "KEEP"
    MARK_UNCERTAIN = "MARK_UNCERTAIN"

    @classmethod
    def allowed(cls) -> frozenset["RuleAction"]:
        return frozenset(cls)


_TEXT_FIELDS = {
    RuleField.FILENAME,
    RuleField.EXTENSION,
    RuleField.DIRECTORY,
    RuleField.PATH,
    RuleField.PROJECT,
    RuleField.TOPIC,
}
_NUMERIC_FIELDS = {RuleField.SIZE, RuleField.MODIFIED_DATE}
_FLAG_FIELDS = {RuleField.DUPLICATE, RuleField.HIDDEN}

_OPERATORS_FOR_TEXT = {
    RuleOperator.EQUALS,
    RuleOperator.NOT_EQUALS,
    RuleOperator.CONTAINS,
    RuleOperator.STARTS_WITH,
    RuleOperator.ENDS_WITH,
}
_OPERATORS_FOR_NUMERIC = {
    RuleOperator.GT,
    RuleOperator.LT,
    RuleOperator.GTE,
    RuleOperator.LTE,
    RuleOperator.BETWEEN,
    RuleOperator.EQUALS,
}
_OPERATORS_FOR_FLAG = {RuleOperator.IS_TRUE, RuleOperator.IS_FALSE}


@dataclass(frozen=True, slots=True)
class Condition:
    field: RuleField
    operator: RuleOperator
    value: str | int | float | bool
    value2: str | int | float | None = None


@dataclass(frozen=True, slots=True)
class OrganizationRule:
    id: str
    name: str
    priority: int
    action: RuleAction
    conditions: tuple[Condition, ...]
    destination: str | None = None  # relative POSIX path under the root
    enabled: bool = True
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class RuleDecision:
    rule_id: str
    rule_name: str
    matched_condition: str
    action: RuleAction
    destination: Path | None
    priority: int
    explanation: str


@dataclass(frozen=True, slots=True)
class RuleContext:
    record: FileRecord
    project_name: str | None
    topic_name: str | None
    is_duplicate: bool
    relative_path_posix: str

    @property
    def directory(self) -> str:
        return self.record.absolute_path.parent.name

    @property
    def filename(self) -> str:
        return self.record.name

    @property
    def extension(self) -> str:
        return self.record.extension


def operators_for_field(field: RuleField) -> frozenset[RuleOperator]:
    if field in _TEXT_FIELDS:
        return frozenset(_OPERATORS_FOR_TEXT)
    if field in _NUMERIC_FIELDS:
        return frozenset(_OPERATORS_FOR_NUMERIC)
    if field in _FLAG_FIELDS:
        return frozenset(_OPERATORS_FOR_FLAG)
    return frozenset()
