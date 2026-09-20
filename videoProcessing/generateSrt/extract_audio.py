import argparse
import subprocess
import sys
from pathlib import Path

# Under pythonw (no console attached), spawning a console app like ffmpeg
# briefly flashes a new console window unless this flag is set.
SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def extract_audio(video_path, output_path=None, bitrate="32k", audio_stream_index=None):
    video_path = Path(video_path)
    output_path = Path(output_path) if output_path else video_path.with_suffix(".opus")

    cmd = ["ffmpeg", "-y", "-i", str(video_path)]
    if audio_stream_index is not None:
        # Select one specific audio stream (0-based, among audio streams only)
        # instead of letting ffmpeg guess which track to use.
        cmd += ["-map", f"0:a:{audio_stream_index}"]
    cmd += [
        "-vn",              # drop the video stream entirely
        "-ac", "1",         # mono
        "-ar", "16000",     # 16kHz -- what Whisper resamples everything to anyway
        "-c:a", "libopus",
        "-b:a", bitrate,    # speech doesn't need much bitrate
        str(output_path),
    ]
    subprocess.run(cmd, check=True, creationflags=SUBPROCESS_FLAGS)

    print(f"Audio extracted to {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strip the audio track out of a video file.")
    parser.add_argument("video", help="Path to the movie/video file")
    parser.add_argument("--output", default=None, help="Output audio file path (default: same name, .opus)")
    parser.add_argument("--bitrate", default="32k", help="Audio bitrate (default 32k, fine for speech)")
    parser.add_argument("--audio-index", type=int, default=None, help="Which audio stream to extract (0-based, among audio streams only)")
    args = parser.parse_args()

    extract_audio(args.video, args.output, args.bitrate, args.audio_index)
