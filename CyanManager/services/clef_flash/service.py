"""Clef-flash, Cloudflare's 9B decision model, served by llama.cpp's llama-server.

The model is a GGUF quantization (the BF16 weights do not fit a 12 GB card),
so it runs in its own process rather than in this one like Whisper: this
service starts llama-server, restarts it if it dies and stops it -- freeing
the VRAM -- when disabled. llama-server downloads the weights itself the
first time a quantization is used (6.5 GB for Q4_K_M), into its own cache.

It listens on this PC only (URL). Everyone, this PC included, reaches it
through the API server, at /clef/... (services/api_server), e.g.
POST http://<pc>:10000/clef/v1/systemone.

tools/llama/ is llama.cpp's Windows CUDA release, unzipped together with its
cudart zip (https://github.com/ggml-org/llama.cpp/releases); not in git.
"""
import os
import subprocess
import time
import psutil
import requests
from utils import Parameter, wait
from PyQt5.QtWidgets import QComboBox


NAME = "Clef-flash"
PARAMETERS = {
    "Quantization": Parameter("Q4_K_M", QComboBox, ["Q4_K_M", "Q8_0"]),
}

REPO = "ggml-org/Clef-Flash-GGUF"
PORT = 10001
URL = f"http://127.0.0.1:{PORT}"
CONTEXT = 16384  # tokens: the model card's default max_length
RESTART_DELAY = 10  # seconds before relaunching a llama-server that died

LLAMA_SERVER_EXE = os.path.join(os.path.dirname(__file__), "tools", "llama", "llama-server.exe")
LOG = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "clef_flash.log")


def kill_leftovers():
    """A llama-server of ours that outlived a CyanManager that crashed still holds the port and the VRAM."""
    for proc in psutil.process_iter(['exe']):
        try:
            if proc.info['exe'] and os.path.samefile(proc.info['exe'], LLAMA_SERVER_EXE):
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass


def launch(quantization):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as log:
        return subprocess.Popen(
            [LLAMA_SERVER_EXE, "-hf", f"{REPO}:{quantization}", "--host", "127.0.0.1", "--port", str(PORT),
             # A decision model reads its whole prompt in one batch: the default of 512 tokens refuses anything longer.
             "-c", str(CONTEXT), "-b", str(CONTEXT), "-ub", str(CONTEXT), "-ngl", "99", "--no-ui"],
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def ready():
    try:
        return requests.get(f"{URL}/health", timeout=1).status_code == 200
    except requests.RequestException:
        return False


def entrypoint(thread_manager):
    signal = thread_manager.signal
    if not os.path.exists(LLAMA_SERVER_EXE):
        print(f"Clef-flash: {LLAMA_SERVER_EXE} not found")
        return

    kill_leftovers()
    proc, announced, died_at = None, False, 0
    while signal.is_alive() and not thread_manager.to_kill:
        if proc is None and time.time() - died_at > RESTART_DELAY:
            quantization = thread_manager.get_param("Quantization")
            print(f"Launching llama-server with {REPO}:{quantization}")
            proc, announced = launch(quantization), False
        elif proc is not None and proc.poll() is not None:
            print(f"Clef-flash: llama-server exited ({proc.returncode}), see {os.path.normpath(LOG)}")
            proc, died_at = None, time.time()
        elif proc is not None and not announced and ready():
            # Not at once the first time: llama-server downloads the weights first.
            print("Clef-flash loaded")
            announced = True
        wait(signal, 1000)

    if proc is not None:
        proc.kill()
        proc.wait()

    print(f"{thread_manager.name} thread down..")
