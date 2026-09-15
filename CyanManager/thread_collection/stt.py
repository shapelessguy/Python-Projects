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
from PyQt5.QtWidgets import QLineEdit
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

    download_voices.download_voice(VOICE_NAME, VOICE_DIR)  # no-op if already downloaded
    signal.whisper_model = whisper.load_model("small").to("cuda")
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