"""Arrangement engine: turns analysis into a validated, conservative plan.

PRIORITY MODEL (authoritative; documented verbatim in docs/rules.md):

    1. PROTECTED              ruleset protection / protect-rule
    2. IGNORED                ruleset ignore / ignore-rule
    3. SAFETY CONSTRAINTS     non-regular objects are never planned
    4. EXPLICIT USER RULE     prefer_directory rule
    5. PROJECT BOUNDARY       strong cluster already living in its own
                              on-disk directory -> structure preserved
    6. PROJECT MATCH          cluster without an on-disk home -> Projects/<n>/
    7. EXISTING STRUCTURE     file already inside its target -> keep
    8. DUPLICATE              exact copies (hash-verified) -> Duplicates/
    9. TOPIC RULE             Topics/<t>/ only when the topic is large enough
   10. INFERENCE/FALLBACK     loose top-level files -> Uncategorized/;
                              nested loose files stay put

Only MEDIUM-or-higher confidence ever produces a move; LOW confidence
becomes an UNCERTAIN action requiring review. The engine reads the scan and
analysis results and writes nothing to disk.
"""

from __future__ import annotations

from pathlib import Path

from sfo.analysis.result import AnalysisResult
from sfo.arrangement.destinations import (
    duplicates_target,
    project_target,
    topic_target,
    uncategorized_target,
)
from sfo.arrangement.naming import unique_destination
from sfo.arrangement.scoring import (
    MIN_DUPLICATE_GROUP_SIZE,
    is_executable_confidence,
    topic_folder_allowed,
)
from sfo.domain.confidence import Confidence
from sfo.domain.plan import (
    ActionStatus,
    DirectoryCreation,
    OrganizationPlan,
    PlannedMove,
    PlanStatistics,
    Recommendation,
)
from sfo.domain.records import FileRecord
from sfo.errors import SfoError
from sfo.infrastructure.filesystem import FileSystem
from sfo.rules.engine import first_matching_rule
from sfo.rules.models import OrganizationRule, RuleAction, RuleContext
from sfo.domain.rules import RuleSet
from sfo.scanning.result import ScanResult


class ArrangementError(SfoError):
    """Raised when a plan cannot be produced from the given inputs."""


def _value_for(confidence: Confidence) -> Recommendation:
    if confidence is Confidence.HIGH:
        return Recommendation.STRONGLY_RECOMMENDED
    if confidence is Confidence.MEDIUM:
        return Recommendation.RECOMMENDED
    return Recommendation.LOW_VALUE


class ArrangementEngine:
    def __init__(self, fs: FileSystem) -> None:
        self._fs = fs

    def build_plan(
        self,
        scan: ScanResult,
        analysis: AnalysisResult,
        rules: RuleSet = RuleSet.EMPTY,
        user_rules: tuple[OrganizationRule, ...] = (),
    ) -> OrganizationPlan:
        root = scan.root
        actions: list[PlannedMove] = []
        claimed: set[str] = set()
        next_id = 1

        # Duplicate membership lookup (exact content copies).
        dup_targets = self._duplicate_destinations(analysis, root, claimed)

        for record in sorted(scan.files, key=lambda r: r.relative_path.as_posix()):
            action_id = next_id
            outcome = self._decide(record, analysis, rules, user_rules, root, dup_targets, claimed)
            status, destination, reason_code, reason, confidence, rule_id = outcome
            if status is ActionStatus.MOVE and destination == record.absolute_path:
                status = ActionStatus.KEEP
            actions.append(
                PlannedMove(
                    action_id=action_id,
                    source=record.absolute_path,
                    destination=destination or record.absolute_path,
                    file_identity=record.identity,
                    reason=reason,
                    reason_code=reason_code,
                    confidence=confidence,
                    arrangement_value=_value_for(confidence),
                    status=status,
                    rule_id=rule_id,
                )
            )
            next_id += 1

        moves = [a for a in actions if a.status is ActionStatus.MOVE]
        creations = self._directory_creations(root, moves)

        statistics = PlanStatistics(
            total_files=len(scan.files),
            moves=len(moves),
            unchanged=sum(1 for a in actions if a.status is ActionStatus.KEEP),
            skipped=sum(
                1 for a in actions if a.status in (ActionStatus.SKIP, ActionStatus.PROTECTED)
            ),
            conflicts=sum(
                1
                for a in actions
                if a.status in (ActionStatus.CONFLICT, ActionStatus.REVIEW_REQUIRED)
            ),
            protected=sum(1 for a in actions if a.status is ActionStatus.PROTECTED),
            uncertain=sum(1 for a in actions if a.status is ActionStatus.UNCERTAIN),
            directories_created=len({c.path for c in creations}),
        )

        warnings = tuple(f"scan warning: {e.message}" for e in scan.errors) + tuple(
            f"analysis warning: {w}" for w in analysis.warnings
        )

        return OrganizationPlan(
            root=root,
            statistics=statistics,
            source_snapshot=scan.snapshot,
            actions=tuple(actions),
            directory_creations=tuple(creations),
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    def _decide(
        self,
        record: FileRecord,
        analysis: AnalysisResult,
        rules: RuleSet,
        user_rules: tuple[OrganizationRule, ...],
        root: Path,
        dup_targets: dict[Path, Path],
        claimed: set[str],
    ):
        rel = record.relative_path
        abs_path = record.absolute_path

        # 1/2. PROTECTED & IGNORED — absolute priority, never moved.
        if record.protected or rules.is_protected(root, abs_path):
            return (
                ActionStatus.PROTECTED,
                None,
                "PROTECTED",
                "protected by safety configuration",
                Confidence.HIGH,
                None,
            )
        if record.ignored or rules.is_ignored(root, abs_path):
            return (
                ActionStatus.SKIP,
                None,
                "IGNORED",
                "excluded by ignore rules",
                Confidence.HIGH,
                None,
            )
        if not record.is_scannable:
            return (
                ActionStatus.SKIP,
                None,
                "UNSUPPORTED_OBJECT",
                "not a stable regular file; never moved automatically",
                Confidence.HIGH,
                None,
            )

        # 1b/1c. SYSTEM SAFETY DEFAULTS: sensitive and temporary files are
        # recognized by name and never moved unless explicitly configured
        # otherwise. These are policy inputs, not user content decisions.
        from sfo.analysis.markers import is_sensitive, is_temporary

        if is_sensitive(record.name):
            return (
                ActionStatus.PROTECTED,
                None,
                "PROTECTED",
                "sensitive file (credentials/key material) protected by default",
                Confidence.HIGH,
                None,
            )
        if is_temporary(record.name):
            return (
                ActionStatus.SKIP,
                None,
                "IGNORED",
                "temporary or partial file; left untouched by default",
                Confidence.MEDIUM,
                None,
            )

        # 3. SAFETY: identity must be known before we ever propose a move.
        if record.identity is None:
            return (
                ActionStatus.SKIP,
                None,
                "INSUFFICIENT_EVIDENCE",
                "file identity could not be established safely",
                Confidence.NONE,
                None,
            )

        # 4. EXPLICIT USER RULE (never overrides protection above; never
        # splits a file that already lives inside its on-disk project).
        context = RuleContext(
            record=record,
            project_name=(
                analysis.project_for(abs_path).name if analysis.project_for(abs_path) else None
            ),
            topic_name=analysis.topic_for(abs_path),
            is_duplicate=abs_path in dup_targets,
            relative_path_posix=rel.as_posix(),
        )
        hit = first_matching_rule(list(user_rules), context)
        if hit is not None and hit[0].action is RuleAction.PREFER_DIRECTORY:
            rule, matched_condition = hit
            rule_target = root / (rule.destination or "")
            if not self._inside_existing_project_dir(abs_path, analysis):
                destination = unique_destination(rule_target, record.name, claimed)
                claimed.add(str(destination))
                return (
                    ActionStatus.MOVE,
                    destination,
                    "USER_RULE",
                    f'matched rule "{rule.name}" ({matched_condition})',
                    Confidence.HIGH,
                    rule.id,
                )

        # 8. DUPLICATE (checked before project/topic: exact-copy evidence
        # outranks naming heuristics for the *copies*; primaries stay put).
        if abs_path in dup_targets:
            destination = dup_targets[abs_path]
            claimed.add(str(destination))
            return (
                ActionStatus.MOVE,
                destination,
                "DUPLICATE",
                "exact duplicate of another file (content hash match)",
                Confidence.HIGH,
                None,
            )

        # 5/6. PROJECT BOUNDARY vs PROJECT MATCH.
        project = analysis.project_for(abs_path)
        if project is not None:
            if self._inside_existing_project_dir(abs_path, analysis):
                return (
                    ActionStatus.KEEP,
                    None,
                    "ALREADY_ORGANIZED",
                    f"already inside its project directory '{project.name}'",
                    project.confidence,
                    None,
                )
            if is_executable_confidence(project.confidence):
                base = root / project_target(project.name)
                destination = unique_destination(base, record.name, claimed)
                claimed.add(str(destination))
                evidence_bits = ", ".join(sorted({e.kind.value for e in project.evidence}))
                return (
                    ActionStatus.MOVE,
                    destination,
                    "PROJECT_MATCH",
                    f"part of project '{project.name}' ({evidence_bits})",
                    project.confidence,
                    None,
                )
            return (
                ActionStatus.UNCERTAIN,
                None,
                "LOW_CONFIDENCE_PROJECT",
                f"possibly part of project '{project.name}', but evidence is weak",
                project.confidence,
                None,
            )

        # 7. EXISTING STRUCTURE / minimal movement: files already sitting in
        # a category directory are left alone even without fresh evidence.
        if len(rel.parts) > 1 and rel.parts[0] in {
            "Projects",
            "Topics",
            "Duplicates",
            "Uncategorized",
        }:
            return (
                ActionStatus.KEEP,
                None,
                "ALREADY_ORGANIZED",
                "already organized in a managed category directory",
                Confidence.MEDIUM,
                None,
            )

        # 9. TOPIC RULE.
        topic_name = analysis.topic_for(abs_path)
        if topic_name is not None:
            members = self._topic_member_count(analysis, topic_name)
            if topic_folder_allowed(members):
                base = root / topic_target(topic_name)
                classification = analysis.classification_for(abs_path)
                destination = unique_destination(base, record.name, claimed)
                claimed.add(str(destination))
                return (
                    ActionStatus.MOVE,
                    destination,
                    "TOPIC_MATCH",
                    f"matches topic '{topic_name}'",
                    classification.confidence,
                    None,
                )
            return (
                ActionStatus.KEEP,
                None,
                "TOPIC_TOO_SMALL",
                f"resembles topic '{topic_name}', but the group is too small to justify a folder",
                Confidence.LOW,
                None,
            )

        # 10. INFERENCE/FALLBACK.
        if len(rel.parts) == 1:
            destination = unique_destination(root / uncategorized_target(), record.name, claimed)
            claimed.add(str(destination))
            return (
                ActionStatus.MOVE,
                destination,
                "UNCLASSIFIED_ROOT_FILE",
                "loose file at folder root; parked in Uncategorized",
                Confidence.MEDIUM,
                None,
            )
        return (
            ActionStatus.KEEP,
            None,
            "NO_SAFE_IMPROVEMENT",
            "no reliable evidence; nested file left untouched",
            Confidence.LOW,
            None,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _topic_member_count(analysis: AnalysisResult, topic_name: str) -> int:
        for group in analysis.topics:
            if group.topic == topic_name:
                return len(group.members)
        return 0

    @staticmethod
    def _inside_existing_project_dir(path: Path, analysis: AnalysisResult) -> bool:
        project = analysis.project_for(path)
        if project is None or project.directory is None:
            return False
        try:
            path.relative_to(project.directory)
        except ValueError:
            return False
        return True

    def _directory_creations(self, root: Path, moves: list[PlannedMove]) -> list[DirectoryCreation]:
        needed: dict[str, DirectoryCreation] = {}
        for move in moves:
            parent = move.destination.parent
            while parent != root and root in parent.parents:
                if not self._fs.exists(parent):
                    needed[str(parent)] = DirectoryCreation(
                        path=parent, reason=f"required for {move.destination.name}"
                    )
                parent = parent.parent
        ordered = sorted(needed.values(), key=lambda c: str(c.path))
        # Only leaf-most directories are created explicitly; create_directory
        # makes parents idempotently.
        leaves = [
            c
            for c in ordered
            if not any(other != c and other.path in c.path.parents for other in ordered)
        ]
        return leaves

    def _duplicate_destinations(
        self,
        analysis: AnalysisResult,
        root: Path,
        claimed: set[str],
    ) -> dict[Path, Path]:
        targets: dict[Path, Path] = {}
        for group in analysis.duplicate_groups:
            if len(group.members) < MIN_DUPLICATE_GROUP_SIZE:
                continue
            for member in sorted(group.members)[1:]:
                if not self._fs.exists(member):
                    continue
                name = member.name
                destination = unique_destination(root / duplicates_target(), name, claimed)
                claimed.add(str(destination))
                targets[member] = destination
        return targets


__all__ = ["ArrangementEngine", "ArrangementError"]
