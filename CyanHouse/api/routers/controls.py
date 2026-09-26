"""CC (Cyan Controls) home-automation — a plug-and-play router module.

The Room actuator (top/lights/strip/tv/audio -> ESP32 boards over HTTP) runs
in-process — see api/services/room.py, ported from old_roomserver. The fn
service is still a separate process on the LAN (CONTROLS_FN_HOST in secrets.json),
reached the same way CyanControls always did, just proxied here so the
panels stay same-origin and behind the dashboard login. Each call carries the
caller's own credential: the fn service signs people in with the CyanHouse
users too (CyanManager/thread_collection/api_auth.py).

    POST /api/controls/room/{topic}  ->  api.services.room.send(topic, command)
    POST /api/controls/fn/{name}     ->  {CONTROLS_FN_URL}/functions/{name}/run   body: optional
    GET  /api/controls/voices        ->  {CONTROLS_FN_URL}/voices  (list of voice names)
    POST /api/controls/voices/{name} ->  {CONTROLS_FN_URL}/voices/{name}/play
    GET  /api/controls/info          ->  {CONTROLS_FN_URL}/info

Contract picked up by ``api/main.py`` auto-discovery: only `router` and
`init()` (starts the Room actuator's lights-auto scheduler) — no DB, no
version counter, so `versions()` isn't needed.
"""
import asyncio
import time
from typing import Any
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from api import longpoll
from api.auth import basic_header, require_user
from api.config import CONTROLS_FN_URL
from api.services import room

router = APIRouter(prefix="/api/controls", tags=["controls"])

PANEL = "controls"  # gates the whole router behind permissions.visibility -- see api/auth.py

_TIMEOUT = 5  # same as CyanControls' OkHttp timeouts


def init() -> None:
    room.init()


def _forward(method: str, base: str, path: str, payload: dict | None, user: str) -> dict:
    if not base:
        raise HTTPException(
            status_code=503,
            detail="controls proxy not configured — set CONTROLS_FN_HOST in secrets.json",
        )
    url = f"{base}{path}"
    headers = basic_header(user)
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=_TIMEOUT)
        elif payload is None:
            r = requests.post(url, headers=headers, timeout=_TIMEOUT)
        else:
            r = requests.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"control server unreachable: {e}")
    if not r.ok:
        raise HTTPException(status_code=502, detail=f"control server returned {r.status_code}")
    try:
        return r.json()
    except ValueError:
        return {}


@router.post("/room/{topic}")
async def room_command(topic: str, body: dict[str, Any] | None = None):
    command = (body or {}).get("command")
    if not command:
        raise HTTPException(status_code=400, detail="command is required")
    set_auto_time = (body or {}).get("set_auto_time")
    try:
        return await run_in_threadpool(room.send, topic, command, set_auto_time)
    except room.RoomError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.post("/fn/{name}")
async def fn(name: str, body: dict[str, Any] | None = None, user: str = Depends(require_user)):
    return await run_in_threadpool(
        _forward, "POST", CONTROLS_FN_URL, f"/functions/{name}/run", body if body else None, user
    )


@router.get("/voices")
async def voices(user: str = Depends(require_user)):
    return await run_in_threadpool(_forward, "GET", CONTROLS_FN_URL, "/voices", None, user)


@router.post("/voices/{name}")
async def play_voice(name: str, user: str = Depends(require_user)):
    return await run_in_threadpool(
        _forward, "POST", CONTROLS_FN_URL, f"/voices/{quote(name, safe='')}/play", None, user
    )


# What the fn service last said about the room, and when: however many
# clients are waiting on it, it is asked at most once a second.
_info: tuple[float, dict] | None = None
_info_lock = asyncio.Lock()
INFO_FRESH = 1.0


async def _current_info(user: str) -> dict:
    global _info
    async with _info_lock:
        if _info is None or time.monotonic() - _info[0] >= INFO_FRESH:
            _info = (time.monotonic(), await run_in_threadpool(_forward, "GET", CONTROLS_FN_URL, "/info", None, user))
        return _info[1]


@router.get("/info")
async def info(request: Request, since: str | None = None, wait: float = 25,
               user: str = Depends(require_user)):
    """The room's state (volume and the like, which changes on its own).
    With `since` (the X-Tag of the last answer) held until it changes, or
    `wait` seconds pass — api/longpoll.py."""
    return await longpoll.hold(request, lambda: _current_info(user), since, wait, check=INFO_FRESH)
