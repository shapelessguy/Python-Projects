"""Who may see and change which album of the Images library.

The rule for a folder lives in the folder itself, in a hidden file
(`.cyanhouse.json`), so it goes wherever the folder goes — renamed, moved —
with nothing to keep in step elsewhere:

    {"owner": "webe_m2", "visibility": "shared", "people": {"giulioppis": "see"}}

  * owner — who made the folder (a new folder, or a folder dropped in from
    the computer). The owner of a folder manages it and everything under
    it, and decides who else may.
  * visibility — "public" (everyone with the Media panel sees it), "shared"
    (only the owner and `people`) or "private" (only the owner).
  * people — what others may do there: "see", "add" (put photos in, make
    folders) or "manage" (also rename, move and delete). In a public folder
    it can only raise someone above "see".

A folder with no visibility of its own follows the nearest folder above it
that has one; with none anywhere up to the top, it is public, as every
folder was before these rules. Nobody sees past a rule: there is no admin
over the albums, and `publish` gives nothing here.

At the top of the library everyone may add: anyone can start an album
there, and it is theirs.
"""
import json
import os
import threading
from pathlib import Path

from api.auth import USERS, visible_panels
from api.config import IMAGE_DIR

SIDE = ".cyanhouse.json"
LEVELS = ("none", "see", "add", "manage")
MODES = ("public", "shared", "private")

_cache: dict[str, tuple[float, dict | None]] = {}
_lock = threading.Lock()


class AccessError(Exception):
    def __init__(self, message: str, status_code: int = 403):
        super().__init__(message)
        self.status_code = status_code


def _rank(level: str | None) -> int:
    return LEVELS.index(level) if level in LEVELS else 0


def _dir(rel: str) -> Path:
    return IMAGE_DIR / rel if rel else IMAGE_DIR


def _rule(rel: str) -> dict | None:
    """The rule file of one folder, if it has one — read again only when it
    changed."""
    side = _dir(rel) / SIDE
    try:
        mtime = side.stat().st_mtime
    except OSError:
        return None
    key = str(side)
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else None
    except (OSError, ValueError):
        data = None
    with _lock:
        _cache[key] = (mtime, data)
    return data


def _chain(folder: str) -> list[tuple[str, dict]]:
    """The rules from the top of the library down to `folder`, inclusive."""
    parts = [p for p in folder.split("/") if p]
    out = []
    for i in range(len(parts) + 1):
        rel = "/".join(parts[:i])
        r = _rule(rel)
        if r:
            out.append((rel, r))
    return out


def access(user: str, folder: str) -> dict:
    """What `user` may do in `folder` (a folder of the library, "" the top),
    and what the folder is: its mode, its owner, where its visibility comes
    from, and whether this user may change it."""
    chain = _chain(folder)
    owners = [r.get("owner") for _, r in chain if r.get("owner")]
    vis = next(((rel, r) for rel, r in reversed(chain) if r.get("visibility") in MODES), None)
    mode = vis[1]["visibility"] if vis else "public"
    people = (vis[1].get("people") or {}) if vis else {}
    mine = people.get(user)
    if mode == "public":
        level = "add" if not folder else "see"
        if _rank(mine) > _rank(level):
            level = mine
    elif mode == "shared":
        level = mine if mine in LEVELS else "none"
    else:
        level = "none"
    # An owner manages their folder and everything under it.
    manages = user in owners
    if manages:
        level = "manage"
    return {
        "mode": mode,
        "owner": owners[-1] if owners else None,
        "level": level,
        # Where the visibility is set: here, or inherited from a folder above.
        "from": vis[0] if vis else None,
        "can_share": bool(folder) and manages,
    }


def can(user: str, path: str, need: str, *, cache: dict | None = None) -> bool:
    """Whether `user` has at least `need` on `path`: a folder is judged by
    its own rule, a file by its folder's."""
    p = _dir(path)
    folder = path if (not path or p.is_dir()) else os.path.dirname(path)
    if cache is not None:
        if folder not in cache:
            cache[folder] = access(user, folder)
        a = cache[folder]
    else:
        a = access(user, folder)
    return _rank(a["level"]) >= _rank(need)


def require(user: str, path: str, need: str) -> None:
    if not can(user, path, need):
        what = {"see": "see", "add": "add to", "manage": "change"}[need]
        # "Not found" for what the user may not even see: a private album's
        # name is not something to confirm to them.
        raise AccessError(f"not permitted to {what} that", 404 if need == "see" else 403)


def filter_listing(user: str, files: list[dict]) -> list[dict]:
    """A browse() listing of the library narrowed to what `user` may see,
    each folder carrying its `access` — the panel shows the lock and offers
    Sharing from it."""
    cache: dict[str, dict] = {}
    out = []
    for f in files:
        is_folder = f.get("kind") == "folder"
        folder = f["path"] if is_folder else f.get("folder", "")
        if folder not in cache:
            cache[folder] = access(user, folder)
        a = cache[folder]
        if _rank(a["level"]) < _rank("see"):
            continue
        if is_folder:
            f = {**f, "access": a}
        out.append(f)
    return out


def claim(folder: str, user: str) -> None:
    """`user` made `folder`: it is theirs. Its visibility is left to follow
    the folder it is in until the owner says otherwise."""
    side = _dir(folder) / SIDE
    if not folder or side.exists():
        return
    side.write_text(json.dumps({"owner": user}, indent=2), encoding="utf-8")


def rule_here(folder: str) -> dict:
    return dict(_rule(folder) or {})


def set_rule(user: str, folder: str, visibility: str | None, people: dict[str, str]) -> dict:
    """Change who may see `folder`: only its owner (or the owner of a folder
    above it) may. `visibility` None goes back to following the
    folder above."""
    if not folder or not _dir(folder).is_dir():
        raise AccessError("that is not a folder of the library", 404)
    if not access(user, folder)["can_share"]:
        raise AccessError("only the folder's owner can change who sees it")
    if visibility is not None and visibility not in MODES:
        raise AccessError(f"visibility is one of {', '.join(MODES)}", 400)
    known = set(users())
    clean = {}
    for name, level in (people or {}).items():
        if name not in known:
            raise AccessError(f"no user called {name!r}", 400)
        if level not in ("see", "add", "manage"):
            raise AccessError("a person's access is see, add or manage", 400)
        clean[name] = level
    rule = rule_here(folder)
    rule.pop("visibility", None)
    rule.pop("people", None)
    if visibility is not None:
        rule["visibility"] = visibility
        if clean:
            rule["people"] = clean
    side = _dir(folder) / SIDE
    if rule:
        side.write_text(json.dumps(rule, indent=2), encoding="utf-8")
    elif side.exists():
        side.unlink()
    return access(user, folder)


def users() -> list[str]:
    """Everyone who can open the Media panel — who a folder can be shared with."""
    out = []
    for name in USERS:
        vis = visible_panels(name)
        if vis is None or "movies" in vis:
            out.append(name)
    return sorted(out)
