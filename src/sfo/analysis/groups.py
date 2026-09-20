"""Candidate-group formation from analysis evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sfo.domain.analysis import AnalysisResult, Evidence, ProjectGroup


class GroupType(str, Enum):
    PROJECT = "PROJECT"
    TOPIC = "TOPIC"


@dataclass(frozen=True, slots=True)
class CandidateGroup:
    group_id: str
    name: str
    group_type: GroupType
    members: tuple[Path, ...]
    evidence: tuple[Evidence, ...]
    confidence: str  # Confidence value name; kept as plain str for stable rendering
    recommended_destination: Path | None = None


class GroupBuilder:
    def build(self, analysis: AnalysisResult) -> tuple[CandidateGroup, ...]:
        groups: list[CandidateGroup] = []
        for project in analysis.projects:
            groups.append(
                CandidateGroup(
                    group_id=f"project::{project.name.lower()}",
                    name=project.name,
                    group_type=GroupType.PROJECT,
                    members=project.members,
                    evidence=project.evidence,
                    confidence=project.confidence.value,
                )
            )
        for topic in analysis.topics:
            groups.append(
                CandidateGroup(
                    group_id=f"topic::{topic.topic.lower()}",
                    name=topic.topic,
                    group_type=GroupType.TOPIC,
                    members=topic.members,
                    evidence=topic.evidence,
                    confidence=topic.confidence.value,
                )
            )
        groups.sort(key=lambda g: (g.group_type.value, g.name.lower()))
        return tuple(groups)

    @staticmethod
    def from_project(group: ProjectGroup) -> CandidateGroup:
        return CandidateGroup(
            group_id=f"project::{group.name.lower()}",
            name=group.name,
            group_type=GroupType.PROJECT,
            members=group.members,
            evidence=group.evidence,
            confidence=group.confidence.value,
        )
