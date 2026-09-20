"""CC (Cyan Controls) home-automation — a plug-and-play router module.

The Room actuator (top/lights/strip/tv/audio -> Arduino over serial) runs
in-process — see api/services/room.py, ported from old_roomserver. The fn
service is still a separate process on the LAN (CONTROLS_FN_HOST in secrets.json),
reached the same way CyanControls always did, just proxied here so the
panels stay same-origin and behind the dashboard login:

    POST /api/controls/room/{topic}  ->  api.services.room.send(topic, command)
    POST /api/controls/fn/{name}     ->  {CONTROLS_FN_URL}/functions/{name}/run   body: optional
    GET  /api/controls/voices        ->  {CONTROLS_FN_URL}/voices  (list of voice names)
    POST /api/controls/voices/{name} ->  {CONTROLS_FN_URL}/voices/{name}/play
    GET  /api/controls/info          ->  {CONTROLS_FN_URL}/info

Contract picked up by ``api/main.py`` auto-discovery: only `router` and
`init()` (starts the Room actuator's serial connection) — no DB, no version
counter, so `versions()` isn't needed.
"""
from typing import Any
from urllib.parse import quote

import requests
from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from api.config import CONTROLS_FN_URL
from api.services import room

router = APIRouter(prefix="/api/controls", tags=["controls"])

PANEL = "controls"  # gates the whole router behind permissions.visibility -- see api/auth.py

_TIMEOUT = 5  # same as CyanControls' OkHttp timeouts


def init() -> None:
    room.init()


def _forward(method: str, base: str, path: str, payload: dict | None) -> dict:
    if not base:
        raise HTTPException(
            status_code=503,
            detail="controls proxy not configured — set CONTROLS_FN_HOST in secrets.json",
        )
    url = f"{base}{path}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=_TIMEOUT)
        elif payload is None:
            r = requests.post(url, timeout=_TIMEOUT)
        else:
            r = requests.post(url, json=payload, timeout=_TIMEOUT)
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
async def fn(name: str, body: dict[str, Any] | None = None):
    return await run_in_threadpool(
        _forward, "POST", CONTROLS_FN_URL, f"/functions/{name}/run", body if body else None
    )


@router.get("/voices")
async def voices():
    return await run_in_threadpool(_forward, "GET", CONTROLS_FN_URL, "/voices", None)


@router.post("/voices/{name}")
async def play_voice(name: str):
    return await run_in_threadpool(
        _forward, "POST", CONTROLS_FN_URL, f"/voices/{quote(name, safe='')}/play", None
    )


@router.get("/info")
async def info():
    return await run_in_threadpool(_forward, "GET", CONTROLS_FN_URL, "/info", None)
