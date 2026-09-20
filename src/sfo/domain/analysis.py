"""Analysis-layer domain models.

Everything here is pure data produced by reading scan results. The analysis
layer has no filesystem mutation capability by construction: these models
contain no I/O code at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sfo.domain.confidence import Confidence


class EvidenceKind(str, Enum):
    FILENAME_TERMS = "FILENAME_TERMS"
    NAMING_PATTERN = "NAMING_PATTERN"
    DIRECTORY_PROXIMITY = "DIRECTORY_PROXIMITY"
    EXISTING_STRUCTURE = "EXISTING_STRUCTURE"
    PROJECT_MARKER = "PROJECT_MARKER"
    EXTENSION = "EXTENSION"
    TIMESTAMP_PROXIMITY = "TIMESTAMP_PROXIMITY"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    TOPIC_TERMS = "TOPIC_TERMS"
    README_TITLE = "README_TITLE"


@dataclass(frozen=True, slots=True)
class Evidence:
    kind: EvidenceKind
    weight: Confidence
    description: str


class ClassificationKind(str, Enum):
    PROJECT = "PROJECT"
    TOPIC = "TOPIC"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True, slots=True)
class Classification:
    kind: ClassificationKind
    confidence: Confidence
    name: str | None = None  # project or topic label; None when uncertain
    evidence: tuple[Evidence, ...] = ()

    @classmethod
    def uncertain(cls) -> "Classification":
        return cls(
            kind=ClassificationKind.UNCERTAIN,
            confidence=Confidence.LOW,
            evidence=(
                Evidence(
                    EvidenceKind.FILENAME_TERMS,
                    Confidence.NONE,
                    "insufficient evidence to classify safely",
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class ProjectGroup:
    name: str
    directory: Path | None  # existing project directory, if any
    members: tuple[Path, ...]
    markers: tuple[str, ...]
    confidence: Confidence
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class TopicGroup:
    topic: str
    members: tuple[Path, ...]
    confidence: Confidence
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    sha256: str
    size: int
    members: tuple[Path, ...]

    @property
    def primary(self) -> Path:
        """Deterministic representative (lexicographically first)."""
        return sorted(self.members)[0]


class RelationshipType(str, Enum):
    SAME_PROJECT = "SAME_PROJECT"
    SAME_TOPIC = "SAME_TOPIC"
    SAME_DIRECTORY = "SAME_DIRECTORY"
    SAME_NAMING_PATTERN = "SAME_NAMING_PATTERN"
    DUPLICATE_OF = "DUPLICATE_OF"
    DOCUMENTS_PROJECT = "DOCUMENTS_PROJECT"
    SOURCE_OF_PROJECT = "SOURCE_OF_PROJECT"
    TEST_OF_PROJECT = "TEST_OF_PROJECT"
    CONFIG_OF_PROJECT = "CONFIG_OF_PROJECT"


@dataclass(frozen=True, slots=True)
class Relationship:
    source: Path
    relation: RelationshipType
    target: str  # project/topic label or sibling path as string
    confidence: Confidence


@dataclass(frozen=True, slots=True)
class RelationshipGraph:
    nodes: tuple[Path, ...]
    edges: tuple[Relationship, ...]

    def edges_for(self, path: Path) -> tuple[Relationship, ...]:
        return tuple(e for e in self.edges if e.source == path)


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    root: Path
    classifications: dict[Path, Classification]
    projects: tuple[ProjectGroup, ...]
    topics: tuple[TopicGroup, ...]
    duplicate_groups: tuple[DuplicateGroup, ...]
    graph: RelationshipGraph
    uncertain: tuple[Path, ...]
    skipped: tuple[Path, ...]
    warnings: tuple[str, ...]

    def classification_for(self, path: Path) -> Classification:
        return self.classifications.get(path, Classification.uncertain())

    def project_for(self, path: Path) -> ProjectGroup | None:
        c = self.classification_for(path)
        if c.kind is not ClassificationKind.PROJECT or c.name is None:
            return None
        for group in self.projects:
            if group.name == c.name:
                return group
        return None

    def topic_for(self, path: Path) -> str | None:
        c = self.classification_for(path)
        if c.kind is ClassificationKind.TOPIC:
            return c.name
        return None
