"""Several files and folders of the Media panel as one ZIP, streamed.

The archive is written as it is sent — nothing is built on disk first, and
the download starts at once however big the selection. Entries are stored,
not compressed: films, songs and pictures are compressed already, and
deflating them again only costs CPU for nothing.
"""
import zipfile
from pathlib import Path
from typing import Callable, Iterable, Iterator

from api.services.audio_convert import TEMP_PREFIX

CHUNK = 1 << 20


class _Sink:
    """A write-only, non-seekable file that hands what was written on;
    zipfile then marks each entry with a data descriptor instead of
    seeking back to fill in its header."""

    def __init__(self):
        self.parts: list[bytes] = []
        self.pos = 0

    def write(self, b) -> int:
        self.parts.append(bytes(b))
        self.pos += len(b)
        return len(b)

    def tell(self) -> int:
        return self.pos

    def flush(self) -> None:
        pass

    def take(self) -> bytes:
        out = b"".join(self.parts)
        self.parts.clear()
        return out


def entries(roots: Iterable[tuple[Path, str]], allowed: Callable[[Path], bool]) -> list[tuple[Path, str]]:
    """Every file to put in the archive, with its name there: each root
    under its own name, a folder's files under it. `allowed` leaves out
    what this user may not see. Hidden files (a conversion in progress, the
    trash, a folder's own settings) are not part of what was picked."""
    out: list[tuple[Path, str]] = []
    for path, name in roots:
        if path.is_file():
            if allowed(path):
                out.append((path, name))
            continue
        for f in sorted(path.rglob("*")):
            rel = f.relative_to(path)
            if any(p.startswith(".") for p in rel.parts) or f.name.startswith(TEMP_PREFIX):
                continue
            if f.is_file() and allowed(f):
                out.append((f, f"{name}/{rel.as_posix()}"))
    return out


def stream(files: list[tuple[Path, str]]) -> Iterator[bytes]:
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for path, name in files:
            try:
                src = path.open("rb")
            except OSError:
                continue  # gone since it was listed
            with src, zf.open(zipfile.ZipInfo.from_file(path, name), "w", force_zip64=True) as dst:
                while chunk := src.read(CHUNK):
                    dst.write(chunk)
                    yield sink.take()
            yield sink.take()
    yield sink.take()
