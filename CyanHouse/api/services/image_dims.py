"""How big each picture is — so a gallery can draw every tile at its final
shape before a single thumbnail has arrived, instead of tiles growing and
the page jumping as they load.

Kept in a small SQLite database (path, size, time, width, height), in step
with the Images folder however things got there — the panel, a copy over
the network, a script, a drive plugged back in:

  * the kernel says when something in the folder changes (inotify, one watch
    per folder, new folders watched as they appear), and that sets a
    `changed` flag in the database;
  * a loop waits for the flag, lets a burst of changes settle (a copy of a
    thousand photos is one scan, not a thousand), then walks the folder —
    names, sizes and times only — reads the header of each picture that is
    new or changed, once, forgets the ones that are gone, and clears the
    flag. The panel is then told, and the listing it asks for carries the
    sizes (movie_prep.browse);
  * nothing is watching while the API is down, so it scans once when it
    starts (the flag is kept in the database, so one set just before a
    restart is not lost either); a drive that goes away takes its watches
    with it, so they are armed again when it is back; and a slow safety scan
    runs now and then in case anything slipped past.

Sizes are read from the files' headers (a few KB each, no decoding, no
Pillow): JPEG, PNG, GIF, WebP and BMP. A JPEG's EXIF orientation is
honoured — a phone photo taken upright is stored sideways with a flag
saying so, and is shown (and thumbnailed) upright, so its width and height
are swapped here.
"""
import os
import sqlite3
import time
import struct
import threading
from pathlib import Path

from api.config import API_DATA_DIR, IMAGE_DIR
from api.services import fs_watch

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
SETTLE = 2.0          # seconds of quiet after a change before scanning
SAFETY = 15 * 60      # a scan at least this often, flag or not

DB = API_DATA_DIR / "images.sqlite"
_db_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _jpeg(f) -> tuple[int, int] | None:
    f.seek(2)
    size, orient = None, 1
    while True:
        b = f.read(1)
        while b and b != b"\xff":
            b = f.read(1)
        while b == b"\xff":
            b = f.read(1)
        if not b:
            break
        marker = b[0]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        head = f.read(2)
        if len(head) < 2:
            break
        length = struct.unpack(">H", head)[0]
        if marker == 0xE1 and orient == 1:           # EXIF: the orientation
            data = f.read(length - 2)
            orient = _exif_orientation(data)
            continue
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            data = f.read(5)
            h, w = struct.unpack(">HH", data[1:5])
            size = (w, h)
            break
        f.seek(length - 2, 1)
    if size and orient in (5, 6, 7, 8):
        size = (size[1], size[0])
    return size


def _exif_orientation(data: bytes) -> int:
    if not data.startswith(b"Exif\x00\x00"):
        return 1
    t = data[6:]
    try:
        end = "<" if t[:2] == b"II" else ">"
        first = struct.unpack(end + "I", t[4:8])[0]
        count = struct.unpack(end + "H", t[first:first + 2])[0]
        for i in range(count):
            e = t[first + 2 + i * 12: first + 14 + i * 12]
            if struct.unpack(end + "H", e[:2])[0] == 0x0112:
                return struct.unpack(end + "H", e[8:10])[0]
    except (struct.error, IndexError):
        pass
    return 1


def _read(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as f:
        head = f.read(32)
        if head[:2] == b"\xff\xd8":
            return _jpeg(f)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        if head[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", head[6:10])
        if head[:2] == b"BM":
            w, h = struct.unpack("<ii", head[18:26])
            return abs(w), abs(h)
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            kind = head[12:16]
            if kind == b"VP8 ":
                w, h = struct.unpack("<HH", head[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if kind == b"VP8L":
                b = head[21:25]
                w = 1 + (((b[1] & 0x3F) << 8) | b[0])
                h = 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
                return w, h
            if kind == b"VP8X":
                w = 1 + int.from_bytes(head[24:27], "little")
                h = 1 + int.from_bytes(f.read(3) if len(head) < 30 else head[27:30], "little")
                return w, h
    return None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB, check_same_thread=False)
        _conn.execute("CREATE TABLE IF NOT EXISTS dims (path TEXT PRIMARY KEY, size INTEGER,"
                      " mtime INTEGER, w INTEGER, h INTEGER)")
        _conn.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER)")
        _conn.commit()
    return _conn


def known(root: Path) -> dict[str, tuple[int, int, int, int]]:
    """Every picture known under `root`: path -> (size, mtime, w, h)."""
    prefix = str(root).rstrip("/") + "/"
    with _db_lock:
        rows = _db().execute("SELECT path, size, mtime, w, h FROM dims WHERE substr(path, 1, ?) = ?",
                             (len(prefix), prefix)).fetchall()
    return {r[0]: r[1:] for r in rows}


def sync(root: Path) -> int:
    """Bring the database in step with the pictures under `root`: read the
    new and changed ones, forget the gone ones. How many rows changed."""
    if not root.is_dir():
        return 0   # the drive is away: keep what is known until it is back
    have = known(root)
    seen: set[str] = set()
    fresh: list[tuple] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # A set: the ntfs3 driver repeats names in a folder being written to.
        dirnames[:] = sorted({d for d in dirnames if not d.startswith(".") and d != ".trash"})
        for name in set(filenames):
            if name.startswith(".") or os.path.splitext(name)[1].lower() not in IMAGE_EXT:
                continue
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            seen.add(path)
            row = have.get(path)
            if row and row[0] == st.st_size and row[1] == int(st.st_mtime):
                continue
            try:
                wh = _read(Path(path)) or (0, 0)
            except OSError:
                wh = (0, 0)
            fresh.append((path, st.st_size, int(st.st_mtime), wh[0], wh[1]))
    gone = [p for p in have if p not in seen]
    if fresh or gone:
        with _db_lock:
            db = _db()
            db.executemany("INSERT OR REPLACE INTO dims VALUES (?, ?, ?, ?, ?)", fresh)
            db.executemany("DELETE FROM dims WHERE path = ?", [(p,) for p in gone])
            db.commit()
    return len(fresh) + len(gone)


def _set_changed(on: bool) -> None:
    with _db_lock:
        db = _db()
        db.execute("INSERT OR REPLACE INTO state VALUES ('changed', ?)", (1 if on else 0,))
        db.commit()


def _is_changed() -> bool:
    with _db_lock:
        row = _db().execute("SELECT value FROM state WHERE key = 'changed'").fetchone()
    return bool(row and row[0])


_wake = threading.Event()


def _watch_loop() -> None:
    """Arm inotify on the Images folder, and set the flag on every change.
    When the folder goes away (the drive), wait for it and arm again."""
    while True:
        if not IMAGE_DIR.is_dir():
            time.sleep(10)
            continue
        try:
            w = fs_watch.Watch(IMAGE_DIR)
        except OSError as e:
            print(f"image_dims: cannot watch {IMAGE_DIR} ({e}); scanning on a timer only")
            return
        # Whatever happened while nothing was watching.
        _set_changed(True)
        _wake.set()
        try:
            while True:
                changed, lost = w.events(30)
                if changed:
                    _set_changed(True)
                    _wake.set()
                if lost or not IMAGE_DIR.is_dir():
                    break
        finally:
            w.close()
        time.sleep(2)


def _scan_loop() -> None:
    from api.services import movie_prep
    last = 0.0
    while True:
        _wake.wait(SAFETY)
        # Let a burst of changes settle: one scan for a whole copy.
        while _wake.is_set():
            _wake.clear()
            time.sleep(SETTLE)
        if not _is_changed() and time.time() - last < SAFETY:
            continue
        _set_changed(False)   # before the walk: a change during it sets it again
        try:
            if sync(IMAGE_DIR):
                movie_prep._bump()   # the panel lists the folder again, sizes and all
        except Exception as e:   # tried again at the next change, or the next safety scan
            print(f"image_dims: scan failed ({e})")
            _set_changed(True)
        last = time.time()


def nudge() -> None:
    """A listing met a picture the database does not know: scan soon."""
    _set_changed(True)
    _wake.set()


_threads: list[threading.Thread] = []


def start() -> None:
    """Watch the Images folder and keep the sizes in step, in the background."""
    if IMAGE_DIR is None or any(t.is_alive() for t in _threads):
        return
    _set_changed(True)   # the first scan, for what changed while nothing watched
    _wake.set()
    for target, name in ((_watch_loop, "image-dims-watch"), (_scan_loop, "image-dims-scan")):
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        _threads.append(t)
