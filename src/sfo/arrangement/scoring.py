"""Planning policy thresholds and gates.

Conservative by design: weak evidence never moves a file, small clusters
never spawn folders, and files already in their right place are left alone.
"""

from __future__ import annotations

from sfo.domain.confidence import Confidence

# A topic folder is only created when enough unrelated files share it;
# below this they stay where they are rather than fragmenting the layout.
MIN_FILES_FOR_TOPIC_FOLDER = 3

# Duplicate groups smaller than this are reported but not reorganized.
MIN_DUPLICATE_GROUP_SIZE = 2

_EXECUTABLE = frozenset({Confidence.HIGH, Confidence.MEDIUM})


def is_executable_confidence(confidence: Confidence) -> bool:
    return confidence in _EXECUTABLE


def topic_folder_allowed(member_count: int) -> bool:
    return member_count >= MIN_FILES_FOR_TOPIC_FOLDER
