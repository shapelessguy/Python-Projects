import json
import threading
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import dotenv_values
from utils import wait, ENV_PATH
from thread_collection import api_auth
from functions.mouse_remote import (
    move_relative,
    click,
    scroll,
    type_text,
    press_key,
    move_window_left,
    move_window_right,
    toggle_maximize_window,
)


NAME = "Mouse Server"
PARAMETERS = {}

env_vars = dotenv_values(ENV_PATH)
MOUSE_WS_PORT = int(env_vars.get("MOUSE_WS_PORT", "10001"))


def handle_message(msg):
    t = msg.get("t")
    if t == "move":
        move_relative(msg.get("dx", 0), msg.get("dy", 0))
    elif t == "click":
        click(msg.get("btn", "left"))
    elif t == "scroll":
        scroll(msg.get("dy", 0))
    elif t == "text":
        type_text(msg.get("insert", ""), msg.get("delete", 0))
    elif t == "key":
        press_key(msg.get("key", ""))
    elif t == "window":
        action = msg.get("action")
        if action == "move_left":
            move_window_left()
        elif action == "move_right":
            move_window_right()
        elif action == "toggle_maximize":
            toggle_maximize_window()


def build_app():
    app = FastAPI()

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        # Keyboard and mouse: only a CyanHouse user with the Controls panel
        # (api_auth.py). A browser cannot set Authorization on a WebSocket,
        # so no web page can drive this even from inside the LAN.
        remote = websocket.client.host if websocket.client else None
        if not api_auth.allowed(remote, websocket.headers.get("authorization")):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                try:
                    handle_message(msg)
                except Exception as e:
                    print(f"mouse_server: error handling {msg}: {e}")
        except WebSocketDisconnect:
            pass

    return app


def entrypoint(thread_manager):
    signal = thread_manager.signal
    app = build_app()

    server = threading.Thread(
        target=lambda: uvicorn.run(app, host="0.0.0.0", port=MOUSE_WS_PORT, log_level="warning"),
        daemon=True,
    )
    server.start()

    while signal.is_alive() and not thread_manager.to_kill:
        wait(signal, 2000)

    print(f"{thread_manager.name} thread down..")
