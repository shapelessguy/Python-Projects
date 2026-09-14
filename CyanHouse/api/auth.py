"""Auth: a username + token pair, accepted either as a `diary_auth` cookie
holding `base64(user:token)` or as HTTP Basic (`Authorization: Basic
base64(user:token)`). The browser SPA manages the cookie and it takes
precedence; Android sends the Basic header (it has no cookie).

Users come from, in order:
  1. env var  DIARY_USERS='{"alice":{"token":"tok1","permissions":{}}}'
  2. file     api/users.json  (git-ignored, same JSON shape)
  3. dev fallback  {"dev": {"token": "dev", "permissions": {}}}  (logs a warning)

Each user is `{"token": str, "permissions": dict}`. One permission is
enforced so far: `permissions.visibility`, an optional list of panel ids
(see each router module's own `PANEL` constant) a user is restricted to.
Omitted entirely (the common case), a user sees/can call every panel, same
as before this existed -- it's an allowlist that only narrows things down
when explicitly set, never something you opt into by omission.
"""
import base64
import json
import os
import secrets

from fastapi import Depends, HTTPException, Request, status

from api.config import API_DIR


def _load_users() -> dict[str, dict]:
    raw = os.environ.get("DIARY_USERS")
    if raw:
        return {str(k): dict(v) for k, v in json.loads(raw).items()}

    f = API_DIR / "users.json"
    if f.exists():
        return {str(k): dict(v) for k, v in json.loads(f.read_text("utf-8")).items()}

    print("WARNING: no DIARY_USERS / api/users.json — using dev/dev credentials")
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
