"""FileIdentity: the strongest safe identity mechanism in SFO.

A filename is NOT an identity. Two files may share a name while being
completely different objects. Identity combines stable filesystem facts
(device, inode), observable state (size, mtime, type) and, when computed,
a content hash. It is used by the scanner, the executor's verification step
and the undo system to confirm that "the file we expected" is still the file
that is actually there.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from sfo.domain.fs_types import FileType


@dataclass(frozen=True, slots=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    modified_at: float
    file_type: FileType
    sha256: str | None = None

    @classmethod
    def from_stat(cls, st: Any, sha256: str | None = None) -> "FileIdentity":
        return cls(
            device=st.st_dev,
            inode=st.st_ino,
            size=st.st_size,
            modified_at=st.st_mtime,
            file_type=FileType.from_mode(st.st_mode),
            sha256=sha256,
        )

    def matches_stat(self, st: Any) -> bool:
        """True when a fresh stat still describes this same object/state."""
        return (
            st.st_dev == self.device
            and st.st_ino == self.inode
            and st.st_size == self.size
            and st.st_mtime == self.modified_at
            and FileType.from_mode(st.st_mode) == self.file_type
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["file_type"] = self.file_type.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileIdentity":
        return cls(
            device=int(data["device"]),
            inode=int(data["inode"]),
            size=int(data["size"]),
            modified_at=float(data["modified_at"]),
            file_type=FileType(data["file_type"]),
            sha256=data.get("sha256"),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str | None) -> "FileIdentity | None":
        if not raw:
            return None
        return cls.from_dict(json.loads(raw))
