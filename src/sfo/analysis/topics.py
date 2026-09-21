"""Controlled topic taxonomy: small, human-readable, evidence-gated.

Topics are inferred ONLY from filename terms and extensions - never from
file contents. A topic folder is proposed by the planner only when the
group is large enough (see arrangement.scoring).
"""

from __future__ import annotations

from sfo.domain.confidence import Confidence
from sfo.domain.records import FileRecord

# term -> topic. Deliberately small; users customize via rules instead.
TAXONOMY: dict[str, str] = {
    # Programming / technology
    "python": "Programming",
    "javascript": "Programming",
    "typescript": "Programming",
    "code": "Programming",
    "script": "Programming",
    "program": "Programming",
    "api": "Programming",
    "database": "Programming",
    "docker": "Programming",
    # Cybersecurity
    "security": "Cybersecurity",
    "cyber": "Cybersecurity",
    "firewall": "Cybersecurity",
    "malware": "Cybersecurity",
    "encryption": "Cybersecurity",
    "vulnerability": "Cybersecurity",
    "pentest": "Cybersecurity",
    "phishing": "Cybersecurity",
    # School / education
    "lecture": "School",
    "homework": "School",
    "assignment": "School",
    "worksheet": "School",
    "chapter": "School",
    "class": "School",
    "physics": "School",
    "chemistry": "School",
    "biology": "School",
    "mathematics": "School",
    "maths": "School",
    "math": "School",
    "ncert": "School",
    "syllabus": "School",
    "exam": "School",
    # Research
    "research": "Research",
    "paper": "Research",
    "thesis": "Research",
    "survey": "Research",
    "study": "Research",
    "analysis": "Research",
    # Finance
    "invoice": "Finance",
    "receipt": "Finance",
    "budget": "Finance",
    "tax": "Finance",
    "salary": "Finance",
    "bank": "Finance",
    "statement": "Finance",
    # Health
    "medical": "Health",
    "health": "Health",
    " prescription": "Health",
}

EXTENSION_TOPICS: dict[str, str] = {
    ".py": "Programming",
    ".js": "Programming",
    ".ts": "Programming",
    ".go": "Programming",
    ".rs": "Programming",
    ".java": "Programming",
    ".c": "Programming",
    ".cpp": "Programming",
    ".h": "Programming",
    ".sh": "Programming",
    ".mp4": "Media",
    ".mkv": "Media",
    ".avi": "Media",
    ".mov": "Media",
    ".mp3": "Media",
    ".flac": "Media",
    ".wav": "Media",
    ".png": "Media",
    ".jpg": "Media",
    ".jpeg": "Media",
    ".gif": "Media",
    ".webp": "Media",
    ".svg": "Media",
    ".zip": "Archives",
    ".tar": "Archives",
    ".gz": "Archives",
    ".7z": "Archives",
    ".rar": "Archives",
    ".xz": "Archives",
}


def classify_topic(record: FileRecord) -> tuple[str | None, Confidence]:
    """Return (topic, confidence) or (None, LOW).

    Evidence rule: an explicit keyword in the filename gives MEDIUM;
    a matching extension alone gives only WEAK-level support and is
    returned as None so weak signals cannot create folders. Multiple
    agreeing signals raise to HIGH.
    """
    from sfo.analysis.naming import tokenize

    tokens = set(tokenize(record.name))
    hits = {TAXONOMY[t] for t in tokens if t in TAXONOMY}
    ext_topic = EXTENSION_TOPICS.get(record.extension)

    if not hits:
        return None, Confidence.LOW
    if len(hits) == 1:
        topic = next(iter(hits))
        if ext_topic == topic:
            return topic, Confidence.HIGH
        return topic, Confidence.MEDIUM
    # Conflicting keyword topics: ambiguous on purpose.
    return None, Confidence.LOW
