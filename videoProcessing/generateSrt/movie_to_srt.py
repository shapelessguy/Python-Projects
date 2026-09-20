import argparse
from pathlib import Path

from videoProcessing.generateSrt.extract_audio import extract_audio
from videoProcessing.generateSrt.transcribe_client import transcribe_movie


def movie_to_srt(video_path, host="localhost:10000", language=None, output=None):
    video_path = Path(video_path)

    print("Extracting audio...")
    audio_path = extract_audio(video_path)

    print("Sending to the STT service...")
    result = transcribe_movie(host, str(audio_path), language=language)
    if result.get("status") != "done":
        print(f"Failed: {result}")
        return None

    srt_path = Path(output) if output else video_path.with_suffix(".srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(result["srt"])
    print(f"Subtitles saved to {srt_path}")

    audio_path.unlink(missing_ok=True)
    return srt_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract a movie's audio and transcribe it into an .srt via the running CyanManager STT service."
    )
    parser.add_argument("video", help="Path to the movie/video file")
    parser.add_argument("--host", default="localhost:10000", help="host:port of the CyanManager server")
    parser.add_argument("--language", default=None, help="Force the source language (e.g. 'de')")
    parser.add_argument("--output", default=None, help="Where to save the .srt (default: alongside the video)")
    args = parser.parse_args()

    movie_to_srt(args.video, host=args.host, language=args.language, output=args.output)
