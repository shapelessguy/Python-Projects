"""Resumable uploads into a browsable folder — the server half of tus 1.0.0.

Why a protocol rather than a plain multipart POST: the files that belong in
these folders are films. A 40 GB upload over a home connection will be
interrupted — a dropped wifi link, a closed laptop, a proxy timeout — and the
only acceptable answer to that is to carry on from where it stopped. tus is
the standard for exactly this, `tus-js-client` implements the client side,
and the server side is four methods:

    POST   /api/uploads            create; replies Location: .../<id>
    HEAD   /api/uploads/<id>       how many bytes are already here
    PATCH  /api/uploads/<id>       append at Upload-Offset, reply the new one
    DELETE /api/uploads/<id>       give up on it

Everything the client needs to resume is derived from the file on disk, so
a restart of this process loses nothing: the offset *is* the partial file's
size, not a number remembered somewhere.

Where the bytes land
--------------------
The partial is written inside the destination folder, hidden
(``.<name>.cyanpart-<id>``), so finishing it is a rename on the same
filesystem rather than a 40 GB copy from a scratch directory on another
disk. The listing skips dotfiles, so an upload in flight — or one abandoned
half-done — stays out of the way until the sweeper removes it.
"""
import base64
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from api.config import MOVIES_DATA_DIR
from api.services import movie_prep

# One PATCH body is held in memory while it is written, so this is a memory
# cap as much as a protocol one: the client picks the chunk size, and both a
# client asking to send 2 GB in one PATCH (which defeats resuming) and one
# asking this process to hold 2 GB (which defeats everything else) are
# refused. The SPA asks for 8 MB.
MAX_CHUNK_BYTES = 32 * 1024 * 1024
# Nothing here is a film if it is bigger than this. A guard against a typo in
# Upload-Length reserving something absurd, not a policy.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024 * 1024
# A partial nobody has touched in this long is abandoned. Long enough to
# survive a night of "I will finish it tomorrow".
STALE_SECONDS = 7 * 24 * 3600

TUS_VERSION = "1.0.0"

_lock = threading.Lock()


class UploadError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _state_dir() -> Path:
    path = MOVIES_DATA_DIR.resolve() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(upload_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", upload_id or ""):
        raise UploadError("no such upload", 404)
    return _state_dir() / f"{upload_id}.json"


def _read_state(upload_id: str) -> dict:
    try:
        return json.loads(_state_path(upload_id).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UploadError("no such upload", 404)
    except Exception as e:
        raise UploadError(f"upload state unreadable: {e}", 410)


def _write_state(upload_id: str, state: dict) -> None:
    path = _state_path(upload_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ── names ────────────────────────────────────────────────────────────────
# A dropped folder arrives as a set of files carrying their path *inside*
# that folder ("Subs/eng.srt"). That path is client-supplied, so every
# segment is checked rather than trusted: this is the one place where a
# string from a browser turns into a place on this filesystem.
_BAD_CHARS = set('\\:*?"<>|')


def _safe_segments(rel_path: str) -> list[str]:
    parts = []
    for raw in (rel_path or "").replace("\\", "/").split("/"):
        name = raw.strip()
        if not name or name == ".":
            continue
        # Tested before the trailing dots come off: ".." rstripped of its
        # dots is the empty string, which read as "nothing here, skip it" --
        # so a path full of them quietly lost its segments instead of being
        # refused. It never escaped (the containment check below is what
        # actually guarantees that), but silently writing somewhere other
        # than what was asked for is its own kind of wrong.
        if name == ".." or name.startswith("."):
            raise UploadError(f"{raw!r} is not a name this will write")
        name = name.rstrip(".")
        if not name:
            raise UploadError(f"{raw!r} is not a name this will write")
        if set(name) & _BAD_CHARS or any(ord(c) < 32 for c in name):
            raise UploadError(f"{raw!r} contains characters a filename cannot carry")
        if len(name.encode("utf-8")) > 255:
            raise UploadError(f"{raw!r} is too long for a filename")
        parts.append(name)
    if not parts:
        raise UploadError("the upload has no filename")
    return parts


def decode_metadata(header: str) -> dict[str, str]:
    """tus sends metadata as `key <base64>,key <base64>` — and a key with no
    value at all, which is legal and means the empty string."""
    out: dict[str, str] = {}
    for pair in (header or "").split(","):
        pair = pair.strip()
        if not pair:
            continue
        key, _, encoded = pair.partition(" ")
        if not key:
            continue
        try:
            out[key] = base64.b64decode(encoded).decode("utf-8") if encoded else ""
        except Exception:
            raise UploadError(f"metadata {key!r} is not valid base64")
    return out


# ── the four operations ──────────────────────────────────────────────────
def create(area: str, folder: str, rel_path: str, length: int) -> dict:
    """Reserve an upload. Everything that can be refused is refused here,
    before a single byte crosses the wire — the worst possible moment to
    discover the name is taken is after 40 GB of it."""
    if length < 0 or length > MAX_UPLOAD_BYTES:
        raise UploadError("that upload is larger than this accepts", 413)

    # Raises if the area is unknown or the folder is not in it.
    dest_dir = movie_prep.resolve_entry(area, folder)
    if not dest_dir.is_dir():
        raise UploadError("the destination is not a folder", 400)

    segments = _safe_segments(rel_path)
    target = dest_dir.joinpath(*segments)
    # The segments are checked, so they cannot climb out on their own — but a
    # folder inside the area may be a symlink pointing anywhere, so the
    # result is tested for containment like every other path here.
    root, _ = movie_prep.area(area)
    root = root.resolve()
    parent = target.parent.resolve()
    if root != parent and root not in parent.parents:
        raise UploadError("that destination is outside the folder", 403)
    if target.exists():
        raise UploadError(f"{target.name!r} is already in that folder", 409)

    upload_id = uuid.uuid4().hex
    # The subfolders of a dropped folder are made now, so the tree appears as
    # it is being filled rather than all at once at the end.
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.parent / f".{target.name}.cyanpart-{upload_id}"
    part.touch()
    state = {
        "id": upload_id,
        "area": area,
        "folder": folder,
        "rel_path": "/".join(segments),
        "target": str(target),
        "part": str(part),
        "length": length,
        "created": time.time(),
    }
    _write_state(upload_id, state)
    return state


def area_of(upload_id: str) -> str:
    """Which folder an upload is going into — what its permission is judged
    against on every chunk, not just when it was created."""
    return _read_state(upload_id).get("area", "")


def offset(upload_id: str) -> tuple[int, dict]:
    """How much is already here. Taken from the file, never from a counter:
    a number in a sidecar can disagree with the bytes, and the bytes win."""
    state = _read_state(upload_id)
    part = Path(state["part"])
    if not part.exists():
        raise UploadError("that upload has been finished or removed", 410)
    return part.stat().st_size, state


def append(upload_id: str, at: int, chunks) -> dict:
    """Append one chunk. `chunks` is an iterable of bytes — the request body
    streamed, not buffered: these are films, and holding a chunk of one in
    memory to write it out again is pure waste."""
    with _lock:
        current, state = offset(upload_id)
        if at != current:
            # tus says 409 here, and the client re-reads the offset and
            # carries on from it. This is the normal shape of a retry, not
            # an error worth logging loudly.
            raise UploadError(f"expected offset {current}", 409)
        part = Path(state["part"])
        written = 0
        with open(part, "r+b") as fh:
            fh.seek(current)
            for chunk in chunks:
                if not chunk:
                    continue
                written += len(chunk)
                if current + written > state["length"]:
                    fh.truncate(current)
                    raise UploadError("that is more than the declared length", 400)
                fh.write(chunk)
            fh.flush()
            os.fsync(fh.fileno())
        state["offset"] = current + written
        state["touched"] = time.time()
        _write_state(upload_id, state)
        if state["offset"] >= state["length"]:
            _finish(state)
        return state


def _finish(state: dict) -> None:
    """Rename into place. Same directory, so it is atomic and instant even
    for a 40 GB file — the whole reason the partial was written here."""
    part, target = Path(state["part"]), Path(state["target"])
    if target.exists():
        # Something else claimed the name while this was uploading. The
        # bytes are kept, under a name that says what happened.
        alt = target.with_name(f"{target.stem} (uploaded {time.strftime('%H-%M-%S')}){target.suffix}")
        target = alt
        state["target"] = str(alt)
    os.replace(part, target)
    state["done"] = True
    state["finished"] = time.time()
    _write_state(state["id"], state)
    movie_prep._bump()   # the panel refreshes on this, same as a move


def terminate(upload_id: str) -> None:
    state = _read_state(upload_id)
    part = Path(state["part"])
    try:
        if part.exists() and not state.get("done"):
            part.unlink()
    except OSError:
        pass
    try:
        _state_path(upload_id).unlink()
    except OSError:
        pass


def sweep() -> int:
    """Drop partials nobody has touched in a week, and the state of uploads
    that finished. Called on startup; cheap enough to be unconditional."""
    removed = 0
    now = time.time()
    for path in _state_dir().glob("*.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            path.unlink(missing_ok=True)
            removed += 1
            continue
        last = state.get("touched") or state.get("finished") or state.get("created", 0)
        if state.get("done"):
            # Nothing to resume; the sidecar is only kept so a client that
            # asks again learns it finished.
            if now - last > 3600:
                path.unlink(missing_ok=True)
                removed += 1
            continue
        if now - last > STALE_SECONDS:
            try:
                Path(state["part"]).unlink(missing_ok=True)
            except (OSError, KeyError):
                pass
            path.unlink(missing_ok=True)
            removed += 1
    return removed
