"""Confidence levels shared by analysis, planning and rules.

Confidence is expressed in human categories only. Raw numeric scores exist
internally but are never shown to normal users.
"""

from __future__ import annotations

from enum import Enum


class Confidence(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK: dict[Confidence, int] = {
    Confidence.NONE: 0,
    Confidence.LOW: 1,
    Confidence.MEDIUM: 2,
    Confidence.HIGH: 3,
    Confidence.VERY_HIGH: 4,
}
