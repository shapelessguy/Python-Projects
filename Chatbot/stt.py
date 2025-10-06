import sounddevice as sd
import numpy as np
import whisper
import queue
import torch
import time

KEYWORD = "computer"
MIC_NAME = "Microphone (4- USB PnP Audio"
SAMPLE_RATE = 16000
CHUNK_SECONDS = 3.0
audio_buffer = []
conversation_on = False

mic_index = None
for i, dev in enumerate(sd.query_devices()):
    if dev['name'].startswith(MIC_NAME):
        mic_index = i
        print(f"Using microphone #{i}: {dev['name']}")
        break
if mic_index is None:
    raise RuntimeError("Microphone not found!")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print("Using device:", DEVICE)

base = whisper.load_model("base", device=DEVICE)
medium = whisper.load_model("medium", device=DEVICE)
q = queue.Queue()

def audio_callback(indata, frames, time_info, status):
    if status:
        print("⚠️", status)
    q.put(indata.copy())
    if not conversation_on:
        audio_buffer = []
    if len(audio_buffer) > 5:
        del audio_buffer[0]
    audio_buffer.append(indata.copy())

stream = sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="float32",
    callback=audio_callback,
    blocksize=int(CHUNK_SECONDS * SAMPLE_RATE),
    device=mic_index
)
stream.start()
print("🎤 Listening continuously...")

try:
    while True:
        audio_chunk = q.get()
        audio_flat = audio_chunk.flatten()

        print("keyword match...")
        result = base.transcribe(audio_flat, fp16=(DEVICE=="cuda"), language="en")
        text = result["text"].lower().strip()

        if any(a in text.lower() for a in ["jesus"]):
            print("KEYWORD found!")
            conversation_on = True

        if text:
            print("maybe: ", text)
            print("Long transcription...")
            result = medium.transcribe(np.concatenate(audio_buffer, axis=0).flatten(), fp16=(DEVICE=="cuda"), language="en")
            print(result["text"])

        if KEYWORD in text:
            print("✅ Keyword detected! Triggering function...")

except KeyboardInterrupt:
    print("Stopping listener...")
    stream.stop()
    stream.close()