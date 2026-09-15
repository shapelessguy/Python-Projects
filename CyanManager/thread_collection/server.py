import threading
import numpy as np
import base64
from functions.audio import get_current_audio_info
from utils import wait
from flask import Flask, jsonify, request
from thread_collection.stt import transcribe, synthesize_speech, askLLM, NAME as STT_NAME


NAME = "API Server"
PARAMETERS = {
}


def get_info():
    return {
        **get_current_audio_info()
    }


def entrypoint(thread_manager):
    signal = thread_manager.signal
    app = Flask(__name__)

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

    server = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000), daemon=True)
    server.start()

    while signal.is_alive() and not thread_manager.to_kill:
        wait(signal, 2000)

    print(f"{thread_manager.name} thread down..")
