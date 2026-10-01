import json
import os
import tempfile
import threading
import uuid
import numpy as np
import base64
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from functions.audio import get_current_audio_info, list_voices, play_voice
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
from utils import wait
from services.stt.service import transcribe, transcribe_movie, synthesize_speech, askLLM, NAME as STT_NAME
import api_auth


PORT = 10000
NAME = "API Server (port 10000)"  # a plain string: service_deps.py reads it without importing
PARAMETERS = {
}


def get_info():
    return {
        **get_current_audio_info()
    }


def handle_mouse_message(msg):
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


def entrypoint(thread_manager):
    signal = thread_manager.signal
    app = FastAPI()
    transcription_jobs = {}

    def get_funcs():
        return signal.reg_functions.get_functions()

    def remote(conn):
        return conn.client.host if conn.client else None

    # Every route runs something on this PC: see api_auth.py.
    @app.middleware("http")
    async def require_user(request: Request, call_next):
        controls = not request.url.path.startswith("/transcribe_movie/")
        if not api_auth.allowed(remote(request), request.headers.get("authorization"), controls):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.get("/info")
    def get_info_():
        return get_info()

    @app.post("/audio")
    async def receive_audio(request: Request):
        data = await request.body()

        def run():
            print("Audio received")
            stt_thread = thread_manager.signal.thread_managers.get(STT_NAME, None)
            audio_int16 = np.frombuffer(data, dtype=np.int16)
            text = transcribe(stt_thread, audio_int16)

            print(f"Audio transcription -> {text}")
            reply, tool, args = askLLM(stt_thread, text)
            if tool:
                print("LLM tool usage:", tool, args)
                get_funcs()[tool].run(**args)

            print(f"LLM reply -> {reply}")
            reply_pcm, sample_rate = synthesize_speech(stt_thread, reply)

            return {
                "status": "ok",
                "text": reply,
                "audio": base64.b64encode(reply_pcm).decode("ascii"),
                "sample_rate": sample_rate,
            }

        try:
            return await run_in_threadpool(run)
        except Exception as e:
            return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

    @app.post("/transcribe")
    async def transcribe_audio(request: Request):
        data = await request.body()

        def run():
            print("Audio received")
            stt_thread = thread_manager.signal.thread_managers.get(STT_NAME, None)
            audio_int16 = np.frombuffer(data, dtype=np.int16)
            text = transcribe(stt_thread, audio_int16)

            print(f"Audio transcription -> {text}")
            return {"status": "ok", "text": text}

        try:
            return await run_in_threadpool(run)
        except Exception as e:
            return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

    @app.post("/transcribe_movie/start")
    async def start_transcribe_movie(request: Request):
        try:
            stt_thread = thread_manager.signal.thread_managers.get(STT_NAME, None)
            language = request.query_params.get("language")
            ext = request.query_params.get("ext", ".mp4")
            data = await request.body()

            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name

            job_id = uuid.uuid4().hex
            transcription_jobs[job_id] = {"status": "running", "percent": 0.0}

            def run_job():
                print(f"[{job_id}] Transcription started")
                try:
                    from whisper.utils import get_writer  # the STT service's requirement
                    result = transcribe_movie(
                        stt_thread, tmp_path, language=language, progress=transcription_jobs[job_id]
                    )
                    if result is None:
                        transcription_jobs[job_id] = {"status": "error", "error": "Whisper model not loaded"}
                        return

                    srt_dir = tempfile.gettempdir()
                    get_writer("srt", srt_dir)(result, tmp_path, {})
                    srt_path = os.path.join(srt_dir, os.path.splitext(os.path.basename(tmp_path))[0] + ".srt")
                    with open(srt_path, encoding="utf-8") as f:
                        srt_content = f.read()
                    os.remove(srt_path)

                    transcription_jobs[job_id] = {
                        "status": "done",
                        "percent": 100.0,
                        "text": result["text"].strip(),
                        "language": result["language"],
                        "srt": srt_content,
                    }
                except Exception as e:
                    transcription_jobs[job_id] = {"status": "error", "error": str(e)}
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    print(f"[{job_id}] Transcription stopped")

            threading.Thread(target=run_job, daemon=True).start()
            return {"status": "ok", "job_id": job_id}
        except Exception as e:
            return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

    @app.get("/transcribe_movie/status/{job_id}")
    def transcribe_movie_status(job_id: str):
        job = transcription_jobs.get(job_id)
        if not job:
            return JSONResponse({"status": "error", "error": "Unknown job_id"}, status_code=404)
        return job

    @app.get("/functions")
    def list_functions():
        return list(get_funcs().keys())

    @app.post("/functions/{name}/run")
    async def run_function(name: str, request: Request):
        funcs = get_funcs()
        if name not in funcs:
            return JSONResponse({"error": f"Function '{name}' not found"}, status_code=404)

        if name == "SET_VOLUME":
            body = await request.body()
            slide_value = json.loads(body).get("slide_value", None) if body else None
            result = await run_in_threadpool(funcs[name].run, slide_value)
        else:
            result = await run_in_threadpool(funcs[name].run)

        return {"status": "ok", "ran": name, "result": str(result), "info": get_info()}

    @app.get("/voices")
    def get_voices():
        return list_voices()

    @app.post("/voices/{name}/play")
    def play_voice_(name: str):
        try:
            file = play_voice(name)
        except KeyError:
            return JSONResponse({"error": f"Voice '{name}' not found"}, status_code=404)
        except FileNotFoundError as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        except Exception as e:
            return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
        return {"status": "ok", "voice": name, "file": file}

    @app.websocket("/ws")
    async def mouse_ws(websocket: WebSocket):
        # Keyboard and mouse, from CyanHouse's /api/controls/mouse relay: only
        # a CyanHouse user with the Controls panel (api_auth.py). A browser
        # cannot set Authorization on a WebSocket, so no web page can drive
        # this even from inside the LAN.
        if not api_auth.allowed(remote(websocket), websocket.headers.get("authorization")):
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
                    await run_in_threadpool(handle_mouse_message, msg)
                except Exception as e:
                    print(f"mouse ws: error handling {msg}: {e}")
        except WebSocketDisconnect:
            pass

    server = threading.Thread(
        target=lambda: uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning"),
        daemon=True,
    )
    server.start()

    while signal.is_alive() and not thread_manager.to_kill:
        wait(signal, 2000)

    print(f"{thread_manager.name} thread down..")
