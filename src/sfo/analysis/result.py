"""Public re-exports of analysis result models.

The canonical definitions live in sfo.domain.analysis (pure data); this
module gives the rest of the pipeline a stable import surface.
"""

from __future__ import annotations

from sfo.analysis.engine import CLASSIFIER_VERSION, AnalysisEngine
from sfo.domain.analysis import (
    AnalysisResult,
    Classification,
    ClassificationKind,
    DuplicateGroup,
    Evidence,
    EvidenceKind,
    ProjectGroup,
    Relationship,
    RelationshipGraph,
    RelationshipType,
    TopicGroup,
)

__all__ = [
    "CLASSIFIER_VERSION",
    "AnalysisEngine",
    "AnalysisResult",
    "Classification",
    "ClassificationKind",
    "DuplicateGroup",
    "Evidence",
    "EvidenceKind",
    "ProjectGroup",
    "Relationship",
    "RelationshipGraph",
    "RelationshipType",
    "TopicGroup",
]
