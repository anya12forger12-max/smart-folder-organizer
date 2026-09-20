"""Bounded file-type detection.

Extension labels come from Python's mimetypes table; content labels come
from reading AT MOST a few KB of the file header. Nothing here executes,
extracts or modifies anything - the only filesystem interaction is a
read-only binary open of a bounded prefix, which is exactly what the
inspection layer is allowed to do. (The stricter FileSystem mutation-
boundary interface governs organization machinery; this module never
mutates and never feeds data back into execution decisions.)
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

HEADER_BYTES = 16
TEXT_PROBE_BYTES = 1024

# Extensions treated as safe-to-preview text even when sniffing is unsure.
TEXT_EXTENSIONS = frozenset(
    {
        ".txt", ".md", ".rst", ".log", ".csv", ".json", ".toml", ".yaml",
        ".yml", ".ini", ".cfg", ".conf", ".py", ".js", ".ts", ".sh",
        ".html", ".css", ".xml", ".c", ".h", ".cpp", ".rs", ".go", ".java",
    }
)


@dataclass(frozen=True, slots=True)
class SniffResult:
    label: str          # human description, e.g. "PDF document"
    mime: str | None    # best-effort MIME, None when unknown
    is_text: bool       # safe to show a text preview


def _match_magic(header: bytes) -> SniffResult | None:
    checks: tuple[tuple[bytes, str, str], ...] = (
        (b"%PDF-", "PDF document", "application/pdf"),
        (b"\x7fELF", "ELF binary", "application/x-executable"),
        (b"\x89PNG", "PNG image", "image/png"),
        (b"\xff\xd8\xff", "JPEG image", "image/jpeg"),
        (b"GIF87a", "GIF image", "image/gif"),
        (b"GIF89a", "GIF image", "image/gif"),
        (b"SQLite format 3\x00", "SQLite database", "application/x-sqlite3"),
        (b"{\\rtf", "RTF document", "application/rtf"),
        (b"\x1f\x8b", "gzip archive", "application/gzip"),
        (b"BZh", "bzip2 archive", "application/x-bzip2"),
        (b"7z\xbc\xaf\x27\x1c", "7-Zip archive", "application/x-7z-compressed"),
        (b"OggS", "OGG media", "audio/ogg"),
        (b"fLaC", "FLAC audio", "audio/flac"),
        (b"ID3", "MP3 audio", "audio/mpeg"),
    )
    for magic, label, mime in checks:
        if header.startswith(magic):
            return SniffResult(label, mime, is_text=False)
    if header.startswith(b"PK\x03\x04"):
        return SniffResult("ZIP-based archive or document", "application/zip", False)
    if header.startswith(b"#!"):
        return SniffResult("script", "text/x-script", True)
    return None


def sniff(path: Path) -> SniffResult | None:
    """Content-based type guess from a bounded header read, or None if the
    file cannot be read (permission, special file, vanished, ...)."""
    try:
        with open(path, "rb") as handle:  # read-only, bounded
            header = handle.read(max(HEADER_BYTES, TEXT_PROBE_BYTES))
    except OSError:
        return None
    if not header:
        return SniffResult("empty file", None, True)
    magic = _match_magic(header[:HEADER_BYTES])
    if magic is not None:
        return magic
    probe = header[:TEXT_PROBE_BYTES]
    if b"\x00" not in probe:
        try:
            probe.decode("utf-8")
            return SniffResult("text", "text/plain", True)
        except UnicodeDecodeError:
            pass
    return SniffResult("binary data", "application/octet-stream", False)


def describe_extension(path: Path) -> tuple[str, str | None]:
    """(label, mime) derived from the extension only."""
    mime, _encoding = mimetypes.guess_type(path.name)
    suffix = path.suffix.lower()
    if mime:
        top = mime.split("/")[0]
        pretty = {
            "text": "text file",
            "image": "image",
            "video": "video",
            "audio": "audio",
            "application": None,
        }.get(top)
        if pretty:
            return pretty, mime
        named = {
            "application/pdf": "PDF document",
            "application/zip": "ZIP archive",
            "application/json": "JSON data",
        }
        return named.get(mime, f"{suffix.lstrip('.') or 'unknown'} file"), mime
    return (f"{suffix.lstrip('.') or 'unknown'} file" if suffix else "no extension"), None
