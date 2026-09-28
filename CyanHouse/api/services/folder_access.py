"""Who may see and change which folder of the shared libraries: Images
(its albums) and Documents. Both follow the same rules, each library on
its own.

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

At the top of the library everyone may add: anyone can start a folder
there, and it is theirs. A file put loose at the top is its uploader's the
same way: the top folder's rule keeps who put each one there
(`"files": {"Taxonomy.md": "cian_cl"}`), and that user manages that file —
nothing else at the top, which stays nobody's.

Every function takes the library by its area key (LIBRARIES).

A folder of Documents may be encrypted -- a vault (VAULT.md): its files
and names are encrypted by the browser or the app, and the server holds
nothing that decrypts them. A vault is private to its owner and stays so;
its vault file (VAULT) sits in its top folder, and everything under that
folder is part of it.
"""
import json
import os
import threading
from pathlib import Path

from api.auth import USERS, visible_panels
from api.config import DOCUMENTS_DIR, IMAGE_DIR

SIDE = ".cyanhouse.json"
VAULT = ".cyanhouse-vault.json"
# Files the server keeps for itself in a folder: never listed, and never
# renamed, moved, deleted or overwritten through the file endpoints.
PROTECTED = {SIDE, VAULT}
VAULT_AREA = ":documents"
# The libraries these rules apply to, by area key (api/services/movie_prep.py).
LIBRARIES = {":images": IMAGE_DIR, ":documents": DOCUMENTS_DIR}
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


def shared(area: str) -> bool:
    """Whether `area` is a library whose folders carry these rules."""
    return LIBRARIES.get(area) is not None


def _dir(area: str, rel: str) -> Path:
    root = LIBRARIES[area]
    return root / rel if rel else root


def _rule(area: str, rel: str) -> dict | None:
    """The rule file of one folder, if it has one — read again only when it
    changed."""
    side = _dir(area, rel) / SIDE
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


def _chain(area: str, folder: str) -> list[tuple[str, dict]]:
    """The rules from the top of the library down to `folder`, inclusive."""
    parts = [p for p in folder.split("/") if p]
    out = []
    for i in range(len(parts) + 1):
        rel = "/".join(parts[:i])
        r = _rule(area, rel)
        if r:
            out.append((rel, r))
    return out


def access(user: str, area: str, folder: str) -> dict:
    """What `user` may do in `folder` (a folder of the library, "" the top),
    and what the folder is: its mode, its owner, where its visibility comes
    from, and whether this user may change it."""
    chain = _chain(area, folder)
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


def top_file_owner(area: str, rel: str) -> str | None:
    """Who put a file loose at the top of the library, if it is one."""
    if not rel or "/" in rel:
        return None
    return ((_rule(area, "") or {}).get("files") or {}).get(rel)


_files_lock = threading.Lock()


def _change_top_files(area: str, change) -> None:
    """Edit the top folder's record of loose files, `change(files)` in place."""
    with _files_lock:
        rule = rule_here(area, "")
        files = dict(rule.get("files") or {})
        change(files)
        if files:
            rule["files"] = files
        else:
            rule.pop("files", None)
        side = _dir(area, "") / SIDE
        if rule:
            side.write_text(json.dumps(rule, indent=2), encoding="utf-8")
        elif side.exists():
            side.unlink()


def claim_file(area: str, rel: str, user: str) -> None:
    """`user` put `rel` at the top of the library: it is theirs. A file in a
    folder follows its folder instead, so nothing is recorded for it."""
    if rel and "/" not in rel:
        _change_top_files(area, lambda files: files.__setitem__(rel, user))


def forget_file(area: str, rel: str) -> None:
    """`rel` is no longer at the top (deleted, or moved into a folder)."""
    if top_file_owner(area, rel) is not None:
        _change_top_files(area, lambda files: files.pop(rel, None))


def renamed_file(area: str, old: str, new: str) -> None:
    """A loose file renamed where it is keeps its owner."""
    owner = top_file_owner(area, old)
    if owner is None or old == new:
        return
    def change(files):
        files.pop(old, None)
        if "/" not in new:
            files[new] = owner
    _change_top_files(area, change)


def can(user: str, area: str, path: str, need: str, *, cache: dict | None = None) -> bool:
    """Whether `user` has at least `need` on `path`: a folder is judged by
    its own rule, a file by its folder's — or, loose at the top, by who put
    it there."""
    p = _dir(area, path)
    folder = path if (not path or p.is_dir()) else os.path.dirname(path)
    if not folder and path and top_file_owner(area, path) == user:
        return True
    if cache is not None:
        if folder not in cache:
            cache[folder] = access(user, area, folder)
        a = cache[folder]
    else:
        a = access(user, area, folder)
    return _rank(a["level"]) >= _rank(need)


def require(user: str, area: str, path: str, need: str) -> None:
    if not can(user, area, path, need):
        what = {"see": "see", "add": "add to", "manage": "change"}[need]
        # "Not found" for what the user may not even see: a private folder's
        # name is not something to confirm to them.
        raise AccessError(f"not permitted to {what} that", 404 if need == "see" else 403)


def filter_listing(user: str, area: str, files: list[dict]) -> list[dict]:
    """A browse() listing of the library narrowed to what `user` may see,
    each folder carrying its `access` — the panel shows the lock and offers
    Sharing from it."""
    cache: dict[str, dict] = {}
    out = []
    for f in files:
        is_folder = f.get("kind") == "folder"
        folder = f["path"] if is_folder else f.get("folder", "")
        if folder not in cache:
            cache[folder] = access(user, area, folder)
        a = cache[folder]
        if _rank(a["level"]) < _rank("see"):
            continue
        if not is_folder and not folder and top_file_owner(area, f["path"]) == user:
            # A loose file at the top that this user put there: theirs.
            f = {**f, "access": {**a, "level": "manage", "owner": user}}
        if is_folder:
            f = {**f, "access": a}
            if area == VAULT_AREA and (_dir(area, f["path"]) / VAULT).is_file():
                f["vault"] = True
        out.append(f)
    return out


def claim(area: str, folder: str, user: str) -> None:
    """`user` made `folder`: it is theirs. Its visibility is left to follow
    the folder it is in until the owner says otherwise."""
    side = _dir(area, folder) / SIDE
    if not folder or side.exists():
        return
    side.write_text(json.dumps({"owner": user}, indent=2), encoding="utf-8")


def rule_here(area: str, folder: str) -> dict:
    return dict(_rule(area, folder) or {})


def set_rule(user: str, area: str, folder: str, visibility: str | None, people: dict[str, str]) -> dict:
    """Change who may see `folder`: only its owner (or the owner of a folder
    above it) may. `visibility` None goes back to following the
    folder above."""
    if not folder or not _dir(area, folder).is_dir():
        raise AccessError("that is not a folder of the library", 404)
    if not access(user, area, folder)["can_share"]:
        raise AccessError("only the folder's owner can change who sees it")
    if vault_of(area, folder) is not None:
        raise AccessError("an encrypted folder stays private", 400)
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
    rule = rule_here(area, folder)
    rule.pop("visibility", None)
    rule.pop("people", None)
    if visibility is not None:
        rule["visibility"] = visibility
        if clean:
            rule["people"] = clean
    side = _dir(area, folder) / SIDE
    if rule:
        side.write_text(json.dumps(rule, indent=2), encoding="utf-8")
    elif side.exists():
        side.unlink()
    return access(user, area, folder)


def users() -> list[str]:
    """Everyone who can open the Media panel — who a folder can be shared with."""
    out = []
    for name in USERS:
        vis = visible_panels(name)
        if vis is None or "movies" in vis:
            out.append(name)
    return sorted(out)


# ── vaults (encrypted folders of Documents) ────────────────────────────────
def vault_of(area: str, path: str) -> str | None:
    """The vault `path` is in or is -- its top folder, relative to the
    library -- or None."""
    if area != VAULT_AREA or not shared(area):
        return None
    parts = [p for p in path.split("/") if p]
    for i in range(len(parts) + 1):
        rel = "/".join(parts[:i])
        if (_dir(area, rel) / VAULT).is_file():
            return rel
    return None


def _check_vault_file(data) -> dict:
    """The vault file's shape (VAULT.md): nothing in it is secret, but it has
    to be something the browser and the app can unlock."""
    import base64

    def blob(v, n):
        try:
            return isinstance(v, str) and len(base64.b64decode(v, validate=True)) == n
        except ValueError:
            return False
    kdf = data.get("kdf") if isinstance(data, dict) else None
    ok = (isinstance(data, dict) and data.get("v") == 1 and isinstance(kdf, dict)
          and kdf.get("alg") == "argon2id"
          and isinstance(kdf.get("m"), int) and 8 <= kdf["m"] <= 1 << 20
          and isinstance(kdf.get("t"), int) and 1 <= kdf["t"] <= 10
          and isinstance(kdf.get("p"), int) and 1 <= kdf["p"] <= 8
          and all(isinstance(data.get(w), dict) and blob(data[w].get("salt"), 16)
                  and blob(data[w].get("nonce"), 12) and blob(data[w].get("key"), 48)
                  for w in ("password", "recovery")))
    if not ok:
        raise AccessError("not a vault file this server understands", 400)
    return {"v": 1, "kdf": {k: kdf[k] for k in ("alg", "m", "t", "p")},
            **{w: {k: data[w][k] for k in ("salt", "nonce", "key")} for w in ("password", "recovery")}}


def make_vault(user: str, area: str, folder: str, data) -> dict:
    """`folder` (just made by `user`) becomes a vault: theirs, private, with
    its vault file."""
    clean = _check_vault_file(data)
    d = _dir(area, folder)
    (d / SIDE).write_text(json.dumps({"owner": user, "visibility": "private"}, indent=2), encoding="utf-8")
    (d / VAULT).write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return access(user, area, folder)


def read_vault(area: str, folder: str) -> dict:
    try:
        return json.loads((_dir(area, folder) / VAULT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise AccessError("that is not an encrypted folder", 404)


def replace_vault(user: str, area: str, folder: str, data) -> None:
    """A new vault file -- a changed password -- from the vault's owner."""
    if vault_of(area, folder) != folder:
        raise AccessError("that is not an encrypted folder", 404)
    if not access(user, area, folder)["can_share"]:
        raise AccessError("only the folder's owner can change its password")
    clean = _check_vault_file(data)
    tmp = _dir(area, folder) / (VAULT + ".tmp")
    tmp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    tmp.replace(_dir(area, folder) / VAULT)
