"""Relationship graph construction.

Simple deterministic structures (no graph database). Edges connect a file to
its project/topic labels, its siblings, role-based project links and its
duplicate primaries.
"""

from __future__ import annotations

from sfo.analysis.markers import FileRole
from sfo.domain.analysis import (
    DuplicateGroup,
    Relationship,
    RelationshipGraph,
    RelationshipType,
)
from sfo.domain.confidence import Confidence


class RelationshipAnalyzer:
    def build(
        self,
        classifications: dict,
        duplicate_groups: tuple[DuplicateGroup, ...],
        roles: dict,
    ) -> RelationshipGraph:
        edges: list[Relationship] = []
        nodes: list = []

        for path, classification in sorted(classifications.items()):
            nodes.append(path)
            role = roles.get(path, FileRole.UNKNOWN)
            if classification.kind.value == "PROJECT" and classification.name:
                relation = {
                    FileRole.DOCUMENTATION: RelationshipType.DOCUMENTS_PROJECT,
                    FileRole.SOURCE: RelationshipType.SOURCE_OF_PROJECT,
                    FileRole.TEST: RelationshipType.TEST_OF_PROJECT,
                    FileRole.CONFIGURATION: RelationshipType.CONFIG_OF_PROJECT,
                }.get(role, RelationshipType.SAME_PROJECT)
                edges.append(
                    Relationship(
                        source=path,
                        relation=relation,
                        target=classification.name,
                        confidence=classification.confidence,
                    )
                )
            elif classification.kind.value == "TOPIC" and classification.name:
                edges.append(
                    Relationship(
                        source=path,
                        relation=RelationshipType.SAME_TOPIC,
                        target=classification.name,
                        confidence=classification.confidence,
                    )
                )

        for group in duplicate_groups:
            primary = group.primary
            for member in group.members:
                if member == primary:
                    continue
                edges.append(
                    Relationship(
                        source=member,
                        relation=RelationshipType.DUPLICATE_OF,
                        target=str(primary),
                        confidence=Confidence.VERY_HIGH,
                    )
                )

        return RelationshipGraph(nodes=tuple(nodes), edges=tuple(edges))
