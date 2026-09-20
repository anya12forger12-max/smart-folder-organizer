"""Target layout computation.

Decides *where* a classified file should live. Produces relative paths
under the selected root using a small, predictable top-level structure:

    Projects/<Project>/...
    Topics/<Topic>/...
    Duplicates/
    Uncategorized/

The planner never invents deeper structures than these; existing project
internals are preserved rather than flattened (see engine.py).
"""

from __future__ import annotations

from pathlib import PurePosixPath

PROJECTS_DIR = "Projects"
TOPICS_DIR = "Topics"
DUPLICATES_DIR = "Duplicates"
UNCATEGORIZED_DIR = "Uncategorized"


def project_target(project_name: str) -> PurePosixPath:
    return PurePosixPath(PROJECTS_DIR) / _safe_component(project_name)


def topic_target(topic_name: str) -> PurePosixPath:
    return PurePosixPath(TOPICS_DIR) / _safe_component(topic_name)


def duplicates_target() -> PurePosixPath:
    return PurePosixPath(DUPLICATES_DIR)


def uncategorized_target() -> PurePosixPath:
    return PurePosixPath(UNCATEGORIZED_DIR)


def _safe_component(name: str) -> str:
    from sfo.arrangement.naming import slugify

    component = slugify(name)
    if component in {".", ".."} or "/" in component:
        component = "unnamed"
    return component
