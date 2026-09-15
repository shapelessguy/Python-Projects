import collections
import numpy as np
import sounddevice as sd
import whisper
from openwakeword.model import Model

WAKE_WORD = "hey_jarvis"
DETECTION_THRESHOLD = 0.5
SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280  # 80ms, openWakeWord's expected frame size
PRE_ROLL_SECONDS = 0.1
COMMAND_SECONDS = 5

whisper_model = whisper.load_model("small").to("cuda")
oww_model = Model(wakeword_models=[WAKE_WORD], inference_framework="onnx")

def transcribe(audio_int16):
    audio = audio_int16.astype(np.float32) / 32768.0
    result = whisper_model.transcribe(audio, fp16=True)
    return result["text"].strip()

def main():
    print(f"Listening for wake word '{WAKE_WORD}'...")
    pre_roll_chunks = max(1, round(PRE_ROLL_SECONDS * SAMPLE_RATE / CHUNK_SAMPLES))
    pre_roll = collections.deque(maxlen=pre_roll_chunks)
    command_frames = int(COMMAND_SECONDS * SAMPLE_RATE / CHUNK_SAMPLES)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK_SAMPLES) as stream:
        while True:
            chunk, _ = stream.read(CHUNK_SAMPLES)
            chunk = chunk.flatten()
            score = oww_model.predict(chunk)[WAKE_WORD]
            if score > 0.15:
                print(f"score: {score:.2f}")

            if score <= DETECTION_THRESHOLD:
                pre_roll.append(chunk)
                continue

            oww_model.reset()
            print("Wake word detected, listening...")

            command_chunks = list(pre_roll) + [chunk]
            for _ in range(command_frames):
                more, _ = stream.read(CHUNK_SAMPLES)
                command_chunks.append(more.flatten())

            audio = np.concatenate(command_chunks)
            print(transcribe(audio))

            pre_roll.clear()
            print(f"Listening for wake word '{WAKE_WORD}'...")

main()
