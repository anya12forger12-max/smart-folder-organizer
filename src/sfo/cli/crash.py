"""Bounded local crash records for unexpected exceptions.

SFO has no telemetry: when an unexpected error escapes a command handler,
the only durable evidence is a local record in the private state directory
(0600 files under data_dir/crashes). Records are bounded - the newest
_MAX_RECORDS are kept - so repeated failures cannot grow storage without
limit. Paths may appear inside argv/message fields; that is the same
sensitivity class journals already hold, protected by the same permissions.
"""

from __future__ import annotations

import json
import os
import platform
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from sfo import __version__

MAX_RECORDS = 10
_MAX_MESSAGE = 400
_MAX_TRACEBACK = 2400


def crashes_dir(state_dir: Path) -> Path:
    return state_dir / "crashes"


def record_crash(state_dir: Path, argv: list[str], exc: BaseException) -> Path:
    """Persist one crash record; returns its path. May raise OSError."""
    directory = crashes_dir(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)

    trace_tail = "".join(traceback.format_exception(exc)[-8:])
    record = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": __version__,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "argv": [str(a) for a in argv],
        "exception_type": type(exc).__name__,
        "message": str(exc)[:_MAX_MESSAGE],
        "traceback_tail": trace_tail[-_MAX_TRACEBACK:],
    }
    path = directory / f"{time.time_ns()}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    _prune(directory)
    return path


def recent_crashes(state_dir: Path) -> list[Path]:
    directory = crashes_dir(state_dir)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def _prune(directory: Path) -> None:
    for old in sorted(directory.glob("*.json"))[:-MAX_RECORDS]:
        try:
            old.unlink()
        except OSError:
            pass  # best effort; bounded growth is restored on next prune
