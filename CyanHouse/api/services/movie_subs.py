"""Subtitles the user uploaded, and the index tying them to a film.

Deliberately stored outside the film library: the movie folders stay exactly
as they were found, and everything this feature creates lives under
``MOVIES_DATA_DIR`` instead. That only works if a film can be recognised
again later without relying on where it sits, hence the fingerprint in
``movies.fingerprint`` — rename the file or reorganise the folders and the
subtitles you uploaded still find their way back to it.

Layout::

    <MOVIES_DATA_DIR>/
        subtitles.json                  the index, keyed by fingerprint
        subtitles/<fingerprint>/<id>.srt

The index is small (one entry per film you have uploaded something for) and
rewritten atomically on every change, so a crash mid-write cannot leave it
truncated — the worst case is losing the last edit, not the file.
"""
import json
import os
import threading
import time
import uuid
from pathlib import Path

from api.config import (
    MOVIES_DATA_DIR,
    MOVIES_SUB_IMAGE_MAX_BYTES,
    MOVIES_SUB_MAX_BYTES,
)

# Text subtitles: one file, re-encoded to UTF-8 on the way in.
TEXT_EXT = {".srt", ".ass", ".ssa", ".vtt"}
# Bitmap subtitles that are self-contained: Blu-ray PGS.
IMAGE_EXT = {".sup"}
# VobSub is the awkward one — two files that are one subtitle. The .idx holds
# the index, the timings, the palette and the canvas size; the .sub holds the
# bitmaps. ffmpeg is pointed at the .idx and finds the .sub beside it by name,
# which is why the pair is stored under a shared stem below.
VOBSUB_IDX, VOBSUB_SUB = ".idx", ".sub"
ALLOWED_EXT = TEXT_EXT | IMAGE_EXT | {VOBSUB_IDX, VOBSUB_SUB}

_lock = threading.Lock()


class SubtitleError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _root() -> Path:
    path = MOVIES_DATA_DIR.resolve()
    (path / "subtitles").mkdir(parents=True, exist_ok=True)
    return path


def _index_path() -> Path:
    return _root() / "subtitles.json"


def _load() -> dict:
    try:
        data = json.loads(_index_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "movies": {}}
    except Exception as e:
        # Never throw away a file we failed to parse — a stale index is
        # recoverable by hand, an overwritten one isn't.
        print(f"movies: subtitle index unreadable ({e}); starting a new one")
        return {"version": 1, "movies": {}}
    data.setdefault("version", 1)
    data.setdefault("movies", {})
    return data


def _save(data: dict) -> None:
    path = _index_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)  # atomic: readers see either the old file or the new one


def for_movie(fingerprint: str) -> list[dict]:
    """Every subtitle uploaded for this film, oldest first."""
    with _lock:
        entry = _load()["movies"].get(fingerprint)
    return list(entry.get("subtitles", [])) if entry else []


def _group(files: list[tuple[str, bytes]]) -> list[dict]:
    """Turn the uploaded files into subtitle tracks.

    Everything is one file per track except VobSub, where the .idx and .sub
    sharing a stem are one track. A half of a pair on its own is an error
    worth naming: silently accepting it would produce a track that appears in
    the list and renders nothing."""
    by_ext: dict[str, list[tuple[str, bytes]]] = {}
    for name, data in files:
        ext = Path(name or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            raise SubtitleError(
                f"{ext or Path(name).name!r} isn't a subtitle format this can render "
                f"({', '.join(sorted(TEXT_EXT | IMAGE_EXT))}, or an .idx + .sub pair)",
                415,
            )
        by_ext.setdefault(ext, []).append((name, data))

    groups: list[dict] = []
    idx = {Path(n).stem.lower(): (n, d) for n, d in by_ext.pop(VOBSUB_IDX, [])}
    sub = {Path(n).stem.lower(): (n, d) for n, d in by_ext.pop(VOBSUB_SUB, [])}
    for stem in sorted(set(idx) | set(sub)):
        if stem not in idx:
            raise SubtitleError(
                f"{sub[stem][0]} needs its .idx as well — a .sub alone has no index "
                f"or timings. Select both files.", 400)
        if stem not in sub:
            raise SubtitleError(
                f"{idx[stem][0]} needs its .sub as well — an .idx alone has no "
                f"images. Select both files.", 400)
        groups.append({"kind": "image", "primary": idx[stem], "aux": sub[stem]})

    for ext, items in by_ext.items():
        for name, data in items:
            groups.append({
                "kind": "text" if ext in TEXT_EXT else "image",
                "primary": (name, data), "aux": None,
            })
    if not groups:
        raise SubtitleError("no subtitle files in that upload")
    return groups


def add(fingerprint: str, title: str, rel_path: str,
        files: list[tuple[str, bytes]]) -> list[dict]:
    """Store one or more uploaded subtitles and link them to the film."""
    groups = _group(files)
    folder = _root() / "subtitles" / fingerprint
    folder.mkdir(parents=True, exist_ok=True)

    records = []
    for group in groups:
        name, data = group["primary"]
        ext = Path(name).suffix.lower()
        total = len(data) + (len(group["aux"][1]) if group["aux"] else 0)
        if not total:
            raise SubtitleError(f"{Path(name).name} is empty")
        cap = MOVIES_SUB_MAX_BYTES if group["kind"] == "text" else MOVIES_SUB_IMAGE_MAX_BYTES
        if total > cap:
            raise SubtitleError(
                f"{Path(name).name} is {total // (1024 * 1024)} MB — too large "
                f"for a subtitle ({cap // (1024 * 1024)} MB limit)", 413)

        sub_id = uuid.uuid4().hex[:12]
        if group["kind"] == "text":
            # Decoded here rather than inside ffmpeg, where a binary file
            # surfaces as a stalled stream instead of a message, and written
            # back as UTF-8 so the render path never guesses an encoding.
            text = _decode(data)
            if not text.strip():
                raise SubtitleError(f"{Path(name).name} has no text in it")
            (folder / f"{sub_id}{ext}").write_text(text, encoding="utf-8")
        else:
            # Bitmap payloads are binary; byte-exact or not at all.
            (folder / f"{sub_id}{ext}").write_bytes(data)

        record = {
            "id": sub_id,
            "file": f"{sub_id}{ext}",
            "kind": group["kind"],
            "name": Path(name).name,
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "bytes": total,
        }
        if group["aux"]:
            # Same stem on purpose: the vobsub demuxer finds the .sub by
            # replacing the .idx's extension, so renaming them apart would
            # break the pair.
            (folder / f"{sub_id}{VOBSUB_SUB}").write_bytes(group["aux"][1])
            record["aux"] = f"{sub_id}{VOBSUB_SUB}"
        records.append(record)

    with _lock:
        index = _load()
        entry = index["movies"].setdefault(fingerprint, {"subtitles": []})
        # Kept for humans reading the index by hand; the fingerprint is what
        # actually resolves the link, so these going stale costs nothing.
        entry["title"] = title
        entry["path"] = rel_path
        entry["subtitles"].extend(records)
        _save(index)
    return records


def remove(fingerprint: str, sub_id: str) -> None:
    with _lock:
        index = _load()
        entry = index["movies"].get(fingerprint)
        if not entry:
            raise SubtitleError("no uploaded subtitles for that film", 404)
        keep = [s for s in entry.get("subtitles", []) if s["id"] != sub_id]
        if len(keep) == len(entry.get("subtitles", [])):
            raise SubtitleError("no such subtitle", 404)
        gone = [s for s in entry["subtitles"] if s["id"] == sub_id][0]
        entry["subtitles"] = keep
        if not keep:
            index["movies"].pop(fingerprint, None)
        _save(index)
    for name in (gone.get("file"), gone.get("aux")):
        if not name:
            continue
        try:
            (_root() / "subtitles" / fingerprint / name).unlink()
        except OSError:
            pass  # index is the source of truth; an orphaned file is harmless


def path_for(fingerprint: str, record: dict) -> Path:
    return _root() / "subtitles" / fingerprint / record["file"]


def _decode(data: bytes) -> str:
    """Subtitles in the wild are rarely UTF-8. Try the encodings that actually
    turn up, in the order that avoids mojibake: UTF-8 first (with BOM
    handling), then the Windows codepage most European subs were saved in."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")
