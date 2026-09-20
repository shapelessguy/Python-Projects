import numpy as np
import whisper
import gc
import torch
import requests
import traceback
import time
import json
from dotenv import dotenv_values
from pathlib import Path
from piper import download_voices
from utils import Parameter, wait, ENV_PATH
from functions.audio import get_current_audio_info
from piper import PiperVoice
from PyQt5.QtWidgets import QLineEdit, QComboBox
from registered_functions import RegisteredFunctions


VOICE_NAME = "en_US-lessac-medium"
VOICE_DIR = Path.home() / ".cache" / "whisper" / "piper"
MAX_HISTORY_AGE = 5 * 60  # seconds

SYSTEM_PROMPT = (
    "You are a voice assistant. Keep your answers very short and conversational — "
    "the user is listening to a spoken reply and needs quick, concise information. "
    "You have access to a set of functions to control the user's environment (lights, audio, TV, media, etc.). "
    "Call a function when the user's intent clearly maps to one. "
    "For anything else — questions, chat, opinions — just reply naturally in text. "
    "Never refuse to converse or claim you can only call functions."
)


def build_tools(signal) -> list[dict]:
    """Convert RegisteredFunctions into OpenAI-compatible tool definitions."""
    tools = []
    for name, handle in RegisteredFunctions(signal).get_functions().items():
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": handle.description,
                "parameters": {
                    "type": "object",
                    "properties": handle.properties,
                    "required": handle.required
                }
            }
        })
    return tools


def synthesize_speech(thread_manager, text: str) -> tuple[bytes, int]:
    if not thread_manager.signal.piper_voice:
        return None, None
    audio_bytes = bytearray()
    sample_rate = None
    for chunk in thread_manager.signal.piper_voice.synthesize(text):
        audio_bytes.extend(chunk.audio_int16_bytes)
        sample_rate = chunk.sample_rate
    return bytes(audio_bytes), sample_rate


def _get_history(signal) -> list[dict]:
    if not hasattr(signal, "chat_history"):
        signal.chat_history = []
        signal.chat_last_active = time.time()
    elif time.time() - signal.chat_last_active > MAX_HISTORY_AGE:
        signal.chat_history = []
    return signal.chat_history


def askLLM(thread_manager, text: str) -> tuple[str, str | None, dict | None]:
    try:
        url = thread_manager.get_param("URL")
        token_name = thread_manager.get_param("Token")
        env_vars = dotenv_values(ENV_PATH)
        token = env_vars.get(token_name, "")
        model = thread_manager.get_param("Model")

        signal = thread_manager.signal
        history = _get_history(signal)
        history.append({"role": "user", "content": text})
        signal.chat_last_active = time.time()

        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history,
            "tools": signal.tools,
            "tool_choice": "auto",
        }

        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]

        if message.get("tool_calls"):
            tool_call = message["tool_calls"][0]
            tool_name = tool_call["function"]["name"]
            raw_args = tool_call["function"].get("arguments", "{}")
            tool_args = json.loads(raw_args) if raw_args else {}
            readable = tool_name.replace("_", " ").lower().capitalize()

            history.append({"role": "assistant", "tool_calls": message["tool_calls"]})
            history.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": "done"
            })

            return f"{readable}.", tool_name, tool_args

        reply = message["content"].strip()
        history.append({"role": "assistant", "content": reply})
        return reply, None, None

    except Exception:
        print(traceback.format_exc())
        return "An error on the LLM provider has occurred", None, None


def transcribe_movie(thread_manager, video_path: str, language: str | None = None, progress: dict | None = None) -> dict | None:
    if not thread_manager.signal.whisper_model:
        return None

    import tqdm as tqdm_module

    # whisper/transcribe.py does `import tqdm` then calls `tqdm.tqdm(...)`,
    # so the thing to patch is the tqdm *class* inside that module, not the
    # module reference itself.
    original_tqdm_cls = tqdm_module.tqdm

    class _ProgressTQDM(original_tqdm_cls):
        def update(self, n=1):
            super().update(n)
            if progress is not None and self.total:
                progress["percent"] = round(100 * self.n / self.total, 1)

    # verbose=False turns on whisper's own frame-count progress bar (instead
    # of it being silent, or printing every transcribed segment); we swap in
    # a tqdm subclass that also mirrors that percentage into `progress`.
    tqdm_module.tqdm = _ProgressTQDM
    try:
        return thread_manager.signal.whisper_model.transcribe(
            video_path, language=language, fp16=True, verbose=False,
            beam_size=5,  # beam search instead of greedy decoding on the first (temperature=0) pass
            best_of=5,    # sample 5 candidates and keep the best on temperature-fallback passes
            # Long silence/music stretches otherwise make Whisper loop, repeating
            # the last phrase it locked onto every ~30s window. condition_on_previous_text
            # is what carries that bad context forward; the silence threshold gives
            # it an explicit way to recognize "nothing said here" instead of guessing.
            condition_on_previous_text=False,
            hallucination_silence_threshold=2.0,
        )
    finally:
        tqdm_module.tqdm = original_tqdm_cls


def transcribe(thread_manager, audio_int16: np.ndarray) -> str | None:
    if not thread_manager.signal.whisper_model:
        return None
    audio = audio_int16.astype(np.float32) / 32768.0
    result = thread_manager.signal.whisper_model.transcribe(audio, fp16=True)

    segments = result.get("segments", [])
    if not segments:
        return None

    # heuristics: high no_speech_prob or low avg_logprob = probably not real speech
    if all(seg["no_speech_prob"] > 0.6 or seg["avg_logprob"] < -1.0 for seg in segments):
        return "Please repeat your message"

    return result["text"].strip()


NAME = "STT service"
PARAMETERS = {
    "Whisper Model": Parameter("", QComboBox, ["small", "medium", "large"]),
    "URL": Parameter("", QLineEdit),
    "Token": Parameter("", QLineEdit),
    "Model": Parameter("", QLineEdit),
}


def get_info():
    return {
        **get_current_audio_info()
    }


def entrypoint(thread_manager):
    signal = thread_manager.signal
    params = [x for x in signal.get_threads() if x.name == NAME][0].parameters

    download_voices.download_voice(VOICE_NAME, VOICE_DIR)  # no-op if already downloaded
    signal.whisper_model = whisper.load_model(params.get('Whisper Model', '')).to("cuda")
    signal.piper_voice = PiperVoice.load(str(VOICE_DIR / f"{VOICE_NAME}.onnx"))
    signal.tools = build_tools(signal)
    print("Whisper loaded")

    while signal.is_alive() and not thread_manager.to_kill:
        wait(signal, 100)

    signal.piper_voice = None
    signal.whisper_model = None
    gc.collect()
    torch.cuda.empty_cache()

    print(f"{thread_manager.name} thread down..")