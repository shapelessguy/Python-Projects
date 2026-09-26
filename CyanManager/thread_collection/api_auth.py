"""Who may call the API server (port 10000) and the mouse server (10001).

Both run things on this PC -- typing text, pressing keys, typing the keyring
password -- so a caller signs in with its CyanHouse credentials, the same
`Authorization: Basic base64(user:token)` the Android app sends to CyanHouse,
and CyanHouse forwards its caller's.

.env holds only this PC's own CyanHouse user:

    CYANHOUSE_URL=https://cyanroomserver.duckdns.org
    ADMIN=cyanpc
    ADMIN_TOKEN=<cyanpc's token in CyanHouse's secrets.json>

It signs in with them to call CyanHouse (roomserver.py), and at startup
(load_users(), from main_logic.py) to fetch everyone else from
`GET /api/controls/users`: each user's name, the SHA-256 of their token (so
this PC never holds anyone's token but its own) and whether they have the
Controls panel. Until that fetch succeeds it is retried in the background; a
user added or changed in CyanHouse counts here after CyanManager restarts.

A user needs the Controls panel (`permissions.visibility` omitted, or listing
"controls"), as in CyanHouse itself. Movie transcription (subtitles for the
Media panel) only needs a valid user.

Calls from this PC itself (127.0.0.1 / ::1, e.g. videoProcessing's transcribe
client) need no credentials. With no users fetched every other caller is
refused: failing open would leave the PC controllable by anyone who can
reach the port.
"""
import base64
import hashlib
import secrets
import threading
import time

import requests
from dotenv import dotenv_values

from utils import ENV_PATH

LOOPBACK = {"127.0.0.1", "::1"}
PANEL = "controls"
RETRY = 30  # seconds between attempts while CyanHouse can't be reached

# username -> {"token_sha256": ..., "controls": bool}, from CyanHouse
_users: dict = {}


def own_credentials() -> tuple[str, str] | None:
    """(ADMIN, ADMIN_TOKEN): who this PC calls CyanHouse as."""
    env = dotenv_values(ENV_PATH)
    name = (env.get("ADMIN") or "").strip()
    token = (env.get("ADMIN_TOKEN") or "").strip()
    return (name, token) if name and token else None


def _fetch() -> dict:
    url = (dotenv_values(ENV_PATH).get("CYANHOUSE_URL") or "").strip().rstrip("/")
    creds = own_credentials()
    if not url or not creds:
        raise RuntimeError("set CYANHOUSE_URL, ADMIN and ADMIN_TOKEN in .env")
    r = requests.get(f"{url}/api/controls/users", auth=creds, timeout=10)
    r.raise_for_status()
    return r.json()


def load_users() -> None:
    """Fetch the users from CyanHouse, retrying in the background until it works."""
    def run():
        global _users
        while True:
            try:
                _users = _fetch()
                print(f"api_auth: {len(_users)} users from CyanHouse")
                return
            except Exception as e:
                print(f"api_auth: cannot fetch users from CyanHouse, retrying in {RETRY}s: {e}")
            time.sleep(RETRY)

    threading.Thread(target=run, name="api_auth users", daemon=True).start()


def user_for(authorization: str | None) -> dict | None:
    """The CyanHouse user an `Authorization: Basic` header signs in as."""
    if not authorization or authorization[:6].lower() != "basic ":
        return None
    try:
        name, _, token = base64.b64decode(authorization[6:].strip()).decode("utf-8").partition(":")
    except Exception:
        return None
    user = _users.get(name)
    expected = (user or {}).get("token_sha256")
    if not expected or not secrets.compare_digest(expected, hashlib.sha256(token.encode()).hexdigest()):
        return None
    return user


def allowed(remote_addr: str | None, authorization: str | None, controls: bool = True) -> bool:
    if remote_addr in LOOPBACK:
        return True
    user = user_for(authorization)
    if user is None:
        return False
    return not controls or bool(user.get("controls"))
