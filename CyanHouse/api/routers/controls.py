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
    GET  /api/controls/users         ->  who the fn service lets in (users())
    WS   /api/controls/mouse         ->  {MOUSE_WS_URL}  (the Android app's Mouse section)

Contract picked up by ``api/main.py`` auto-discovery: only `router` and
`init()` (starts the Room actuator's lights-auto scheduler) — no DB, no
version counter, so `versions()` isn't needed.
"""
import asyncio
import hashlib
import time
from typing import Any
from urllib.parse import quote

import requests
import websockets
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool

from api import longpoll
from api.auth import USERS, basic_header, require_user, visible_panels
from api.config import CONTROLS_FN_URL, MOUSE_WS_URL
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


@router.get("/users")
async def users():
    """Every user, for the fn service to sign callers in with (CyanManager
    fetches this at startup, see its api_auth.py): the SHA-256 of their token
    rather than the token, so the PC never holds anyone's credential but its
    own, and whether they have this panel."""
    return {
        name: {
            "token_sha256": hashlib.sha256(u["token"].encode("utf-8")).hexdigest(),
            "controls": (vis := visible_panels(name)) is None or PANEL in vis,
        }
        for name, u in USERS.items() if u.get("token")
    }


@router.websocket("/mouse")
async def mouse(websocket: WebSocket, user: str = Depends(require_user)):
    """The Mouse section's WebSocket, relayed to CyanManager's mouse server
    with the caller's own credential (as _forward does), so the phone only
    ever talks to CyanHouse. The messages only go to the PC; the mouse server
    never answers, it just closes."""
    if not MOUSE_WS_URL:
        await websocket.send_denial_response(PlainTextResponse(
            "mouse server not configured — set CONTROLS_FN_HOST in secrets.json", status_code=503))
        return
    try:
        pc = await websockets.connect(MOUSE_WS_URL, additional_headers=basic_header(user),
                                      open_timeout=_TIMEOUT)
    except (OSError, TimeoutError, websockets.WebSocketException) as e:
        await websocket.send_denial_response(PlainTextResponse(
            f"mouse server unreachable: {e}", status_code=502))
        return
    await websocket.accept()

    async def to_pc():
        while True:
            await pc.send(await websocket.receive_text())

    async def from_pc():
        async for _ in pc:
            pass

    tasks = [asyncio.create_task(to_pc()), asyncio.create_task(from_pc())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await pc.close()
        try:
            await websocket.close()
        except (RuntimeError, WebSocketDisconnect):
            pass  # the phone already went
