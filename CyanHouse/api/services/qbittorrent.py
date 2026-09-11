"""qBittorrent Web API client — backs the read-only Torrents dashboard panel.

Logs in as SEED_USER, reusing that same dashboard token as the qBittorrent
WebUI password (they're set to the same value) instead of managing a second
credential. qBittorrent's own full Web UI is also reverse-proxied directly at
/qbt/ (see docker/nginx.conf) for anything beyond this read-only view.
"""
import os
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
    "hash", "name", "size", "progress", "dlspeed", "upspeed", "eta",
    "state", "ratio", "category", "added_on", "num_seeds", "num_leechs",
)

# api/services/media.py handles anything ffmpeg/ffprobe can read — this is
# just which files in a torrent are worth offering as "play this".
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv"}
_SUBTITLE_EXTS = {".srt", ".vtt", ".ass", ".ssa"}


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


def _get(path: str, params: dict | None = None) -> requests.Response:
    """Authenticated GET against the qBittorrent Web API, with one retry after
    re-login if the session expired. Caller holds `_lock`."""
    global _authed
    if not _authed:
        _login()
    try:
        r = _session.get(f"{QBITTORRENT_URL}{path}", params=params, timeout=_TIMEOUT)
        if r.status_code == 403:
            _authed = False
            _login()
            r = _session.get(f"{QBITTORRENT_URL}{path}", params=params, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise TorrentsError(f"qBittorrent unreachable: {e}", status_code=503)
    if not r.ok:
        raise TorrentsError(f"qBittorrent returned {r.status_code}")
    return r


def list_torrents() -> list[dict]:
    """Blocking (HTTP I/O) — call via run_in_threadpool from the router."""
    with _lock:
        r = _get("/api/v2/torrents/info")
        return [{k: t.get(k) for k in _FIELDS} for t in r.json()]


def _ext(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def list_videos(torrent_hash: str) -> list[dict]:
    """Video files in a torrent, each paired with a same-named subtitle file
    if one exists — absolute paths, ready for api/services/media.py. Blocking
    — call via run_in_threadpool from the router."""
    with _lock:
        save_path = _get("/api/v2/torrents/properties", {"hash": torrent_hash}).json().get("save_path", "")
        files = _get("/api/v2/torrents/files", {"hash": torrent_hash}).json()

    entries = [
        {"name": f["name"], "path": os.path.join(save_path, f["name"]), "size": f.get("size", 0)}
        for f in files
    ]
    videos = [e for e in entries if _ext(e["name"]) in _VIDEO_EXTS]
    subs = {os.path.splitext(os.path.basename(e["name"]))[0].lower(): e for e in entries if _ext(e["name"]) in _SUBTITLE_EXTS}

    out = []
    for v in videos:
        stem = os.path.splitext(os.path.basename(v["name"]))[0].lower()
        match = subs.get(stem)
        out.append({
            "name": v["name"],
            "path": v["path"],
            "size": v["size"],
            "subtitlePath": match["path"] if match else None,
        })
    return out
