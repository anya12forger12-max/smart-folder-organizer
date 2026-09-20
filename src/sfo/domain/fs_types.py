"""Filesystem entry types used across scanner, analysis and planning."""

from __future__ import annotations

import stat
from enum import Enum


class FileType(str, Enum):
    """Conservative classification of a filesystem entry.

    Symlinks are their own type: they are never silently treated as the
    object they point to.  ``MISSING`` marks entries that vanished between
    listing and inspection.
    """

    REGULAR_FILE = "REGULAR_FILE"
    DIRECTORY = "DIRECTORY"
    SYMLINK = "SYMLINK"
    SOCKET = "SOCKET"
    FIFO = "FIFO"
    BLOCK_DEVICE = "BLOCK_DEVICE"
    CHAR_DEVICE = "CHAR_DEVICE"
    OTHER = "OTHER"
    MISSING = "MISSING"

    @classmethod
    def from_mode(cls, mode: int) -> "FileType":
        if stat.S_ISLNK(mode):
            return cls.SYMLINK
        if stat.S_ISDIR(mode):
            return cls.DIRECTORY
        if stat.S_ISREG(mode):
            return cls.REGULAR_FILE
        if stat.S_ISSOCK(mode):
            return cls.SOCKET
        if stat.S_ISFIFO(mode):
            return cls.FIFO
        if stat.S_ISBLK(mode):
            return cls.BLOCK_DEVICE
        if stat.S_ISCHR(mode):
            return cls.CHAR_DEVICE
        return cls.OTHER

    @property
    def is_special(self) -> bool:
        return self in {
            FileType.SOCKET,
            FileType.FIFO,
            FileType.BLOCK_DEVICE,
            FileType.CHAR_DEVICE,
            FileType.OTHER,
        }
