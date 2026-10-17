"""FLAC to MP3, one file at a time, for the remux queue's "convert" jobs.

The MP3 is written beside the FLAC, under the same name: LAME VBR V0 (about
245 kbps, transparent for listening), the tags carried over as ID3v2.3 —
the version every player reads — and the cover art too, when the FLAC has
one. The MP3 replaces the FLAC: once it is in place, the FLAC is deleted.

The encode goes to a hidden temporary name first and is renamed into place
only once ffmpeg has finished cleanly, so a stopped or failed conversion
never leaves a truncated MP3 that looks like a finished one — and the FLAC
is only deleted after that rename, so there is never a moment with neither.
"""
import re
import subprocess
from pathlib import Path

TEMP_PREFIX = ".converting-"
_TIME_RE = re.compile(r"out_time_us=(\d+)")


def is_flac(path: str | Path) -> bool:
    return str(path).lower().endswith(".flac")


def target_of(src: Path) -> Path:
    return src.with_suffix(".mp3")


def temp_of(src: Path) -> Path:
    return src.with_name(TEMP_PREFIX + target_of(src).name)


def _duration(src: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(src)],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip() or 0)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0.0


def convert(src: Path, report, cancelled) -> Path:
    """Encode `src` to an MP3 beside it, then delete `src`. `report(pid=..., percent=...)` is
    told the encoder's pid (so it can be stopped) and how far it is, in
    0–100 of this one file. Raises on failure; returns the MP3's path."""
    dest = target_of(src)
    if dest.exists():
        raise FileExistsError(f"{dest.name} already exists")
    tmp = temp_of(src)
    total = _duration(src)
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(src),
           "-map", "0:a:0", "-map", "0:v?",
           "-c:a", "libmp3lame", "-q:a", "0",
           # Cover art: copied as is, marked as the front cover.
           "-c:v", "copy", "-disposition:v", "attached_pic",
           "-map_metadata", "0", "-id3v2_version", "3",
           "-progress", "pipe:1", "-f", "mp3", str(tmp)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    report(pid=proc.pid)
    last = -1
    try:
        for line in proc.stdout or ():
            m = _TIME_RE.match(line)
            if m and total > 0:
                pct = min(99, int(int(m.group(1)) / 1e6 / total * 100))
                if pct != last:
                    last = pct
                    report(percent=pct)
        err = proc.stderr.read() if proc.stderr else ""
        proc.wait()
    finally:
        report(pid=None)
    if cancelled() or proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        if cancelled():
            raise InterruptedError("stopped")
        raise RuntimeError(f"{src.name}: ffmpeg failed — {err.strip()[-300:] or proc.returncode}")
    tmp.replace(dest)
    src.unlink()
    return dest
