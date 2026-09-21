"""Analysis engine: scans -> classifications, groups, duplicates, graph.

Deterministic and metadata-only. Produces the AnalysisResult consumed by
the arrangement engine; it never touches the filesystem beyond reads and
never proposes a move itself (planning is a separate layer).

CLASSIFIER_VERSION is recorded with every plan so future heuristic changes
remain explainable in history.
"""

from __future__ import annotations

from pathlib import Path

from sfo.analysis.duplicates import find_duplicate_groups
from sfo.analysis.projects import detect_projects
from sfo.analysis.topics import classify_topic
from sfo.domain.analysis import (
    AnalysisResult,
    Classification,
    ClassificationKind,
    Evidence,
    EvidenceKind,
    Relationship,
    RelationshipGraph,
    RelationshipType,
    TopicGroup,
)
from sfo.domain.confidence import Confidence
from sfo.infrastructure.filesystem import FileSystem
from sfo.scanning.result import ScanResult

CLASSIFIER_VERSION = "sfo-analysis-1"

# Topics below this size are still reported, but the planner will not
# create folders for them (see arrangement.scoring).
MIN_TOPIC_MEMBERS = 3


class AnalysisEngine:
    def __init__(self, fs: FileSystem) -> None:
        self._fs = fs

    def analyze(self, scan: ScanResult) -> AnalysisResult:
        scannable = [f for f in scan.files if f.is_scannable]

        duplicate_groups = tuple(find_duplicate_groups(scannable, self._fs))
        projects = detect_projects(scan)

        project_of: dict[Path, str] = {}
        for group in projects:
            for member in group.members:
                project_of[member] = group.name

        # Topic detection runs only for files outside any project.
        topic_groups: dict[str, list[Path]] = {}
        topic_confidence: dict[str, Confidence] = {}
        for record in scannable:
            if record.absolute_path in project_of:
                continue
            topic, confidence = classify_topic(record)
            if topic is None or confidence is Confidence.LOW:
                continue
            topic_groups.setdefault(topic, []).append(record.absolute_path)
            existing = topic_confidence.get(topic)
            if existing is None or confidence == Confidence.HIGH:
                topic_confidence[topic] = confidence

        topics = tuple(
            TopicGroup(
                topic=topic,
                members=tuple(sorted(topic_groups[topic])),
                confidence=topic_confidence.get(topic, Confidence.MEDIUM),
                evidence=(
                    Evidence(
                        EvidenceKind.TOPIC_TERMS,
                        topic_confidence.get(topic, Confidence.MEDIUM),
                        "filename terms match the controlled taxonomy",
                    ),
                ),
            )
            for topic in sorted(topic_groups)
            if len(topic_groups[topic]) >= MIN_TOPIC_MEMBERS
        )

        topic_of: dict[Path, str] = {}
        for group in topics:
            for member in group.members:
                topic_of[member] = group.topic

        classifications: dict[Path, Classification] = {}
        for record in scannable:
            path = record.absolute_path
            if path in project_of:
                group = next(g for g in projects if g.name == project_of[path])
                classifications[path] = Classification(
                    kind=ClassificationKind.PROJECT,
                    confidence=group.confidence,
                    name=group.name,
                    evidence=group.evidence,
                )
            elif path in topic_of:
                t_group = next(g for g in topics if g.topic == topic_of[path])
                classifications[path] = Classification(
                    kind=ClassificationKind.TOPIC,
                    confidence=t_group.confidence,
                    name=t_group.topic,
                    evidence=t_group.evidence,
                )
            else:
                classifications[path] = Classification.uncertain()

        uncertain = tuple(
            path
            for path in sorted(classifications)
            if classifications[path].kind is ClassificationKind.UNCERTAIN
        )
        skipped = tuple(f.absolute_path for f in scan.files if not f.is_scannable)

        return AnalysisResult(
            root=scan.root,
            classifications=classifications,
            projects=projects,
            topics=topics,
            duplicate_groups=duplicate_groups,
            graph=_build_graph(projects, topics, duplicate_groups),
            uncertain=uncertain,
            skipped=skipped,
            warnings=(f"classifier {CLASSIFIER_VERSION}",),
        )


def _build_graph(projects, topics, duplicate_groups) -> RelationshipGraph:  # noqa: ANN001
    edges: list[Relationship] = []
    for group in projects:
        for member in group.members:
            edges.append(
                Relationship(
                    source=member,
                    relation=RelationshipType.SAME_PROJECT,
                    target=group.name,
                    confidence=group.confidence,
                )
            )
    for group in topics:
        for member in group.members:
            edges.append(
                Relationship(
                    source=member,
                    relation=RelationshipType.SAME_TOPIC,
                    target=group.topic,
                    confidence=group.confidence,
                )
            )
    for group in duplicate_groups:
        primary = group.primary
        for member in group.members:
            edges.append(
                Relationship(
                    source=member,
                    relation=RelationshipType.DUPLICATE_OF,
                    target=primary.as_posix(),
                    confidence=Confidence.HIGH,
                )
            )
    return RelationshipGraph(nodes=tuple(sorted({e.source for e in edges})), edges=tuple(edges))
