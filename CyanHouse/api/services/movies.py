"""Movies service — browse a local film library and stream any file to a
browser, transcoded on demand.

The library is assumed to be *anything*: mkv/mp4/avi containers, H.264 or
HEVC (8- or 10-bit, SDR or HDR), FLAC/DTS/TrueHD audio, and subtitles that
are either text (SRT/ASS, embedded or a sidecar file) or bitmaps browsers
can't render at all (PGS/VobSub). Rather than guess what a given browser
will accept, every stream is a full transcode to H.264 + AAC in a fragmented
MP4, with subtitles **burned into the picture**.

Burn-in is the point, not a shortcut: the subtitle lands on the exact frame
its timestamp names, in the same pass that produces that frame. There is no
second clock in the browser to drift against, no WebVTT conversion, and
image subtitles work like any other — so what you see is what the file
actually says, which is what makes this usable for checking sync.

The cost of that choice is seeking. A transcode into a pipe has no byte
ranges and no index, so the browser cannot seek it. Instead the *server*
seeks: every seek is a new request with `t=`, which kills the old ffmpeg and
starts a new one at that timestamp, and the frontend adds `t` back on to
`video.currentTime` to show the real position. Track and quality changes are
the same restart.

Three details make that restart correct, and all three are easy to get
silently wrong:

* ``-ss`` **before** ``-i`` so the seek is a demuxer seek (instant on a 12 GB
  file) rather than decode-and-discard from 0.
* The ``subtitles`` filter opens the subtitle file *itself* and knows nothing
  about that seek, so it would render from 00:00 — i.e. invent a desync. The
  ``setpts=PTS+t/TB`` … ``setpts=PTS-STARTPTS`` sandwich around it puts the
  video back on source time while libass renders, then rebases to 0.
  Bitmap subs don't need this: they come through the same seeked demuxer as
  the video, so overlay gets matching timestamps for free.
* Nothing here resamples audio to "fix" drift (no ``-async``, no
  ``aresample=async``) — a tool for judging sync must not have an opinion
  about it.

Contract picked up by ``api/main.py`` auto-discovery: ``router`` (in
``api/routers/movies.py``) and ``init()``. No DB, so no version counter —
the library is the filesystem.
"""
import asyncio
import atexit
import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

from api.config import (
    FFMPEG,
    FFPROBE,
    MOVIES_CACHE_DIR,
    MOVIES_DIR,
    MOVIES_ENCODER,
    MOVIES_IDLE_TIMEOUT,
    MOVIES_MAX_STREAMS,
    MOVIES_SCAN_TTL,
)

VIDEO_EXT = {
    ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".wmv",
    ".mpg", ".mpeg", ".m2ts", ".ts", ".flv", ".ogv", ".divx",
}
SUB_EXT = {".srt", ".ass", ".ssa", ".vtt", ".sub"}
# Bitmap subtitle codecs: these can only ever be overlaid, never converted to
# text, which is why the subtitle kind decides the whole filter chain below.
IMAGE_SUB_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}
# Transfer characteristics that mean HDR — the picture needs tone-mapping to
# SDR or it comes out grey and flat in a browser.
HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}
# ffprobe's codec names are accurate but not what anyone calls these.
CODEC_NAMES = {
    "hdmv_pgs_subtitle": "PGS", "dvd_subtitle": "VobSub", "dvb_subtitle": "DVB",
    "subrip": "SRT", "ass": "ASS", "ssa": "SSA", "mov_text": "MP4 text",
    "webvtt": "VTT", "eac3": "E-AC3", "truehd": "TrueHD", "dts": "DTS",
    "pcm_s16le": "PCM", "pcm_s24le": "PCM", "opus": "Opus", "vorbis": "Vorbis",
}

# H.264 profiles every browser decodes. "High 10", "High 4:2:2" and
# "High 4:4:4 Predictive" are H.264 too, and none of them play.
BROWSER_H264_PROFILES = {"baseline", "constrained baseline", "main", "high"}

# Height -> (video bitrate, audio bitrate). Deliberately conservative: this
# is re-encoded live, and a stall costs more than a little softness.
LADDER = {
    360: ("800k", "128k"),
    480: ("1400k", "128k"),
    720: ("3000k", "160k"),
    1080: ("6000k", "192k"),
}
# 360p by default. This panel exists to check a file, not to show it off:
# the smaller the frame, the less work per seek and the more headroom on a
# 4K HDR source that only just keeps up at 720p (measured 1.46x realtime at
# 360p vs 1.19x at 720p vs 0.98x -- stalling -- at 1080p).
DEFAULT_HEIGHT = 360

_PROBE_TIMEOUT = 60
# Pulling one subtitle track out of a container means demuxing the whole
# thing, so the cost scales with file size, not subtitle size: under a second
# for a 3 GB rip, minutes for a 19 GB 4K one on a network mount. It is paid
# once per (file, track) and then cached forever, so the ceiling is generous.
_SUB_EXTRACT_TIMEOUT = 1800


class MovieError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ── library ──────────────────────────────────────────────────────────────
def _encode_id(path: Path) -> str:
    """The id *is* the path relative to MOVIES_DIR, percent-encoded so it
    survives a query string. Keeping it readable (rather than hashing) means
    a stream URL stays valid across restarts and says what it points at."""
    return quote(str(path.relative_to(MOVIES_DIR)), safe="")


def resolve(movie_id: str) -> Path:
    """Decode an id back to a file, refusing anything that escapes the
    library root — the id arrives from the client, so `../` is a given."""
    rel = unquote(movie_id or "").strip()
    if not rel:
        raise MovieError("missing movie id")
    try:
        path = (MOVIES_DIR / rel).resolve()
        root = MOVIES_DIR.resolve()
    except OSError as e:
        raise MovieError(f"bad movie id: {e}")
    if root != path and root not in path.parents:
        raise MovieError("movie id outside the library", 403)
    if not path.is_file():
        raise MovieError("no such movie", 404)
    return path


def _main_video_file(folder: Path) -> Path | None:
    """One folder = one film, so the biggest video file in it is the film —
    which also skips the sample/extra/behind-the-scenes clips some rips ship
    alongside it."""
    best: tuple[int, Path] | None = None
    try:
        entries = list(folder.iterdir())
    except OSError:
        return None
    for entry in entries:
        try:
            if entry.is_file() and entry.suffix.lower() in VIDEO_EXT:
                size = entry.stat().st_size
                if best is None or size > best[0]:
                    best = (size, entry)
            elif entry.is_dir():  # e.g. a BDMV-style extra level
                inner = _main_video_file(entry)
                if inner is not None:
                    size = inner.stat().st_size
                    if best is None or size > best[0]:
                        best = (size, inner)
        except OSError:
            continue
    return best[1] if best else None


_scan_lock = threading.Lock()
_scan_cache: tuple[float, list[dict]] | None = None


def list_movies(refresh: bool = False) -> list[dict]:
    """Every immediate child of MOVIES_DIR that resolves to a video file, as
    ``{id, title, file, size}``. Cached: the library lives on a network
    mount, where stat()ing a few hundred folders is not free."""
    global _scan_cache
    with _scan_lock:
        if not refresh and _scan_cache and time.time() - _scan_cache[0] < MOVIES_SCAN_TTL:
            return _scan_cache[1]
        if not MOVIES_DIR.is_dir():
            raise MovieError(f"movie library not found at {MOVIES_DIR}", 503)
        out: list[dict] = []
        for entry in sorted(MOVIES_DIR.iterdir(), key=lambda p: p.name.lower()):
            try:
                if entry.is_dir():
                    path = _main_video_file(entry)
                    title = entry.name
                elif entry.suffix.lower() in VIDEO_EXT:
                    path, title = entry, entry.stem
                else:
                    continue
                if path is None:
                    continue
                out.append(
                    {
                        "id": _encode_id(path),
                        "title": title,
                        "file": path.name,
                        "size": path.stat().st_size,
                    }
                )
            except OSError:
                continue
        _scan_cache = (time.time(), out)
        return out


# ── probe ────────────────────────────────────────────────────────────────
def _run(cmd: list[str], timeout: int) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise MovieError(f"{cmd[0]} is not installed on the server", 503)
    except subprocess.TimeoutExpired:
        raise MovieError(f"{cmd[0]} timed out", 504)
    if res.returncode != 0:
        tail = res.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise MovieError(" / ".join(tail) or f"{cmd[0]} failed", 502)
    return res.stdout.decode("utf-8", "replace")


def _lang(tags: dict) -> str:
    return (tags.get("language") or tags.get("LANGUAGE") or "").strip()


def _label(kind: str, n: int, codec: str, tags: dict, extra: str = "") -> str:
    lang = _lang(tags) or "und"
    title = (tags.get("title") or "").strip()
    bits = [lang.upper()]
    if title and title.lower() != lang.lower():
        bits.append(title)
    bits.append(CODEC_NAMES.get(codec, codec.upper()))
    if extra:
        bits.append(extra)
    return f"{n + 1}. " + " · ".join(bits)


def _sidecar_subs(video: Path) -> list[Path]:
    """Subtitle files sitting next to the film (``Movie.en.srt``). Ones named
    after it win; if none are, every subtitle file in the folder is offered,
    since a folder here holds exactly one film anyway."""
    found = []
    try:
        entries = sorted(video.parent.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    for entry in entries:
        try:
            if entry.is_file() and entry.suffix.lower() in SUB_EXT:
                found.append(entry)
        except OSError:
            continue
    named = [p for p in found if p.stem.lower().startswith(video.stem.lower())]
    return named or found


_probe_cache: dict[str, dict] = {}
_probe_lock = threading.Lock()


def info(movie_id: str) -> dict:
    """Everything the player needs to draw itself: duration plus the audio
    and subtitle tracks it can choose between. Cached per (path, mtime,
    size) — an ffprobe on a network mount is ~a second, and the player asks
    again on every film you click."""
    path = resolve(movie_id)
    st = path.stat()
    key = f"{path}|{st.st_mtime_ns}|{st.st_size}"
    with _probe_lock:
        hit = _probe_cache.get(key)
    if hit:
        return hit

    raw = _run(
        [FFPROBE, "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", str(path)],
        _PROBE_TIMEOUT,
    )
    data = json.loads(raw)
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    video = None
    audio: list[dict] = []
    subs: list[dict] = []
    for s in streams:
        kind = s.get("codec_type")
        tags = s.get("tags") or {}
        if kind == "video":
            # Cover art / poster streams are "video" too; they're marked as
            # attached_pic and must not be mistaken for the film.
            if (s.get("disposition") or {}).get("attached_pic"):
                continue
            if video is None:
                video = {
                    "codec": s.get("codec_name", ""),
                    "width": s.get("width"),
                    "height": s.get("height"),
                    "hdr": s.get("color_transfer") in HDR_TRANSFERS,
                    "pix_fmt": s.get("pix_fmt", ""),
                    "profile": s.get("profile", ""),
                }
        elif kind == "audio":
            n = len(audio)
            ch = s.get("channels")
            audio.append(
                {
                    "id": n,
                    "language": _lang(tags),
                    "label": _label("a", n, s.get("codec_name", "?"), tags,
                                    f"{ch}ch" if ch else ""),
                    "default": bool((s.get("disposition") or {}).get("default")),
                }
            )
        elif kind == "subtitle":
            n = len(subs)
            codec = s.get("codec_name", "?")
            image = codec in IMAGE_SUB_CODECS
            subs.append(
                {
                    "id": n,
                    "stream": n,          # index among subtitle streams
                    "external": None,
                    "kind": "image" if image else "text",
                    # The canvas these bitmaps were authored against, which is
                    # often NOT the video's size — a 2.40:1 encode with the
                    # letterbox cropped away keeps subtitles positioned for
                    # the uncropped frame. build_command has to reconcile the
                    # two or the subtitles fall off the bottom of the picture.
                    "width": s.get("width"),
                    "height": s.get("height"),
                    "language": _lang(tags),
                    "label": _label("s", n, codec, tags, "image" if image else ""),
                }
            )

    for extra in _sidecar_subs(path):
        n = len(subs)
        subs.append(
            {
                "id": n,
                "stream": None,
                "external": str(extra),
                "kind": "text",
                "width": None,
                "height": None,
                "language": "",
                "label": f"{n + 1}. {extra.name} · file",
            }
        )

    if video is None:
        raise MovieError("no video stream in that file", 422)

    remux_ok, remux_why = remux_verdict(video)

    out = {
        "id": movie_id,
        "title": path.parent.name if path.parent != MOVIES_DIR else path.stem,
        "file": path.name,
        "duration": float(fmt.get("duration") or 0.0),
        "size": st.st_size,
        "video": video,
        "audio": audio,
        "subtitles": subs,
        # Every rung is offered whatever the source is: the scale filter
        # never upscales, so picking 1080 for a 576p rip just gets 576 — and
        # a 2.39:1 film is only 800px tall while still being "1080p".
        "heights": ([0] if remux_ok else []) + sorted(LADDER),
        # 0 in `heights` is the "Original" rung: no re-encode at all.
        "remux": {"ok": remux_ok, "reason": remux_why},
        "encoder": encoder(),
    }
    with _probe_lock:
        _probe_cache[key] = out
    # Extraction is slow on big files and would otherwise happen inside the
    # first stream request, where the browser is already waiting for video.
    # Picking a film in the UI calls this endpoint, so start the work now and
    # let it run while the user is still deciding whether to press play.
    _warm_text_subs(path, subs)
    return out


def _warm_text_subs(path: Path, subs: list[dict]) -> None:
    text = [x for x in subs if x["kind"] == "text"]
    if not text:
        return

    def run() -> None:
        for entry in text:
            try:
                _text_sub_file(path, entry)
            except Exception as e:
                print(f"movies: could not pre-extract subtitles for {path.name}: {e}")

    threading.Thread(target=run, daemon=True).start()


def remux_verdict(video: dict) -> tuple[bool, str]:
    """Whether the video stream can be handed to the browser untouched.

    When it can, the whole transcode collapses to a container change plus an
    audio re-encode — measured at ~9x realtime on 40% of one core, against
    ~1x (and stalling) for a real transcode. The video is also bit-exact,
    since nothing re-encodes it.

    The catch is that it rules out burned-in subtitles: you cannot draw on a
    picture you are not decoding. Callers fall back to transcoding whenever a
    subtitle track is selected."""
    codec = (video.get("codec") or "").lower()
    if codec != "h264":
        return False, f"{codec.upper() or 'this'} video has to be re-encoded for the browser"
    if (video.get("profile") or "").lower() not in BROWSER_H264_PROFILES:
        return False, f"H.264 {video.get('profile')} is not a profile browsers decode"
    if (video.get("pix_fmt") or "") != "yuv420p":
        return False, f"{video.get('pix_fmt')} has to be converted to 8-bit 4:2:0"
    if video.get("hdr"):
        return False, "HDR has to be tone-mapped to SDR"
    return True, "sent as-is, no re-encoding"


# ── encoder choice ───────────────────────────────────────────────────────
_encoder: str | None = None


def encoder() -> str:
    """h264_nvenc if this build *and* this GPU actually accept it — `ffmpeg
    -encoders` listing it proves nothing, a driverless or too-old card only
    fails when you ask it to encode. So ask it, once, with a one-frame clip."""
    global _encoder
    if _encoder:
        return _encoder
    if MOVIES_ENCODER and MOVIES_ENCODER != "auto":
        _encoder = MOVIES_ENCODER
        return _encoder
    try:
        res = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "testsrc=size=320x180:rate=25", "-frames:v", "1",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, timeout=30,
        )
        _encoder = "h264_nvenc" if res.returncode == 0 else "libx264"
    except Exception:
        _encoder = "libx264"
    print(f"movies: using {_encoder}")
    return _encoder


# ── subtitle materialisation ─────────────────────────────────────────────
def _cache_dir() -> Path:
    """Absolute, always: DATA_DIR may be relative (it is, by default), and
    this path is handed to ffmpeg inside a filter argument, where "relative
    to whatever directory uvicorn happens to have been started in" is not a
    property worth depending on."""
    path = MOVIES_CACHE_DIR.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


_extracting: dict[str, threading.Lock] = {}
_extracting_guard = threading.Lock()


def _text_sub_file(path: Path, sub: dict) -> Path:
    """A text subtitle track as a standalone file in the cache, under a name
    made only of hex and ASCII.

    Two reasons this is always materialised, even for a sidecar file that
    could be passed straight to the filter. First, pointing the ``subtitles``
    filter at the .mkv makes libass demux the *whole* 12 GB file before the
    first frame appears (~25s here); extracting the track alone takes under a
    second and is then reused by every seek. Second, filter arguments are
    escaped twice, and film folders are full of ``:`` ``'`` ``,`` ``[`` — a
    generated filename sidesteps that entire class of bug."""
    st = path.stat()
    tag = hashlib.sha1(f"{path}|{st.st_mtime_ns}".encode()).hexdigest()[:16]
    key = f"e{sub['stream']}" if sub["external"] is None else "x" + hashlib.sha1(
        sub["external"].encode()).hexdigest()[:10]
    out = _cache_dir() / f"{tag}_{key}.ass"
    if out.exists() and out.stat().st_size > 0:
        return out

    # One extraction per track at a time. Without this, the background warm-up
    # started by `info()` and the stream request that arrives while it is
    # still running would each demux the same 19 GB file — the second one
    # racing the first to the same output path.
    with _extracting_guard:
        lock = _extracting.setdefault(str(out), threading.Lock())
    with lock:
        if out.exists() and out.stat().st_size > 0:
            return out
        return _extract_text_sub(path, sub, out)


def _extract_text_sub(path: Path, sub: dict, out: Path) -> Path:
    tmp = out.with_suffix(".part.ass")
    if sub["external"] is None:
        # -map the one subtitle stream and nothing else: ffmpeg then skips
        # the video/audio packets instead of decoding them.
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
               "-map", f"0:s:{sub['stream']}", "-c:s", "ass", str(tmp)]
    else:
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
               "-sub_charenc_mode", "auto", "-i", sub["external"],
               "-map", "0:s:0", "-c:s", "ass", str(tmp)]
    _run(cmd, _SUB_EXTRACT_TIMEOUT)
    os.replace(tmp, out)
    return out


def _escape_for_filter(path: Path) -> str:
    """Inside a filtergraph a path is parsed twice — once as the graph, once
    as the filter's own argument list. `_text_sub_file` guarantees the
    *filename* is boring, but the cache directory above it still comes from
    config, so escape what would terminate an argument anyway."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


# ── ffmpeg command ───────────────────────────────────────────────────────
TONEMAP = [
    "zscale=transfer=linear:npl=100",
    "tonemap=tonemap=hable:desat=0",
    "zscale=transfer=bt709:matrix=bt709:primaries=bt709:range=tv",
]


def build_command(path: Path, meta: dict, start: float, audio: int | None,
                  sub: int | None, height: int) -> list[str]:
    vid = meta["video"]
    subs = meta["subtitles"]
    chosen = subs[sub] if sub is not None and 0 <= sub < len(subs) else None
    # height 0 = "Original": stream-copy the video. Impossible with subtitles,
    # which have to be drawn onto decoded frames, so a selected track silently
    # promotes this back to a real transcode at the top rung.
    remux = height == 0 and meta.get("remux", {}).get("ok") and chosen is None
    if height == 0 and not remux:
        height = max(LADDER)

    vbr, abr = LADDER.get(height, LADDER[DEFAULT_HEIGHT])

    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start > 0:
        # Before -i: a demuxer seek, instant even on a 12 GB file. After -i it
        # would decode and throw away everything up to `start`.
        #
        # One caveat, and only in remux mode: with -c:v copy ffmpeg cannot
        # decode-and-discard up to an exact frame, so the stream really starts
        # at the keyframe at or before `start`. Audio and video stay in sync
        # with each other (both come off the same seek), but the position the
        # player displays can sit a keyframe interval ahead of the picture.
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]

    if not remux:
        cmd += ["-filter_complex", _video_graph(path, meta, start, chosen, height),
                "-map", "[v]"]
    else:
        cmd += ["-map", "0:v:0"]

    if meta["audio"]:
        track = audio if audio is not None and 0 <= audio < len(meta["audio"]) else 0
        # Downmix to stereo: browsers can decode 5.1 AAC but most people are
        # listening on two channels, where a straight passthrough buries the
        # dialogue in the centre channel.
        cmd += ["-map", f"0:a:{track}", "-c:a", "aac", "-ac", "2", "-b:a", abr]
    else:
        cmd += ["-an"]

    if remux:
        cmd += ["-c:v", "copy"]
    else:
        enc = encoder()
        if enc == "h264_nvenc":
            cmd += ["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "ll",
                    "-rc", "vbr", "-b:v", vbr, "-maxrate", vbr, "-bufsize", vbr,
                    "-bf", "0"]
        else:
            cmd += ["-c:v", enc, "-preset", "veryfast", "-tune", "zerolatency",
                    "-b:v", vbr, "-maxrate", vbr, "-bufsize", vbr]
        cmd += ["-g", "48"]

    cmd += [
        # -map_chapters -1 because the MP4 muxer renders a copied chapter list
        # as a `text` track with a SubtitleHandler, which surfaces as a third,
        # pointless "bin_data" stream beside the video and audio. Browsers
        # ignore it, but nothing here uses chapters either.
        "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
        "-max_muxing_queue_size", "1024",
        # A pipe has no seekable tail to write an index into, so the MP4 has
        # to be fragmented: empty_moov puts a playable header up front and
        # each fragment closes itself as it goes.
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4", "pipe:1",
    ]
    return cmd


def _video_graph(path: Path, meta: dict, start: float, chosen: dict | None,
                 height: int) -> str:
    """The -filter_complex for a transcode, ending in [v]."""
    vid = meta["video"]
    vw, vh = vid.get("width") or 0, vid.get("height") or 0
    image_sub = bool(chosen and chosen["kind"] == "image")

    # Never upscale: a 576p DVD rip asked for at 720 stays 576.
    scale = f"scale=-2:'min({height},ih)':flags=bicubic"
    tonemap = list(TONEMAP) if vid["hdr"] else []

    pre: list[str] = []
    post: list[str] = [scale] if image_sub else []

    if image_sub:
        # Bitmap subtitles carry absolute coordinates on the canvas they were
        # authored for, and overlay honours them literally. That canvas is
        # frequently taller than the video — a 2.40:1 film encoded at
        # 1920x800 commonly ships 1920x1080 subtitles positioned down in the
        # letterbox bar, which then land below row 800 and get cropped away.
        # So reconcile the two coordinate spaces before overlaying, and only
        # scale to the requested size afterwards.
        pre += tonemap
        sw = chosen.get("width") or 0
        sh = chosen.get("height") or 0
        sub_in = f"[0:s:{chosen['stream']}]"
        extra = ""
        if sw > vw or sh > vh:
            # Give the picture back the frame the subtitles expect. The bars
            # this adds are the ones the player would draw anyway.
            pre.append(f"pad={max(sw, vw)}:{max(sh, vh)}:(ow-iw)/2:(oh-ih)/2")
        elif sw and sh and (sw < vw or sh < vh):
            # Authored smaller (DVD subs over an upscaled encode): stretch the
            # subtitle canvas onto the picture instead.
            extra = f"{sub_in}scale={vw}:{vh}[sub];"
            sub_in = "[sub]"
        base = ",".join(pre) if pre else "null"
        return (f"{extra}[0:v:0]{base}[base];"
                f"[base]{sub_in}overlay,{','.join(post + ['format=yuv420p'])}[v]")

    # No bitmap overlay to keep aligned, so scale first. That matters a lot on
    # HDR: tone-mapping is CPU-only here and by far the most expensive filter
    # in the chain, and doing it after a 4K->720p downscale feeds it a ninth
    # of the pixels (measured 24.5s -> 14.0s per 10s of 4K HDR).
    pre.append(scale)
    pre += tonemap
    if chosen:  # text subtitles, burned in at the output size
        ass = _escape_for_filter(_text_sub_file(path, chosen))
        if start > 0:
            # libass renders against the *file's* clock; put the frames back
            # on it for the duration of this filter, then rebase to zero.
            pre.append(f"setpts=PTS+{start:.3f}/TB")
        pre.append(f"subtitles=filename='{ass}'")
        if start > 0:
            pre.append("setpts=PTS-STARTPTS")
    pre.append("format=yuv420p")
    return f"[0:v:0]{','.join(pre)}[v]"


# ── live sessions ────────────────────────────────────────────────────────
@dataclass
class _Session:
    sid: str
    # The pid, not the process object. Killing has to work from the event
    # loop, from a request thread (`/stop`, and the implicit stop every seek
    # does) and from the reaper thread, and os.killpg on a pid is the only
    # one of those that is unambiguously safe from all three.
    pid: int
    started: float = field(default_factory=time.time)
    # Last time the client actually took bytes. A paused video stops reading,
    # the socket buffer fills and the generator parks at its `yield`, so this
    # stops advancing — which is also, indistinguishably, what a browser that
    # died without closing its connection looks like. Hence the timeout.
    last_read: float = field(default_factory=time.time)
    errors: deque = field(default_factory=lambda: deque(maxlen=20))


_sessions: dict[str, _Session] = {}
_sessions_lock = threading.Lock()


def _kill(session: _Session) -> None:
    """SIGKILL the whole process group. ffmpeg is spawned in its own session
    (start_new_session), so the group is exactly this transcode."""
    try:
        os.killpg(session.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def stop(sid: str) -> None:
    """Drop whatever this client was watching. Called on every new stream
    from the same client (a seek is a new stream) and when it goes away."""
    with _sessions_lock:
        session = _sessions.pop(sid, None)
    if session:
        _kill(session)


def stop_all() -> None:
    with _sessions_lock:
        sessions = list(_sessions.values())
        _sessions.clear()
    for session in sessions:
        _kill(session)


def _reap_idle() -> None:
    """Kill transcodes nobody is drinking from. A seek, a tab close and a
    panel unmount all say so explicitly (`stop`), and a dropped connection is
    now noticed immediately by `open_stream`. This is the last backstop: a
    client whose machine vanished without the TCP connection ever resetting,
    and a film left paused and forgotten."""
    while True:
        time.sleep(60)
        cutoff = time.time() - MOVIES_IDLE_TIMEOUT
        with _sessions_lock:
            stale = [s for s in _sessions.values() if s.last_read < cutoff]
            for session in stale:
                _sessions.pop(session.sid, None)
        for session in stale:
            print(f"movies: reaping idle stream {session.sid}")
            _kill(session)


def prepare(movie_id: str, sid: str, start: float = 0.0, audio: int | None = None,
            sub: int | None = None, height: int = DEFAULT_HEIGHT) -> list[str]:
    """Everything that blocks — resolving the path, ffprobe, and extracting a
    subtitle track if this is the first time anyone asked for it. Belongs in a
    threadpool; `open_stream` below must not block the event loop."""
    path = resolve(movie_id)
    meta = info(movie_id)
    duration = meta["duration"]
    start = max(0.0, min(start, max(0.0, duration - 1))) if duration else max(0.0, start)
    return build_command(path, meta, start, audio, sub, height)


async def open_stream(sid: str, cmd: list[str]):
    """Spawn the transcode and return an async generator of MP4 bytes.

    Async on purpose. The obvious version — a plain generator doing a
    blocking `proc.stdout.read()` — looks equivalent but leaks: Starlette
    runs a sync generator on a threadpool thread, a thread parked in a
    blocking read cannot be cancelled, and so the cleanup in `finally` does
    not run when the client disappears. Measured: ffmpeg survived a SIGKILLed
    client for at least 45 seconds, both while streaming and while parked.

    Awaiting the read instead means a cancelled request raises straight out
    of the `await`, `finally` runs, and the process dies with the connection.
    """
    stop(sid)  # one stream per client; a seek supersedes what it seeked from
    with _sessions_lock:
        if len(_sessions) >= MOVIES_MAX_STREAMS:
            raise MovieError(
                f"the server is already transcoding {len(_sessions)} streams", 503
            )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError:
        raise MovieError(f"{FFMPEG} is not installed on the server", 503)

    session = _Session(sid=sid, pid=proc.pid)
    with _sessions_lock:
        _sessions[sid] = session

    async def drain_stderr() -> None:
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    return
                text = line.decode("utf-8", "replace").rstrip()
                if text:
                    session.errors.append(text)
        except (asyncio.CancelledError, Exception):
            return

    stderr_task = asyncio.ensure_future(drain_stderr())

    async def generate():
        try:
            while True:
                chunk = await proc.stdout.read(65536)
                if not chunk:
                    break
                session.last_read = time.time()
                yield chunk
        finally:
            _kill(session)
            stderr_task.cancel()
            with _sessions_lock:
                if _sessions.get(sid) is session:
                    del _sessions[sid]
            rc = proc.returncode
            # -9 is us: every seek and every tab close kills a transcode
            # mid-fragment, and ffmpeg always calls that a broken pipe.
            if rc not in (0, None, -9) and session.errors:
                print(f"movies: ffmpeg exited {rc}: "
                      f"{' | '.join(list(session.errors)[-3:])}")

    return generate()


def init() -> None:
    _cache_dir()
    # A transcode is a child process, not a thread: if uvicorn goes down
    # without this, ffmpeg keeps burning cores on a film nobody is watching.
    atexit.register(stop_all)
    threading.Thread(target=_reap_idle, daemon=True).start()
    for tool in (FFMPEG, FFPROBE):
        if shutil.which(tool) is None:
            print(f"WARNING: movies panel needs {tool} on PATH — streaming will 503")
            break
    if not MOVIES_DIR.is_dir():
        print(f"WARNING: movies library {MOVIES_DIR} is not a directory")
