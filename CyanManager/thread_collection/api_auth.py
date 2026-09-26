"""Who may call the API server (port 10000) and the mouse server (10001).

Both run things on this PC -- typing text, pressing keys, typing the keyring
password -- so a caller signs in with its CyanHouse credentials, the same
`Authorization: Basic base64(user:token)` the Android app sends to CyanHouse,
and CyanHouse forwards its caller's. The users are CyanHouse's own, read
from its secrets.json (../CyanHouse/secrets.json, or `CYANHOUSE_SECRETS` in
.env) on every call, so a user added or removed there counts at once.

A user needs the Controls panel (`permissions.visibility` omitted, or listing
"controls"), as in CyanHouse itself. Movie transcription (subtitles for the
Media panel) only needs a valid user.

`ADMIN` in .env names the user this PC signs in as when it calls CyanHouse
(roomserver.py); the token is that user's in secrets.json.

Calls from this PC itself (127.0.0.1 / ::1, e.g. videoProcessing's transcribe
client) need no credentials. With no users readable every other caller is
refused: failing open would leave the PC controllable by anyone who can
reach the port.
"""
import base64
import json
import os
import secrets

from dotenv import dotenv_values

from utils import ENV_PATH

LOOPBACK = {"127.0.0.1", "::1"}
PANEL = "controls"
_DEFAULT_SECRETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                "CyanHouse", "secrets.json")


def _users() -> dict:
    path = (dotenv_values(ENV_PATH).get("CYANHOUSE_SECRETS") or "").strip() or _DEFAULT_SECRETS
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("users") or {}
    except (OSError, ValueError) as e:
        print(f"api_auth: cannot read users from {path}: {e}")
        return {}


def own_credentials() -> tuple[str, str] | None:
    """(ADMIN, their token): who this PC calls CyanHouse as."""
    name = (dotenv_values(ENV_PATH).get("ADMIN") or "").strip()
    token = (_users().get(name) or {}).get("token") if name else None
    return (name, token) if token else None


def user_for(authorization: str | None) -> dict | None:
    """The CyanHouse user an `Authorization: Basic` header signs in as."""
    if not authorization or authorization[:6].lower() != "basic ":
        return None
    try:
        name, _, token = base64.b64decode(authorization[6:].strip()).decode("utf-8").partition(":")
    except Exception:
        return None
    user = _users().get(name)
    expected = (user or {}).get("token")
    if not expected or not secrets.compare_digest(expected.encode(), token.encode()):
        return None
    return user


def allowed(remote_addr: str | None, authorization: str | None, controls: bool = True) -> bool:
    if remote_addr in LOOPBACK:
        return True
    user = user_for(authorization)
    if user is None:
        return False
    if not controls:
        return True
    vis = (user.get("permissions") or {}).get("visibility")
    return vis is None or PANEL in vis
