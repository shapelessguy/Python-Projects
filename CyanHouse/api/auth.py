"""Auth: a username + token pair, accepted either as a `diary_auth` cookie
holding `base64(user:token)` or as HTTP Basic (`Authorization: Basic
base64(user:token)`). The browser SPA manages the cookie and it takes
precedence; Android sends the Basic header (it has no cookie).

Users come from, in order:
  1. env var  DIARY_USERS='{"alice":{"token":"tok1","permissions":{}}}'
  2. the "users" key of top-level secrets.json (git-ignored) -- see
     secrets.json.example
  3. dev fallback  {"dev": {"token": "dev", "permissions": {}}}  (logs a warning)

Each user is `{"token": str, "permissions": dict}`:
  * `permissions.visibility`, an optional list of panel ids (see each router
    module's own `PANEL` constant) a user is restricted to. Omitted entirely
    (the common case), a user sees/can call every panel -- an allowlist that
    only narrows things down when explicitly set.
  * `permissions.media`, the Media panel's folders beyond the public ones.
    Films, Music and Images (PUBLIC_MEDIA) are everyone's; every other
    folder -- a staging area and its output, by the name it has in
    secrets.json ("Downloads", "Audio", "TV Series", ...) -- only for users
    it is listed for. "downloaders" gives the Torrents and Downloads tabs
    (qBittorrent and pyLoad) together; "*" gives everything. Omitted, a user
    has the public folders only.
  * other names, opt-in flags, off unless set true: `publish` (move things
    between the Media panel's folders). Albums (image_access.py) and
    calendars (services/calendar.py) answer to their owners and whoever they
    were shared with, never to a flag.
"""
import base64
import json
import os
import secrets
from urllib.parse import unquote

from fastapi import Depends, HTTPException, Request, status

from api.config import SECRET_USERS


def _load_users() -> dict[str, dict]:
    raw = os.environ.get("DIARY_USERS")
    if raw:
        return {str(k): dict(v) for k, v in json.loads(raw).items()}

    if SECRET_USERS:
        return {str(k): dict(v) for k, v in SECRET_USERS.items()}

    print("WARNING: no DIARY_USERS / secrets.json users -- using dev/dev credentials")
    return {"dev": {"token": "dev", "permissions": {}}}


USERS = _load_users()


def _split(b64: str) -> tuple[str, str] | None:
    try:
        user, _, token = base64.b64decode(b64).decode("utf-8").partition(":")
        return user, token
    except Exception:
        return None


def require_user(request: Request) -> str:
    # Cookie first: it is what the SPA explicitly manages on login/logout. The
    # browser may keep auto-sending a stale `Authorization: Basic` header it
    # cached from an earlier 401 dialog — that must not override the cookie.
    creds: tuple[str, str] | None = None

    cookie = request.cookies.get("diary_auth")
    if cookie:
        creds = _split(cookie)

    if creds is None:
        header = request.headers.get("authorization", "")
        if header[:6].lower() == "basic ":
            creds = _split(header[6:].strip())

    if creds is not None:
        user, token = creds
        expected = USERS.get(user)
        expected_token = expected.get("token") if expected else None
        if expected_token is not None and secrets.compare_digest(
            expected_token.encode("utf-8"), token.encode("utf-8")
        ):
            # Stash it so middleware (which runs after the route) can read the
            # authenticated user without re-parsing the credential.
            request.state.username = user
            return user

    # NOTE: deliberately no `WWW-Authenticate: Basic` header — it makes the
    # browser pop its native sign-in dialog and then cache those credentials
    # for the whole origin, which then shadow the SPA's cookie. The SPA has its
    # own login screen; Android sends the Basic header proactively.
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad username or token")


def visible_panels(user: str) -> set[str] | None:
    """`None` means unrestricted (every panel) -- a user with no `visibility`
    entry in their permissions, which is every user unless explicitly
    configured otherwise. Otherwise, the explicit allowed set."""
    perms = (USERS.get(user) or {}).get("permissions") or {}
    vis = perms.get("visibility")
    return set(vis) if vis is not None else None


def has_permission(user: str, name: str) -> bool:
    """A named, opt-in permission from `permissions.<name>`.

    Unlike `visibility`, which narrows a default of "everything", these
    default to **off**: publishing moves files into the real library, so it
    is granted deliberately or not at all."""
    perms = (USERS.get(user) or {}).get("permissions") or {}
    return bool(perms.get(name))


def granted(user: str) -> dict[str, bool]:
    """The opt-in permissions this user holds, for /api/me — so a client can
    hide an action it isn't allowed to take rather than discovering it from
    a 403. The media list is not a flag; what it gives shows up instead as
    the folders /api/prep/areas lists and the `downloaders` flag."""
    perms = (USERS.get(user) or {}).get("permissions") or {}
    out = {k: bool(v) for k, v in perms.items() if k not in ("visibility", "media")}
    out["downloaders"] = may_use_downloaders(user)
    return out


# ── the Media panel's folders ──────────────────────────────────────────────
# Area keys as the panel and movie_prep use them: "" the films, ":music",
# ":images"; a staging area by its name, its output as "<name>:library".
PUBLIC_MEDIA = {"", ":music", ":images"}
DOWNLOADERS = "downloaders"


def _media_grants(user: str) -> set[str]:
    perms = (USERS.get(user) or {}).get("permissions") or {}
    return {str(x) for x in (perms.get("media") or [])}


def may_see_media(user: str, area: str) -> bool:
    """Whether `area` (a folder of the Media panel, either half of a staging
    pair) is one this user may see."""
    name = (area or "").removesuffix(":library")
    if name in PUBLIC_MEDIA:
        return True
    grants = _media_grants(user)
    return "*" in grants or name in grants


def may_use_downloaders(user: str) -> bool:
    grants = _media_grants(user)
    return "*" in grants or DOWNLOADERS in grants


def require_media_area(request: Request, user: str = Depends(require_user)) -> str:
    """Router dependency for everything that takes a Media folder: 403s a
    request naming one the user may not see -- as `area` or `to_area`, or
    inside a film id (`@<area>/...`, api/services/movies.py) -- so a folder
    left out of someone's list cannot be reached by URL either, not just
    missing from their tabs. Endpoints that take the area another way (an
    upload's metadata) check with may_see_media themselves."""
    q = request.query_params
    named = [q.get("area"), q.get("to_area")]
    movie_id = unquote(q.get("id") or "")
    if movie_id.startswith("@"):
        named.append(movie_id[1:].partition("/")[0])
    for area in named:
        if area is not None and not may_see_media(user, area):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not permitted to see that folder")
    return user


def require_downloaders(user: str = Depends(require_user)) -> str:
    """Router dependency for qBittorrent and pyLoad (the Torrents and
    Downloads tabs)."""
    if not may_use_downloaders(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not permitted to use the downloaders")
    return user


def require_permission(name: str):
    """Dependency factory: 403s a user without the named permission."""
    def _dep(user: str = Depends(require_user)) -> str:
        if not has_permission(user, name):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"not permitted to {name}")
        return user
    return _dep


def require_panel(panel: str):
    """Dependency factory for `app.include_router(..., dependencies=[...])`:
    401s an unauthenticated caller (via the nested require_user) same as
    always, and additionally 403s an authenticated one whose visibility list
    exists and doesn't include `panel` -- so a restricted user can't reach
    this router's endpoints directly even knowing the URL, not just fail to
    see the tab for it."""
    def _dep(user: str = Depends(require_user)) -> str:
        vis = visible_panels(user)
        if vis is not None and panel not in vis:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"not permitted to access {panel!r}")
        return user
    return _dep
