"""Seek-and-pipe video playback — a self-contained function, not a feature.

Given a path to a video file on disk, this lets a browser play it with real
seeking, the same trick Plex/Jellyfin use: the frontend never seeks within one
HTTP response (which would need a slow full transcode + Range support to get
right); instead every scrub of the slider requests a brand new stream that
starts at the target timestamp. ffmpeg seeks its *input* to that timestamp
(fast — jumps to the nearest keyframe instead of decoding from the start) and
pipes a small fragmented-mp4 stream out, which the <video> element just plays
start to end like a live broadcast.

Video is always stream-copied (free, instant — no re-encoding). Audio is
transcoded to AAC, since browsers can't play the AC3/DTS tracks common in
torrent rips but audio transcoding is cheap enough to do in real time. A
source with an incompatible *video* codec (e.g. some HEVC rips) isn't handled
here yet — out of scope for this pass; would need a conditional full
re-encode later.

No knowledge of torrent clients, download folders, or anything else — the
only input is a file path. Whatever calls this owns finding the file.
"""
import subprocess
from collections.abc import Iterator
from pathlib import Path

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def probe_duration(path: str) -> float:
    """Total duration of the file in seconds, via ffprobe."""
    out = subprocess.run(
        [
            FFPROBE, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def stream_from(path: str, start: float) -> Iterator[bytes]:
    """Fragmented-mp4 stream starting at `start` seconds into `path`. Blocking
    generator — call via run_in_threadpool if driving it from async code, or
    consume directly from a sync StreamingResponse."""
    cmd = [
        FFMPEG,
        "-ss", str(max(start, 0)),
        "-i", path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov",
        "-avoid_negative_ts", "make_zero",
        "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            yield chunk
    finally:
        # Scrubbing the slider abandons the in-flight response (generator gets
        # GeneratorExit) — always kill the process rather than let it run to
        # completion transcoding a stream nobody's reading anymore.
        proc.kill()
        proc.wait()


def to_vtt(path: str) -> str:
    """WebVTT text for a subtitle file — passes .vtt through, converts .srt
    (the format torrent releases almost always ship) with the one difference
    that matters to a browser: comma decimal separators -> dots."""
    text = Path(path).read_text("utf-8", errors="replace")
    if path.lower().endswith(".vtt"):
        return text
    body = "\n".join(
        line.replace(",", ".") if _is_timestamp_line(line) else line
        for line in text.splitlines()
    )
    return f"WEBVTT\n\n{body}\n"


def _is_timestamp_line(line: str) -> bool:
    return "-->" in line
