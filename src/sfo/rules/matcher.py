"""Condition matching against scan/analysis context.

Matching is deterministic, case-insensitive for text comparisons, and uses
only bounded string operations — no regex, no eval, no shell, no I/O.
"""

from __future__ import annotations

import datetime as _dt

from sfo.rules.models import Condition, RuleContext, operators_for_field


def parse_size(raw: str | int | float) -> float:
    """Accept plain byte counts or strings like '500MB' / '2 GiB'."""
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().upper().replace(" ", "")
    units = {
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "B": 1,
        "": 1,
    }
    for suffix in ("KIB", "MIB", "GIB", "KB", "MB", "GB", "B"):
        if text.endswith(suffix):
            return float(text[: -len(suffix)]) * units[suffix]
    raise ValueError(f"cannot parse size: {raw!r}")


def parse_timestamp(raw: str | int | float) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    date = _dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if date.tzinfo is None:
        date = date.replace(tzinfo=_dt.timezone.utc)
    return date.timestamp()


def matches(condition: Condition, context: RuleContext) -> bool:
    actual = _field_value(condition.field, context)
    operator = condition.operator
    if operator not in operators_for_field(condition.field):
        return False  # invalid combinations are rejected by validation too
    if condition.field.value == "size":
        left = float(actual)
        right = parse_size(condition.value)
        second = parse_size(condition.value2) if condition.value2 is not None else None
    elif condition.field.value == "modified_date":
        left = float(actual)
        right = parse_timestamp(condition.value)
        second = parse_timestamp(condition.value2) if condition.value2 is not None else None
    elif isinstance(actual, bool):
        return (operator.value == "is_true" and actual) or (
            operator.value == "is_false" and not actual
        )
    else:
        left = str(actual).casefold()
        right = str(condition.value).casefold()
        second = str(condition.value2).casefold() if condition.value2 is not None else None

    match operator.value:
        case "equals":
            return left == right
        case "not_equals":
            return left != right
        case "contains":
            return right in left
        case "starts_with":
            return left.startswith(right)
        case "ends_with":
            return left.endswith(right)
        case "gt":
            return left > right
        case "lt":
            return left < right
        case "gte":
            return left >= right
        case "lte":
            return left <= right
        case "between":
            return second is not None and right <= left <= second
        case _:
            return False


def describe(condition: Condition) -> str:
    base = f"{condition.field.value} {condition.operator.value.replace('_', ' ')} {condition.value}"
    if condition.value2 is not None:
        base += f" and {condition.value2}"
    return base.strip()


def _field_value(field_name, context: RuleContext):
    mapping = {
        "filename": context.filename,
        "extension": context.extension,
        "directory": context.directory,
        "path": context.relative_path_posix,
        "project": context.project_name or "",
        "topic": context.topic_name or "",
        "duplicate": context.is_duplicate,
        "hidden": context.record.hidden,
        "size": float(context.record.size),
        "modified_date": float(context.record.modified_at or 0.0),
    }
    return mapping[field_name.value]
