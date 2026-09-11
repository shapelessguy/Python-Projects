"""qBittorrent Web API client — backs the read-only Torrents dashboard panel.

Logs in as SEED_USER, reusing that same dashboard token as the qBittorrent
WebUI password (they're set to the same value) instead of managing a second
credential. qBittorrent's own full Web UI is also reverse-proxied directly at
/qbt/ (see docker/nginx.conf) for anything beyond this read-only view.
"""
import threading

import requests

from api.auth import USERS
from api.config import QBITTORRENT_URL, SEED_USER

_TIMEOUT = 5

_lock = threading.Lock()
_session = requests.Session()
_authed = False

# Trimmed to what the dashboard table actually shows.
_FIELDS = (
    "name", "size", "progress", "dlspeed", "upspeed", "eta",
    "state", "ratio", "category", "added_on", "num_seeds", "num_leechs",
)


class TorrentsError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _password() -> str:
    token = USERS.get(SEED_USER, {}).get("token")
    if not token:
        raise TorrentsError(f"no token for {SEED_USER!r} in api/users.json", status_code=500)
    return token


def _login() -> None:
    global _authed
    try:
        r = _session.post(
            f"{QBITTORRENT_URL}/api/v2/auth/login",
            data={"username": SEED_USER, "password": _password()},
            headers={"Referer": QBITTORRENT_URL},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        raise TorrentsError(f"qBittorrent unreachable: {e}", status_code=503)
    if r.status_code != 200 or r.text.strip() != "Ok.":
        raise TorrentsError(f"qBittorrent login failed: {r.status_code} {r.text}")
    _authed = True


def list_torrents() -> list[dict]:
    """Blocking (HTTP I/O) — call via run_in_threadpool from the router."""
    global _authed
    with _lock:
        if not _authed:
            _login()
        try:
            r = _session.get(f"{QBITTORRENT_URL}/api/v2/torrents/info", timeout=_TIMEOUT)
            if r.status_code == 403:  # session expired — one retry after re-login
                _authed = False
                _login()
                r = _session.get(f"{QBITTORRENT_URL}/api/v2/torrents/info", timeout=_TIMEOUT)
        except requests.RequestException as e:
            raise TorrentsError(f"qBittorrent unreachable: {e}", status_code=503)
        if not r.ok:
            raise TorrentsError(f"qBittorrent returned {r.status_code}")
        return [{k: t.get(k) for k in _FIELDS} for t in r.json()]
