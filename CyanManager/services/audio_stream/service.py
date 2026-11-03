"""What this PC is playing, for whoever listens on the API server's /ws/audio.

WASAPI loopback of Windows' default output: the mix of every app, as it is
sent to the device. Captured only while someone listens; when the default
output changes (Speakers/Headphones) the capture is reopened on the new one,
since a loopback stream stays on the device it was opened on.

A listener gets, in order:
    {"type": "format", "rate": 48000, "channels": 2, "device": "..."}
        first, and again whenever the device (and maybe the format) changes
    bytes
        int16 little-endian PCM, channels interleaved, ~20 ms each
None ends the stream (the service stopped).

Windows sends nothing while nothing plays: a gap in the bytes is silence, the
player has to carry on from where it is, not wait for it.
"""
import asyncio
import threading

import numpy as np

from functions.audio import get_default_output_id
from utils import wait


NAME = "Audio Stream"  # a plain string: service_deps.py reads it without importing
PARAMETERS = {}

CHUNK_SECONDS = 0.02
MAX_QUEUED = 25  # chunks (~0.5 s): a listener further behind loses the oldest
RETRY = 5  # seconds before trying again to open a device that failed

_lock = threading.Lock()
_listeners = set()
_format = None
_running = False


class Listener:
    """One /ws/audio connection: what the capture thread hands to its event loop."""

    def __init__(self, loop):
        self.loop = loop
        self.queue = asyncio.Queue(maxsize=MAX_QUEUED)

    def push(self, item):
        self.loop.call_soon_threadsafe(self._put, item)

    def _put(self, item):
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(item)


def listen(loop):
    """A new Listener on `loop`, None when the service is not running."""
    with _lock:
        if not _running:
            return None
        listener = Listener(loop)
        _listeners.add(listener)
        if _format:
            listener.push(_format)
    return listener


def stop_listening(listener):
    with _lock:
        _listeners.discard(listener)


def _broadcast(item):
    with _lock:
        for listener in _listeners:
            listener.push(item)


def _open(pa, pyaudio):
    """A loopback stream on the default output, already sending to the listeners."""
    global _format
    device = pa.get_default_wasapi_loopback()
    channels = device["maxInputChannels"]
    rate = int(device["defaultSampleRate"])

    def callback(data, frame_count, time_info, status):
        if channels > 2:  # 5.1/7.1 mix: front left/right only
            data = np.frombuffer(data, dtype=np.int16).reshape(-1, channels)[:, :2].tobytes()
        _broadcast(data)
        return None, pyaudio.paContinue

    # Shared mode: rate and channels must be the device's own, PortAudio only converts the sample type.
    stream = pa.open(format=pyaudio.paInt16, channels=channels, rate=rate, input=True,
                     input_device_index=device["index"], frames_per_buffer=int(rate * CHUNK_SECONDS),
                     stream_callback=callback)
    with _lock:
        _format = {"type": "format", "rate": rate, "channels": min(channels, 2),
                   "device": device["name"].removesuffix(" [Loopback]")}
    _broadcast(_format)
    print(f"Audio Stream: capturing {_format['device']} ({rate} Hz, {channels} ch)")
    return stream


def _close(stream):
    global _format
    if stream:
        stream.stop_stream()
        stream.close()
    with _lock:
        _format = None


def entrypoint(thread_manager):
    global _running
    import pyaudiowpatch as pyaudio  # this service's requirement

    signal = thread_manager.signal
    pa = None
    stream = None
    device_id = None
    retry_in = 0
    with _lock:
        _running = True
    try:
        while signal.is_alive() and not thread_manager.to_kill:
            if _listeners:
                current = get_default_output_id()
                if (stream is None or current != device_id) and retry_in <= 0:
                    _close(stream)
                    stream = None
                    if pa:
                        pa.terminate()
                    # PortAudio lists the devices once: a new PyAudio sees one plugged in since
                    pa = pyaudio.PyAudio()
                    try:
                        stream = _open(pa, pyaudio)
                        device_id = current
                    except Exception as e:
                        print(f"Audio Stream: cannot capture the default output, retrying in {RETRY}s: {e}")
                        retry_in = RETRY * 1000
            elif stream:
                _close(stream)
                stream = None
                device_id = None
                print("Audio Stream: nobody listening, capture stopped")
            retry_in -= 500
            wait(signal, 500)
    finally:
        _close(stream)
        if pa:
            pa.terminate()
        with _lock:
            _running = False
            for listener in _listeners:
                listener.push(None)
        print(f"{thread_manager.name} thread down..")
