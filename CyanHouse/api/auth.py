"""Auth: a username + token pair, accepted either as a `diary_auth` cookie
holding `base64(user:token)` or as HTTP Basic (`Authorization: Basic
base64(user:token)`). The browser SPA manages the cookie and it takes
precedence; Android sends the Basic header (it has no cookie).

Users come from, in order:
  1. env var  DIARY_USERS='{"alice":{"token":"tok1","permissions":{}}}'
  2. file     api/users.json  (git-ignored, same JSON shape)
  3. dev fallback  {"dev": {"token": "dev", "permissions": {}}}  (logs a warning)

Each user is `{"token": str, "permissions": dict}` — permissions aren't
enforced anywhere yet, just carried through for later.
"""
import base64
import json
import os
import secrets

from fastapi import HTTPException, Request, status

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
