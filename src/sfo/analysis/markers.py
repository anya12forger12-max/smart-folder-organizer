"""Project marker registry and sensitive/temporary file patterns.

Descriptors are pure DATA - no executable content, ever. Detection runs on
names only; project files are never parsed or executed to identify them.
"""

from __future__ import annotations

import fnmatch

# A directory containing any of these is treated as a project root with
# HIGH confidence (structural evidence beats naming guesses).
PROJECT_MARKERS = frozenset(
    {
        ".git",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "CMakeLists.txt",
        "Makefile",
        "pubspec.yaml",
        "*.csproj",
        "composer.json",
        "requirements.txt",
    }
)

# Sensitive files are PROTECTED BY DEFAULT: recognized, never moved unless
# the user explicitly protects/unprotects via configuration.
SENSITIVE_EXACT = frozenset(
    {
        ".env",
        ".env.local",
        ".git-credentials",
        ".netrc",
        "credentials.json",
        "credentials",
        "secrets.yaml",
        "secrets.yml",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
    }
)
SENSITIVE_PATTERNS = ("*.pem", "*.key", "*.p12", "*.pfx", "*.kdbx", "*password*", "*secret*")

# Temporary/partial files: recognized but left untouched by default.
TEMPORARY_PATTERNS = (
    "*.tmp",
    "*.swp",
    "*.swo",
    "*.part",
    "*.partial",
    "*.crdownload",
    "~$",
    "*.bak",
    "*.orig",
    "*.temp",
)


def _matches_any(name: str, patterns: tuple[str, ...]) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, pat) for pat in patterns)


def marker_names_in(children: set[str]) -> list[str]:
    found = []
    for marker in sorted(PROJECT_MARKERS):
        if marker.startswith("*"):
            if _matches_any_dir_children(children, marker):
                found.append(marker)
        elif marker in children:
            found.append(marker)
    return found


def _matches_any_dir_children(children: set[str], pattern: str) -> bool:
    for child in children:
        if fnmatch.fnmatchcase(child.lower(), pattern):
            return True
    return False


def is_sensitive(name: str) -> bool:
    lowered = name.lower()
    return lowered in {n.lower() for n in SENSITIVE_EXACT} or _matches_any(
        lowered, SENSITIVE_PATTERNS
    )


def is_temporary(name: str) -> bool:
    return _matches_any(name.lower(), TEMPORARY_PATTERNS) or name.endswith("~")


# ---- file roles (documentation / source / test / configuration) --------
from enum import Enum  # noqa: E402


class FileRole(str, Enum):
    UNKNOWN = "UNKNOWN"
    DOCUMENTATION = "DOCUMENTATION"
    SOURCE = "SOURCE"
    TEST = "TEST"
    CONFIGURATION = "CONFIGURATION"


_DOC_PATTERNS = ("readme*", "*.md", "*.rst", "*.txt", "changelog*", "license*", "docs/*")
_SOURCE_EXTS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".dart",
    ".sh",
}
_TEST_HINTS = ("test", "spec")
_CONFIG_NAMES = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "setup.cfg",
        "cargo.toml",
        "go.mod",
        "makefile",
        "dockerfile",
        ".gitignore",
        "tsconfig.json",
        "requirements.txt",
    }
)


def classify_file_role(relative_posix: str) -> FileRole:
    """Name/structure-based role guess. Pure function of the path string."""
    lowered = relative_posix.lower()
    name = lowered.rsplit("/", 1)[-1]
    parts = lowered.split("/")
    if any(p in {"tests", "test", "__tests__", "spec"} for p in parts[:-1]):
        return FileRole.TEST
    if name in _CONFIG_NAMES or name.startswith("."):
        return FileRole.CONFIGURATION
    if any(part in _TEST_HINTS for part in name.replace(".", "_").replace("-", "_").split("_")):
        return FileRole.TEST
    if name.startswith("readme") or lowered.endswith((".md", ".rst")):
        return FileRole.DOCUMENTATION
    import fnmatch as _fnmatch

    if any(_fnmatch.fnmatchcase(lowered, pat) for pat in _DOC_PATTERNS):
        return FileRole.DOCUMENTATION
    if "." + name.rsplit(".", 1)[-1] in _SOURCE_EXTS and "." in name:
        return FileRole.SOURCE
    return FileRole.UNKNOWN
