"""Project detection: structural evidence first, naming clusters second.

Two independent signals, deliberately conservative:

1. MARKER PROJECTS (HIGH confidence): a directory containing a recognised
   project descriptor (.git, pyproject.toml, package.json, ...) is a project.
   Its entire subtree belongs together - internal structure is preserved by
   the planner, never flattened.

2. NAMING CLUSTERS (MEDIUM confidence): loose top-level files sharing a
   common leading token (meshtalk_readme.md, meshtalk-notes.txt) form a
   candidate project only when at least MIN_CLUSTER_FILES agree.

Similar names alone never merge two marker projects; boundaries come from
the filesystem structure, not string similarity.
"""

from __future__ import annotations

from pathlib import Path

from sfo.analysis.markers import marker_names_in
from sfo.analysis.naming import shared_prefix_term
from sfo.domain.analysis import Evidence, EvidenceKind, ProjectGroup
from sfo.domain.confidence import Confidence
from sfo.scanning.result import ScanResult

MIN_CLUSTER_FILES = 3


def detect_projects(scan: ScanResult) -> tuple[ProjectGroup, ...]:
    groups: list[ProjectGroup] = []
    claimed: set[Path] = set()

    # 1. Marker projects (deepest marker wins so nested repos stay distinct).
    dirs = sorted(
        {d.absolute_path for d in scan.directories} | {scan.root},
        key=lambda p: len(p.parts),
        reverse=True,
    )
    marker_dirs = [d for d in dirs if _has_marker(d)]
    owned_roots: list[Path] = []
    for candidate in marker_dirs:
        if any(root in candidate.parents or root == candidate for root in owned_roots):
            continue  # already inside a nearer marker project
        owned_roots.append(candidate)
    owned_roots.sort(key=lambda p: p.as_posix())

    for project_root in owned_roots:
        name = project_root.name if project_root != scan.root else scan.root.name
        members = tuple(
            f.absolute_path
            for f in scan.files
            if f.is_scannable
            and (project_root in f.absolute_path.parents or f.absolute_path.parent == project_root)
        )
        if not members:
            continue
        children = _child_names(project_root)
        markers = tuple(marker_names_in(children))
        groups.append(
            ProjectGroup(
                name=name,
                directory=project_root,
                members=members,
                markers=markers,
                confidence=Confidence.HIGH,
                evidence=(
                    Evidence(
                        EvidenceKind.PROJECT_MARKER,
                        Confidence.HIGH,
                        f"project descriptors present: {', '.join(markers)}",
                    ),
                    Evidence(
                        EvidenceKind.EXISTING_STRUCTURE,
                        Confidence.MEDIUM,
                        "files already live together under one project directory",
                    ),
                ),
            )
        )
        claimed.update(members)

    # 2. Naming clusters among still-unclaimed top-level files.
    loose = [
        f
        for f in scan.files
        if f.is_scannable and len(f.relative_path.parts) == 1 and f.absolute_path not in claimed
    ]
    prefix = shared_prefix_term([f.name for f in loose])
    if prefix is not None:
        cluster = [f for f in loose if _first_token(f.name) == prefix]
        if len(cluster) >= MIN_CLUSTER_FILES:
            members = tuple(sorted(f.absolute_path for f in cluster))
            groups.append(
                ProjectGroup(
                    name=prefix,
                    directory=None,
                    members=members,
                    markers=(),
                    confidence=Confidence.MEDIUM,
                    evidence=(
                        Evidence(
                            EvidenceKind.NAMING_PATTERN,
                            Confidence.MEDIUM,
                            f"{len(members)} files share the leading term '{prefix}'",
                        ),
                    ),
                )
            )

    return tuple(groups)


def _has_marker(directory: Path) -> bool:
    try:
        children = {c.name for c in directory.iterdir()}
    except OSError:
        return False
    return bool(marker_names_in(children))


def _child_names(directory: Path) -> set[str]:
    try:
        return {c.name for c in directory.iterdir()}
    except OSError:
        return set()


def _first_token(name: str) -> str:
    from sfo.analysis.naming import tokenize

    tokens = tokenize(name)
    return tokens[0] if tokens else ""
