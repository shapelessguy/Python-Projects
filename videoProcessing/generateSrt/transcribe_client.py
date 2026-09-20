import argparse
import time

import requests


def transcribe_movie(host, audio_path, language=None, ext=None, poll_interval=2, on_progress=None):
    ext = ext or f".{audio_path.rsplit('.', 1)[-1]}"
    params = {"ext": ext}
    if language:
        params["language"] = language

    with open(audio_path, "rb") as f:
        data = f.read()

    resp = requests.post(f"http://{host}/transcribe_movie/start", params=params, data=data)
    resp.raise_for_status()
    job_id = resp.json()["job_id"]
    if not on_progress:
        print(f"Job started: {job_id}")

    status_url = f"http://{host}/transcribe_movie/status/{job_id}"
    start = time.time()
    while True:
        time.sleep(poll_interval)
        status = requests.get(status_url).json()

        if status["status"] == "running":
            percent = status.get("percent", 0.0)
            elapsed = time.time() - start
            eta = (elapsed / percent * (100 - percent)) if percent > 0 else None
            if on_progress:
                on_progress(percent, eta)
            else:
                eta_str = f", ETA {eta:.0f}s" if eta is not None else ""
                print(f"\r{percent:5.1f}%{eta_str}     ", end="", flush=True)
        elif status["status"] == "done":
            if not on_progress:
                print("\rDone.                        ")
            return status
        else:
            if not on_progress:
                print(f"\rError: {status.get('error')}")
            return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Send an audio/video file to the running CyanManager STT service and track progress."
    )
    parser.add_argument("file", help="Path to the audio/video file (run extract_audio.py first for movies)")
    parser.add_argument("--host", default="localhost:10000", help="host:port of the CyanManager server")
    parser.add_argument("--language", default=None, help="Force the source language (e.g. 'de')")
    parser.add_argument("--output", default=None, help="Where to save the .srt (default: alongside the input file)")
    args = parser.parse_args()

    result = transcribe_movie(args.host, args.file, language=args.language)
    if result.get("status") == "done":
        srt_path = args.output or args.file.rsplit(".", 1)[0] + ".srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(result["srt"])
        print(f"Subtitles saved to {srt_path}")
