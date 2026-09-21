"""Filename tokenisation for evidence extraction.

Filenames are data, never commands. Everything here is pure string work:
normalise, split into terms, strip version/download-artifact noise so that
`report-v2`, `report_final` and `report (1)` cluster together instead of
looking like unrelated projects.
"""

from __future__ import annotations

import re

_SPLIT = re.compile(r"[\s_\-.,()\[\]]+")
_VERSION_NOISE = {
    "v1",
    "v2",
    "v3",
    "v4",
    "v5",
    "final",
    "final2",
    "finaldraft",
    "copy",
    "copy2",
    "old",
    "new",
    "backup",
    "draft",
}
_ARTIFACT = re.compile(r"\(\d+\)$")
_STOPWORDS = frozenset({"the", "and", "for", "with", "notes", "doc", "document", "file"})


def normalize_stem(name: str) -> str:
    """Stem without extension, minus version/copy noise, lowercased."""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = _ARTIFACT.sub("", stem)
    terms = tokenize(stem)
    return "-".join(t for t in terms if t not in _VERSION_NOISE)


def tokenize(name: str) -> list[str]:
    lowered = name.lower()
    parts = [p for p in _SPLIT.split(lowered) if p]
    terms: list[str] = []
    for part in parts:
        if part in _STOPWORDS or part in _VERSION_NOISE:
            continue
        terms.append(part)
    return terms


def shared_prefix_term(names: list[str]) -> str | None:
    """Return a common leading token shared by >=2 names, if any.

    Used for loose-file project clustering (`meshtalk_readme.md`,
    `meshtalk-notes.txt` -> 'meshtalk'). Deterministic: longest candidate
    wins, ties broken lexicographically.
    """
    token_sets = [tokenize(n) for n in names]
    candidates: dict[str, int] = {}
    for tokens in token_sets:
        if not tokens:
            continue
        head = tokens[0]
        candidates[head] = candidates.get(head, 0) + 1
    qualifying = [
        (count, term) for term, count in candidates.items() if count >= 2 and len(term) >= 3
    ]
    if not qualifying:
        return None
    qualifying.sort(key=lambda pair: (-pair[0], pair[1]))
    return qualifying[0][1]
