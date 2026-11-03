"""CC (Cyan Controls) home-automation — a plug-and-play router module.

The Room actuator (top/lights/strip/tv/audio -> ESP32 boards over HTTP) runs
in-process — see api/services/room.py, ported from old_roomserver. The fn
service is still a separate process on the LAN (CONTROLS_FN_HOST in config.json),
reached the same way CyanControls always did, just proxied here so the
panels stay same-origin and behind the dashboard login. Each call carries the
caller's own credential: the fn service signs people in with the CyanHouse
users too (CyanManager/api_auth.py).

    POST /api/controls/room/{topic}  ->  api.services.room.send(topic, command)
    POST /api/controls/fn/{name}     ->  {CONTROLS_FN_URL}/functions/{name}/run   body: optional
    GET  /api/controls/voices        ->  {CONTROLS_FN_URL}/voices  (list of voice names)
    POST /api/controls/voices/{name} ->  {CONTROLS_FN_URL}/voices/{name}/play
    GET  /api/controls/info          ->  {CONTROLS_FN_URL}/info
    GET  /api/controls/users         ->  who the fn service lets in (users())
    WS   /api/controls/mouse         ->  {MOUSE_WS_URL}  (the Android app's Mouse section)
    WS   /api/controls/audio         ->  {AUDIO_WS_URL}  (the "PC audio" players, downstream only)

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
from api.config import AUDIO_WS_URL, CONTROLS_FN_URL, MOUSE_WS_URL
from api.services import room

router = APIRouter(prefix="/api/controls", tags=["controls"])

PANEL = "controls"  # gates the whole router behind permissions.visibility -- see api/auth.py

_TIMEOUT = 5  # same as CyanControls' OkHttp timeouts
# The PC is on the LAN: a connection opens in milliseconds or not at all, and
# Windows drops (rather than refuses) one to a closed port, so a down
# CyanManager used to cost the whole _TIMEOUT every time it was asked.
_CONNECT_TIMEOUT = 1


def init() -> None:
    room.init()


def _forward(method: str, base: str, path: str, payload: dict | None, user: str) -> dict:
    if not base:
        raise HTTPException(
            status_code=503,
            detail="controls proxy not configured — set CONTROLS_FN_HOST in config.json",
        )
    url = f"{base}{path}"
    headers = basic_header(user)
    timeout = (_CONNECT_TIMEOUT, _TIMEOUT)
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=timeout)
        elif payload is None:
            r = requests.post(url, headers=headers, timeout=timeout)
        else:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
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
    global _info
    reply = await run_in_threadpool(
        _forward, "POST", CONTROLS_FN_URL, f"/functions/{name}/run", body if body else None, user
    )
    # The fn service nests the room's state after the call under "info";
    # lifted to the top level, where the clients read volume/device, so the
    # caller's bar moves on the reply rather than on the next /info round.
    # It also refreshes the /info cache, so other followers see it now too.
    info_after = reply.get("info") if isinstance(reply, dict) else None
    if isinstance(info_after, dict):
        _info = (time.monotonic(), info_after)
        reply = {**reply, **info_after}
    return reply


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
            "mouse server not configured — set CONTROLS_FN_HOST in config.json", status_code=503))
        return
    try:
        # Pinged often: a PC that went silent (no close) is dropped in seconds,
        # and the phone with it, instead of the library's 20 s + 20 s.
        pc = await websockets.connect(MOUSE_WS_URL, additional_headers=basic_header(user),
                                      open_timeout=_TIMEOUT, ping_interval=3, ping_timeout=3)
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


@router.websocket("/audio")
async def audio(websocket: WebSocket, user: str = Depends(require_user)):
    """The "PC audio" players' WebSocket, relayed from CyanManager's audio
    server with the caller's own credential, as /mouse is. Downstream only:
    its format messages (text) and PCM chunks (binary) go to the client
    unchanged, and its close code and reason with them (1013 "Audio Stream
    is off" is what the players show)."""
    if not AUDIO_WS_URL:
        await websocket.send_denial_response(PlainTextResponse(
            "audio server not configured — set CONTROLS_FN_HOST in config.json", status_code=503))
        return
    try:
        # Pinged as /mouse is, so a PC that went silent is told from one
        # that is just quiet: it sends nothing while it plays nothing.
        pc = await websockets.connect(AUDIO_WS_URL, additional_headers=basic_header(user),
                                      open_timeout=_TIMEOUT, ping_interval=3, ping_timeout=3)
    except (OSError, TimeoutError, websockets.WebSocketException) as e:
        await websocket.send_denial_response(PlainTextResponse(
            f"audio server unreachable: {e}", status_code=502))
        return
    await websocket.accept()

    # Nothing is queued for a slow client: a send waits while its buffer is
    # full (uvicorn), and a chunk that comes meanwhile replaces the one
    # waiting, so it hears the latest audio rather than ever later audio. A
    # format message is never dropped, and drops the chunk waiting before it
    # (it was in the old format).
    pending_text: str | None = None
    pending_bytes: bytes | None = None
    ready = asyncio.Event()

    async def from_pc():
        nonlocal pending_text, pending_bytes
        async for message in pc:
            if isinstance(message, str):
                pending_text, pending_bytes = message, None
            else:
                pending_bytes = message
            ready.set()

    async def to_client():
        nonlocal pending_text, pending_bytes
        while True:
            await ready.wait()
            ready.clear()
            while pending_text is not None or pending_bytes is not None:
                if pending_text is not None:
                    text, pending_text = pending_text, None
                    await websocket.send_text(text)
                else:
                    data, pending_bytes = pending_bytes, None
                    await websocket.send_bytes(data)

    async def client_gone():
        # The client sends nothing; this only sees it leave.
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass

    tasks = [asyncio.create_task(from_pc()), asyncio.create_task(to_client()),
             asyncio.create_task(client_gone())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await pc.close()
        # The PC's close, passed on (1013 "Audio Stream is off" included);
        # 1011 if it dropped without one.
        code = pc.close_code if pc.close_code not in (None, 1005, 1006) else 1011
        try:
            await websocket.close(code, pc.close_reason or "")
        except (RuntimeError, WebSocketDisconnect):
            pass  # the client already went
