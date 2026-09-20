import os
import tempfile
import threading
import time
import uuid
import numpy as np
import base64
from functions.audio import get_current_audio_info
from utils import wait
from flask import Flask, jsonify, request
from whisper.utils import get_writer
from thread_collection.stt import transcribe, transcribe_movie, synthesize_speech, askLLM, NAME as STT_NAME


PORT = 10000
NAME = f"API Server (port {PORT})"
PARAMETERS = {
}


def get_info():
    return {
        **get_current_audio_info()
    }


def entrypoint(thread_manager):
    signal = thread_manager.signal
    app = Flask(__name__)
    transcription_jobs = {}

    def get_funcs():
        return signal.reg_functions.get_functions()

    @app.route("/info", methods=["GET"])
    def get_info_():
        return jsonify(get_info())

    @app.route("/audio", methods=["POST"])
    def receive_audio():
        try:
            print("Audio received")
            stt_thread = thread_manager.signal.thread_managers.get(STT_NAME, None)
            data = request.get_data()
            audio_int16 = np.frombuffer(data, dtype=np.int16)
            text = transcribe(stt_thread, audio_int16)

            print(f"Audio transcription -> {text}")
            reply, tool, args = askLLM(stt_thread, text)
            if tool:
                print("LLM tool usage:", tool, args)
                get_funcs()[tool].run(**args)

            print(f"LLM reply -> {reply}")
            reply_pcm, sample_rate = synthesize_speech(stt_thread, reply)

            return jsonify({
                "status": "ok",
                "text": reply,
                "audio": base64.b64encode(reply_pcm).decode("ascii"),
                "sample_rate": sample_rate,
            })
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/transcribe", methods=["POST"])
    def transcribe_audio():
        try:
            print("Audio received")
            stt_thread = thread_manager.signal.thread_managers.get(STT_NAME, None)
            data = request.get_data()
            audio_int16 = np.frombuffer(data, dtype=np.int16)
            text = transcribe(stt_thread, audio_int16)

            print(f"Audio transcription -> {text}")
            return jsonify({"status": "ok", "text": text})
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/transcribe_movie/start", methods=["POST"])
    def start_transcribe_movie():
        try:
            stt_thread = thread_manager.signal.thread_managers.get(STT_NAME, None)
            language = request.args.get("language")
            ext = request.args.get("ext", ".mp4")

            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(request.get_data())
                tmp_path = tmp.name

            job_id = uuid.uuid4().hex
            transcription_jobs[job_id] = {"status": "running", "percent": 0.0}

            def run_job():
                print(f"[{job_id}] Transcription started")
                try:
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
            return jsonify({"status": "ok", "job_id": job_id})
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/transcribe_movie/status/<job_id>", methods=["GET"])
    def transcribe_movie_status(job_id):
        job = transcription_jobs.get(job_id)
        if not job:
            return jsonify({"status": "error", "error": "Unknown job_id"}), 404
        return jsonify(job)

    @app.route("/functions", methods=["GET"])
    def list_functions():
        return jsonify(list(get_funcs().keys()))

    @app.route("/functions/<name>/run", methods=["POST"])
    def run_function(name):
        funcs = get_funcs()
        if name not in funcs:
            return jsonify({"error": f"Function '{name}' not found"}), 404
        
        if name == "SET_VOLUME":
            result = funcs[name].run(request.json.get("slide_value", None))
        else:
            result = funcs[name].run()
        
        return jsonify({"status": "ok", "ran": name, "result": str(result), "info": get_info()})

    server = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT), daemon=True)
    server.start()

    while signal.is_alive() and not thread_manager.to_kill:
        wait(signal, 2000)

    print(f"{thread_manager.name} thread down..")
