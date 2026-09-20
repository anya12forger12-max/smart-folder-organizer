"""Error hierarchy for SFO.

Every error type carries a user-understandable story. The CLI maps these to
friendly messages; internal layers raise them with precise causes.
"""

from __future__ import annotations


class SfoError(Exception):
    """Base class for all expected SFO errors.

    ``details`` carries optional technical context, shown only in --debug
    mode so normal output stays safe for end users.
    """

    def __init__(self, message: str = "", *, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.details = list(details or [])


class UsageError(SfoError):
    """The user asked for something impossible or malformed."""


class ConfigError(SfoError):
    """Local configuration could not be read or is invalid."""


class RuleConfigError(ConfigError):
    """A rule file is invalid. Rules are data; bad data is rejected."""


class SecurityError(SfoError):
    """A safety invariant was about to be violated."""


class PathOutsideRootError(SecurityError):
    """A path escaped the selected root."""


class UnsafePermissionsError(SecurityError):
    """An SFO-owned directory has unsafe permissions or ownership."""


class UnsafeDestinationError(SecurityError):
    """A proposed destination is unsafe (outside root, protected, ...)."""


class DestinationExistsError(SfoError):
    """Refusal to overwrite: the destination already exists."""


class UnsupportedFileTypeError(SfoError):
    """Operation not permitted for this entry type (e.g. hashing a FIFO)."""


class CrossFilesystemMoveError(SfoError):
    """Move would cross filesystems; copy+delete fallback is prohibited."""


class PlanValidationError(SfoError):
    """A plan failed preflight validation and must not execute."""


class StalePlanError(SfoError):
    """The filesystem/rules changed since the plan was generated."""


class JournalError(SfoError):
    """The local operation journal is inconsistent or unwritable."""


class SchemaMismatchError(SfoError):
    """The on-disk database was written by a newer SFO version."""


class ScanCancelled(SfoError):
    """Scanning was interrupted by the user."""


class LockError(SfoError):
    """A required exclusive lock could not be acquired."""
