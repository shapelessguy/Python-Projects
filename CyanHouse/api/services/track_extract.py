"""Every audio and subtitle track of a video, pulled out into files of their
own, for the remux queue's "extract" jobs.

The tracks land in the extraction folder (EXTRACT_TO in api/config.py), in
the same folders, relative to the root they were picked in, as the video
they came from — a series' Show/Season 1/ again — named after the video and
the track's language code: ``E01.ita.ac3``, ``E01.eng.srt``. A forced
subtitle says so (``E01.eng.forced.srt``); two tracks that would still share
a name are numbered from the second on (``E01.eng.2.ac3``).

Nothing is re-encoded: each track is copied as it is into the plainest
container that holds it (raw AC-3, DTS, ADTS AAC, FLAC, SRT, PGS .sup ...),
and into a one-track Matroska file (.mka / .mks) when there is none — a
VobSub, say, which ffmpeg cannot write as .idx/.sub. The one exception is
an MP4's mov_text subtitle, which has no file of its own and becomes an SRT.

All of a video's tracks come out in one ffmpeg run (one read of the file),
each to a hidden temporary name renamed into place only once ffmpeg has
finished cleanly, so a stopped or failed extraction leaves nothing that
looks finished. A folder is made only for a track that is being written,
and removed again if it ends up empty. A track whose file is already there
is left alone; a video whose tracks are all there is skipped.
"""
import collections
import re
import subprocess
import threading
from pathlib import Path

from api.config import EXTRACT_TO, FFMPEG
from api.services import movie_prep, movies

TEMP_PREFIX = ".extracting-"
_TIME_RE = re.compile(r"out_time_us=(\d+)")

# codec -> (ffmpeg muxer, extension). Anything missing goes into Matroska.
_AUDIO = {
    "aac": ("adts", "aac"), "ac3": ("ac3", "ac3"), "eac3": ("eac3", "eac3"),
    "dts": ("dts", "dts"), "truehd": ("truehd", "thd"), "flac": ("flac", "flac"),
    "mp3": ("mp3", "mp3"), "opus": ("opus", "opus"), "vorbis": ("ogg", "ogg"),
}
_SUBS = {
    "subrip": ("srt", "srt"), "srt": ("srt", "srt"), "ass": ("ass", "ass"), "ssa": ("ass", "ass"),
    "webvtt": ("webvtt", "vtt"), "hdmv_pgs_subtitle": ("sup", "sup"),
    # Text with no file format of its own: the only conversion made.
    "mov_text": ("srt", "srt"),
}
# Bare audio streams, which keep no timestamps: theirs are renumbered 0, 1,
# 2 ... on the way out. Byte for byte the same file, but a TrueHD track out
# of Matroska otherwise has ffmpeg complain about every packet (~100 MB of
# "non monotonically increasing dts" for one episode).
_NO_TIMESTAMPS = {"adts", "ac3", "eac3", "dts", "truehd"}


def available() -> bool:
    return output_key() is not None


def output_key() -> str | None:
    """The extraction folder's source key, when one is configured."""
    return f"{EXTRACT_TO}:library" if EXTRACT_TO in movie_prep.areas() else None


def root() -> Path:
    key = output_key()
    if key is None:
        raise movie_prep.PrepError("no extraction folder configured (extract_to in config.json)", 503)
    return Path(movie_prep.areas()[EXTRACT_TO]["library"])


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in movie_prep.VIDEO_EXT


def _language(tags: dict) -> str:
    """The track's 3-letter code as the library writes it; "und" for none."""
    raw = (tags.get("language") or tags.get("LANGUAGE") or "").strip().lower()
    code = movie_prep._code_for(movies.language_name(raw)) if raw else ""
    return code or (raw if len(raw) == 3 and raw.isalpha() else "und")


def tracks(src: Path, rel: str, probe: dict | None = None) -> list[dict]:
    """The audio and subtitle tracks of `src`, each with the file it goes to.
    `rel` is the video's path in the root it was picked in."""
    probe = probe or movie_prep._probe(src)
    folder = root() / Path(rel).parent
    stem = Path(rel).stem
    out, taken = [], set()
    for s in probe.get("streams", []):
        kind = s.get("codec_type")
        if kind not in ("audio", "subtitle"):
            continue
        codec = s.get("codec_name") or ""
        if kind == "audio":
            muxer, ext = _AUDIO.get(codec) or (("wav", "wav") if codec.startswith("pcm_") else ("matroska", "mka"))
        else:
            muxer, ext = _SUBS.get(codec) or ("matroska", "mks")
        base = stem + "." + _language(s.get("tags") or {})
        if kind == "subtitle" and (s.get("disposition") or {}).get("forced"):
            base += ".forced"
        name, n = f"{base}.{ext}", 1
        while name in taken:
            n += 1
            name = f"{base}.{n}.{ext}"
        taken.add(name)
        out.append({"index": s["index"], "kind": kind, "codec": codec, "muxer": muxer,
                    "convert": codec == "mov_text", "dest": folder / name})
    return out


def temp_of(dest: Path) -> Path:
    return dest.with_name(TEMP_PREFIX + dest.name)


def pending(src: Path, rel: str, probe: dict | None = None) -> list[dict]:
    """The tracks of `src` whose files are not there yet."""
    return [t for t in tracks(src, rel, probe) if not t["dest"].exists()]


def _drop_empty_up(folder: Path, top: Path) -> None:
    """Remove `folder` and its parents while they are empty, up to `top`."""
    while folder != top and top in folder.parents:
        try:
            folder.rmdir()
        except OSError:
            return
        folder = folder.parent


def extract(src: Path, rel: str, report, cancelled, temps) -> list[Path]:
    """Write every track of `src` not yet extracted. `report(pid=..., percent=...)`
    is told ffmpeg's pid and how far it is (0–100 of this video); `temps(paths)`
    the temporary files about to be written, so a restart can clear them.
    Returns the files written (none when all were there)."""
    probe = movie_prep._probe(src)
    todo = pending(src, rel, probe)
    if not todo:
        return []
    top = root()
    for t in todo:
        t["dest"].parent.mkdir(parents=True, exist_ok=True)
    temps([str(temp_of(t["dest"])) for t in todo])
    cmd = [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-progress", "pipe:1", "-i", str(src)]
    for t in todo:
        cmd += ["-map", f"0:{t['index']}", "-c", "srt" if t["convert"] else "copy"]
        if t["muxer"] in _NO_TIMESTAMPS:
            cmd += ["-bsf:a", "setts=ts=N"]
        cmd += ["-f", t["muxer"], str(temp_of(t["dest"]))]
    try:
        total = float(probe.get("format", {}).get("duration") or 0)
    except ValueError:
        total = 0.0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # Drained as it comes, keeping the end for the error: a file that has
    # ffmpeg complain once per packet would otherwise fill the pipe and stop
    # ffmpeg dead.
    tail: collections.deque[str] = collections.deque(maxlen=5)
    drain = threading.Thread(target=lambda: tail.extend(proc.stderr), daemon=True)
    drain.start()
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
        proc.wait()
        drain.join(timeout=5)
        err = "".join(tail)
    finally:
        report(pid=None)
    if cancelled() or proc.returncode != 0:
        for t in todo:
            temp_of(t["dest"]).unlink(missing_ok=True)
        for folder in {t["dest"].parent for t in todo}:
            _drop_empty_up(folder, top)
        temps([])
        if cancelled():
            raise InterruptedError("stopped")
        raise RuntimeError(f"{src.name}: ffmpeg failed — {err.strip()[-300:] or proc.returncode}")
    for t in todo:
        temp_of(t["dest"]).replace(t["dest"])
    temps([])
    return [t["dest"] for t in todo]
