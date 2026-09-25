"""Small copies of pictures, for the Images tab's gallery.

A gallery of full-size photos would pull megabytes per tile; each picture is
instead scaled once to a few widths (ffmpeg, which the server already has
for films) and kept on disk. A copy is keyed by the picture's path, size and
time, so an edited or replaced picture gets a fresh one, and a GIF shows its
first frame.
"""
import hashlib
import subprocess
import threading
from pathlib import Path

from api.config import API_DATA_DIR, FFMPEG
from api.services import movie_prep
from api.services.movie_prep import PrepError

THUMB_DIR = API_DATA_DIR / "thumbs"
# The widths asked for are rounded up to one of these, so a size slider
# does not make a new copy for every pixel.
WIDTHS = (240, 400, 640, 960)
_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()
# How many ffmpeg runs make thumbnails at once. A first scroll through
# thousands of photos asks for them all together; the rest wait their turn
# rather than starting dozens of ffmpegs and taking every CPU.
_working = threading.BoundedSemaphore(3)


def thumbnail(area_name: str, rel: str, width: int) -> Path:
    """A JPEG of a picture in a browsable folder, at least `width` pixels
    wide (or as it is, when it is smaller)."""
    path = movie_prep.resolve_in_area(area_name, rel)
    if movie_prep.file_kind(path) != "image" or not path.is_file():
        raise PrepError("not a picture", 400)
    return scaled(path, width)


def scaled(path: Path, width: int) -> Path:
    """A JPEG copy of the picture at `path`, made the first time it is
    asked for. The caller has checked the path is one it may show."""
    w = next((x for x in WIDTHS if x >= width), WIDTHS[-1])
    st = path.stat()
    key = hashlib.sha1(f"{path}|{st.st_size}|{int(st.st_mtime)}|{w}".encode()).hexdigest()
    out = THUMB_DIR / key[:2] / f"{key}.jpg"
    if out.is_file():
        return out
    with _locks_lock:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        if out.is_file():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.jpg")
        with _working:
            r = subprocess.run(
                [FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(path), "-frames:v", "1",
                 # Never larger than the picture; keeps its shape.
                 "-vf", f"scale='min({w},iw)':-2", "-q:v", "4", str(tmp)],
                capture_output=True, text=True, timeout=60)
        if r.returncode or not tmp.is_file():
            tmp.unlink(missing_ok=True)
            raise PrepError(f"could not make a thumbnail: {r.stderr.strip()[:200]}", 500)
        tmp.replace(out)
    with _locks_lock:
        _locks.pop(key, None)
    return out
