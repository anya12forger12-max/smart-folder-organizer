"""Terminal rendering: safe display of untrusted names.

Filenames are data and may contain ANSI escapes, newlines or control
characters. Everything displayed passes through ``safe_text`` first so a
malicious filename can never manipulate the terminal. Output never depends
on color alone; NO_COLOR and non-TTY detection disable styling entirely.
"""

from __future__ import annotations

import os
import sys
import unicodedata


def safe_text(value: str, max_len: int = 120) -> str:
    """Make arbitrary text terminal-safe: escape controls, cap length."""
    out: list[str] = []
    for ch in value:
        category = unicodedata.category(ch)
        if ch in ("\n", "\r", "\t"):
            out.append({"\\n": "\\n", "\\r": "\\r", "\t": "\\t"}[ch])
        elif category.startswith("C") or ord(ch) < 32:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    text = "".join(out)
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def rel_display(root, path) -> str:  # noqa: ANN001 - Path pair
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


class Style:
    def __init__(self, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)


CONFIDENCE_LABELS = {
    "HIGH": "High confidence",
    "MEDIUM": "Medium confidence",
    "LOW": "Needs review",
    "NONE": "Uncertain",
}


def confidence_label(confidence_name: str) -> str:
    return CONFIDENCE_LABELS.get(confidence_name.upper(), confidence_name.title())
