"""The music library as songs, albums and artists — what the Music tab's
library views are drawn from.

Read from the files themselves: each song's tags (artist, album, title,
track, year — written when it was filed, see music_prep) and the cover.jpg
beside it in its album folder. Nothing depends on Plex.

Tags are read once per file and remembered by (size, mtime), so listing the
library again only reads what changed: ~700 songs take under a second the
first time, next to nothing after.
"""
import threading
from pathlib import Path

import mutagen

from api.config import MUSIC_DIR
from api.services import movie_prep
from api.services.movie_prep import PrepError

_lock = threading.Lock()
_tags: dict[str, tuple] = {}     # path -> ((size, mtime), song dict)


def _first(tags, key: str) -> str:
    try:
        return str((tags.get(key) or [""])[0]).strip()
    except Exception:
        return ""


def _number(s: str) -> int:
    """"6/12" -> 6; "" -> 0."""
    try:
        return int(str(s).split("/")[0])
    except (ValueError, TypeError):
        return 0


def _read(path: Path, rel: str) -> dict:
    audio = mutagen.File(path, easy=True)
    tags = audio if audio is not None and audio.tags is not None else {}
    try:
        seconds = round(float(audio.info.length), 1) if audio is not None else 0
    except Exception:
        seconds = 0
    folder = str(Path(rel).parent) if str(Path(rel).parent) != "." else ""
    title = _first(tags, "title") or path.stem
    artist = _first(tags, "artist")
    album_artist = _first(tags, "albumartist") or artist
    return {
        "path": rel,
        "folder": folder,
        "title": title,
        "artist": artist or album_artist or "Unknown artist",
        "album_artist": album_artist or "Unknown artist",
        "album": _first(tags, "album") or (Path(folder).name if folder else "Unknown album"),
        "track": _number(_first(tags, "tracknumber")),
        "disc": _number(_first(tags, "discnumber")) or 1,
        "year": _first(tags, "date")[:4],
        "seconds": seconds,
        "size": path.stat().st_size,
    }


def songs() -> list[dict]:
    """Every song in the music library, with its tags."""
    if MUSIC_DIR is None or not MUSIC_DIR.is_dir():
        raise PrepError("no music library configured", 404)
    out, present = [], set()
    # A set: the ntfs3 driver repeats names in a folder being written to
    # (UNIQUE_NAMES in movie_prep.py).
    for p in sorted(set(MUSIC_DIR.rglob("*"))):
        rel = p.relative_to(MUSIC_DIR)
        if any(part.startswith(".") for part in rel.parts) or movie_prep.TRASH_DIR in rel.parts:
            continue
        if not p.is_file() or movie_prep.file_kind(p) != "audio":
            continue
        key = str(p)
        present.add(key)
        try:
            st = p.stat()
            sig = (st.st_size, int(st.st_mtime))
            with _lock:
                hit = _tags.get(key)
            if not hit or hit[0] != sig:
                hit = (sig, _read(p, str(rel)))
                with _lock:
                    _tags[key] = hit
            out.append(hit[1])
        except Exception:
            continue
    with _lock:
        for gone in [k for k in _tags if k not in present]:
            _tags.pop(gone, None)
    return out


def library() -> dict:
    """Songs, plus the albums and artists they make up.

    An album is a folder (Artist/Album/…), which is how the inbox files them;
    it carries its cover when the folder has a cover.jpg (or folder.jpg)."""
    tracks = songs()
    albums: dict[str, dict] = {}
    for t in tracks:
        a = albums.setdefault(t["folder"], {
            "folder": t["folder"], "title": t["album"], "artist": t["album_artist"],
            "year": t["year"], "tracks": 0, "seconds": 0, "cover": False,
        })
        a["tracks"] += 1
        a["seconds"] += t["seconds"] or 0
        if t["year"] and (not a["year"] or t["year"] < a["year"]):
            a["year"] = t["year"]
    for a in albums.values():
        folder = MUSIC_DIR / a["folder"]
        a["cover"] = any((folder / n).is_file() for n in ("cover.jpg", "folder.jpg"))
    artists: dict[str, dict] = {}
    for a in albums.values():
        x = artists.setdefault(a["artist"], {"name": a["artist"], "albums": 0, "tracks": 0, "cover": ""})
        x["albums"] += 1
        x["tracks"] += a["tracks"]
        if a["cover"] and not x["cover"]:
            x["cover"] = a["folder"]
    return {
        "songs": tracks,
        "albums": sorted(albums.values(), key=lambda a: (a["artist"].casefold(), a["year"] or "9999", a["title"].casefold())),
        "artists": sorted(artists.values(), key=lambda x: x["name"].casefold()),
    }


def cover(folder: str) -> Path:
    """An album folder's cover image, refusing anything outside the library."""
    if MUSIC_DIR is None:
        raise PrepError("no music library configured", 404)
    root = MUSIC_DIR.resolve()
    target = (root / folder).resolve()
    if target != root and root not in target.parents:
        raise PrepError("outside the music library", 403)
    for name in ("cover.jpg", "folder.jpg"):
        if (target / name).is_file():
            return target / name
    raise PrepError("no cover", 404)
