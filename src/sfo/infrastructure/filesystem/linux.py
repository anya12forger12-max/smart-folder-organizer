"""Linux implementation of the FileSystem abstraction.

Safety notes (security-sensitive):

* ``inspect``/``list_directory`` use lstat semantics: symlinks are reported
  as symlinks and never followed implicitly.
* ``move`` refuses to overwrite. The primary primitive is renameat2 with
  RENAME_NOREPLACE, which is atomic; on kernels/filesystems without support
  we fall back to an existence check plus os.rename. The fallback has a
  theoretical TOCTOU window that RENAME_NOREPLACE closes; this is documented
  in SECURITY.md as a known limitation.
* ``move`` never copies. A cross-device rename raises EXDEV which becomes
  CrossFilesystemMoveError — copy+delete is prohibited by the safety
  contract because deletion does not exist in SFO.
"""

from __future__ import annotations

import ctypes
import errno
import os
import stat
from pathlib import Path

from sfo.domain.fs_types import FileType
from sfo.errors import (
    CrossFilesystemMoveError,
    DestinationExistsError,
    UnsupportedFileTypeError,
)
from sfo.infrastructure.filesystem.interface import (
    FileSystem,
    FileSystemError,
    PathInfo,
)
from sfo.scanning.hashing import sha256_file

_RENAME_NOREPLACE = 1 << 0

# renameat2 syscall numbers for the architectures SFO officially targets.
_SYS_renameat2 = {
    "x86_64": 316,
    "aarch64": 276,
    "armv7l": 382,
    "ppc64le": 357,
    "s390x": 347,
    "riscv64": 276,
}


def _rename_noreplace(source: Path, destination: Path) -> bool:
    """Atomic no-replace rename. Returns False when unsupported."""
    import platform

    nr = _SYS_renameat2.get(platform.machine())
    if nr is None:
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        AT_FDCWD = -100
        result = libc.syscall(
            ctypes.c_long(nr),
            ctypes.c_int(AT_FDCWD),
            ctypes.c_char_p(os.fsencode(source)),
            ctypes.c_int(AT_FDCWD),
            ctypes.c_char_p(os.fsencode(destination)),
            ctypes.c_uint(_RENAME_NOREPLACE),
        )
    except OSError:
        return False
    if result == 0:
        return True
    code = ctypes.get_errno()
    if code == errno.ENOSYS or code == errno.EINVAL or code == errno.EOPNOTSUPP:
        return False
    if code == errno.EEXIST:
        raise DestinationExistsError(f"destination exists: {destination}")
    raise OSError(code, os.strerror(code), str(source), None, str(destination))


class LinuxFileSystem(FileSystem):
    """Read-mostly adapter. Mutations are limited to create_directory/move."""

    def exists(self, path: Path) -> bool:
        return path.exists() or path.is_symlink()

    def inspect(self, path: Path) -> PathInfo:
        try:
            st = path.lstat()
        except FileNotFoundError:
            return PathInfo.missing(path)
        except OSError as exc:
            raise FileSystemError(f"cannot inspect {path}: {exc.strerror}") from exc
        target: str | None = None
        if stat.S_ISLNK(st.st_mode):
            try:
                target = os.readlink(path)
            except OSError:
                target = None
        created = getattr(st, "st_birthtime", None)
        return PathInfo(
            path=path,
            exists=True,
            file_type=FileType.from_mode(st.st_mode),
            size=st.st_size,
            mode=stat.S_IMODE(st.st_mode),
            device=st.st_dev,
            inode=st.st_ino,
            modified_at=st.st_mtime,
            created_at=created,
            accessed_at=st.st_atime,
            symlink_target=target,
        )

    def list_directory(self, path: Path) -> list[Path]:
        try:
            entries = [entry.name for entry in os.scandir(path)]
        except NotADirectoryError as exc:
            raise FileSystemError(f"not a directory: {path}") from exc
        except PermissionError as exc:
            raise FileSystemError(f"permission denied: {path}") from exc
        except FileNotFoundError as exc:
            raise FileSystemError(f"directory disappeared: {path}") from exc
        return sorted(path / name for name in entries)

    def create_directory(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except FileExistsError as exc:
            raise FileSystemError(f"path exists and is not a directory: {path}") from exc
        except PermissionError as exc:
            raise FileSystemError(
                f"cannot create directory {path}: permission denied "
                "(filesystem may be read-only)"
            ) from exc
        except OSError as exc:
            raise FileSystemError(f"cannot create directory {path}: {exc}") from exc

    def move(self, source: Path, destination: Path) -> None:
        info = self.inspect(source)
        if not info.exists:
            raise FileSystemError(f"source disappeared before move: {source}")
        if self.exists(destination):
            raise DestinationExistsError(
                f"refusing to overwrite existing destination: {destination}"
            )
        parent = destination.parent
        if not parent.is_dir():
            self.create_directory(parent)
        if _rename_noreplace(source, destination):
            return
        # Fallback for kernels without renameat2 support.
        try:
            os.rename(source, destination)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise FileSystemError("filesystem is full; nothing was changed") from exc
            if exc.errno == errno.EROFS:
                raise FileSystemError(
                    "filesystem is read-only; nothing was changed"
                ) from exc
            if exc.errno == errno.EXDEV:
                raise CrossFilesystemMoveError(
                    f"{source} and {destination} are on different filesystems; "
                    "SFO will not copy-and-delete"
                ) from exc
            if exc.errno == errno.EACCES or exc.errno == errno.EPERM:
                raise FileSystemError(
                    f"permission denied moving {source}; file left untouched"
                ) from exc
            raise FileSystemError(f"move failed ({exc}); nothing was overwritten") from exc
        # Defensive post-check: rename must not have replaced anything.
        if not destination.exists():
            raise FileSystemError(f"move verification failed for {destination}")

    def hash_file(self, path: Path, algorithm: str = "sha256") -> str:
        info = self.inspect(path)
        if not info.exists:
            raise FileSystemError(f"cannot hash missing file: {path}")
        if info.file_type is FileType.SYMLINK:
            raise UnsupportedFileTypeError(
                f"refusing to hash symlink (target could be outside root): {path}"
            )
        if info.file_type is not FileType.REGULAR_FILE:
            raise UnsupportedFileTypeError(f"refusing to hash special file: {path}")
        return sha256_file(path, algorithm=algorithm)
