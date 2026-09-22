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
import re
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
    MOVIE_STAGING,
)
from api.services import movie_subs

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
def roots() -> dict[str, Path]:
    """Every folder a movie id may point into.

    The library is the unnamed root; each staging area adds its inbox, so a
    film can be *played* while it is still being prepared — which is the
    point of the whole arrangement: you check the subtitle timing in the
    player and only then commit the remux."""
    out = {"": MOVIES_DIR}
    for name, cfg in (MOVIE_STAGING or {}).items():
        if not name:
            continue
        inbox = str((cfg or {}).get("inbox") or "").strip()
        if inbox:
            out[name] = Path(inbox).expanduser()
        # The area's output folder is addressable too, so a film that has
        # been prepared can still be played and inspected without moving it.
        # "output" is the current key, "library" the older spelling — kept in
        # step with movie_prep.areas(), which cannot be imported here without
        # a cycle.
        dest = str((cfg or {}).get("output") or (cfg or {}).get("library") or "").strip()
        out[f"{name}:library"] = Path(dest).expanduser() if dest else MOVIES_DIR
    return out


def _encode_id(path: Path, root_name: str = "") -> str:
    """The id *is* the path relative to its root, percent-encoded so it
    survives a query string, prefixed with `@<area>/` when that root isn't
    the library. Keeping it readable (rather than hashing) means a stream URL
    stays valid across restarts and says what it points at."""
    rel = str(path.relative_to(roots()[root_name]))
    return quote(f"@{root_name}/{rel}" if root_name else rel, safe="")


def resolve(movie_id: str) -> Path:
    """Decode an id back to a file, refusing anything that escapes its root —
    the id arrives from the client, so `../` is a given."""
    rel = unquote(movie_id or "").strip()
    if not rel:
        raise MovieError("missing movie id")
    root_name = ""
    if rel.startswith("@"):
        root_name, _, rel = rel[1:].partition("/")
    available = roots()
    if root_name not in available:
        raise MovieError(f"unknown movie area {root_name!r}", 404)
    try:
        root = available[root_name].resolve()
        path = (root / rel).resolve()
    except OSError as e:
        raise MovieError(f"bad movie id: {e}")
    if root != path and root not in path.parents:
        raise MovieError("movie id outside its folder", 403)
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


def _sub_canvas(idx_path: Path) -> tuple[int | None, int | None]:
    """The canvas a bitmap sidecar was authored against, from its .idx."""
    try:
        raw = _run([FFPROBE, "-v", "error", "-print_format", "json",
                    "-show_streams", "-select_streams", "s", str(idx_path)],
                   _PROBE_TIMEOUT)
        streams = json.loads(raw).get("streams", [])
        if streams:
            return streams[0].get("width"), streams[0].get("height")
    except Exception:
        pass
    return None, None


def _sub_label(n: int, language: str, fmt: str, flags: list[str],
               source: str, name: str = "") -> str:
    """What the dropdown shows. Language first because that is what anyone is
    actually choosing by; the source last because it is the tiebreaker when
    the same language shows up embedded, in the folder and uploaded."""
    lang = language_name(language)
    bits = [lang or (Path(name).stem if name else "Unknown")]
    if flags:
        bits.append(" ".join(sorted(flags)))
    parts = [" ".join(bits), fmt or "?"]
    if source != "embedded":
        parts.append(source)
    return f"{n + 1}. " + " · ".join(p for p in parts if p)


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


def _folder_subs(video: Path) -> list[dict]:
    """Subtitle files sitting next to the film, the way a desktop player finds
    them — including the ones that aren't text.

    Three things this has to get right:

    * **VobSub pairs.** ``.idx`` + ``.sub`` are one subtitle in two files: the
      ``.idx`` carries the index and the canvas size, the ``.sub`` the bitmaps.
      ffmpeg is handed the ``.idx``; offering the ``.sub`` separately would
      produce a track that looks selectable and renders nothing.
    * **Ownership.** A subtitle belongs to the video it is named after. With
      one video in the folder — which is every folder in this library — that
      is simply all of them, and it has to be, or a file called
      ``Vietnamese.srt`` would be discarded for not repeating the title.
      With several videos, the longest matching stem wins and unmatched files
      belong to none, which is the case this rule exists for.
    * **Language.** A sidecar's language lives in its filename and nowhere
      else, so it is read here or not at all.
    """
    folder = video.parent
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []

    videos, subs = [], []
    for entry in entries:
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        ext = entry.suffix.lower()
        if ext in VIDEO_EXT:
            videos.append(entry)
        elif ext in SUB_EXT or ext == ".idx":
            subs.append(entry)

    idx_stems = {e.stem.lower() for e in subs if e.suffix.lower() == ".idx"}
    out = []
    for entry in subs:
        ext = entry.suffix.lower()
        if ext == ".sub":
            # Only meaningful through its .idx. A .sub with no .idx beside it
            # is unusable, not merely awkward, so it is dropped either way.
            continue
        if ext == ".idx" and entry.stem.lower() not in idx_stems:
            continue

        if len(videos) > 1:
            owner = max(
                (v for v in videos if entry.stem.lower().startswith(v.stem.lower())),
                key=lambda v: len(v.stem), default=None,
            )
            if owner != video:
                continue

        lang, flags = parse_sub_name(entry.name, video.stem)
        out.append({
            "path": entry,
            "kind": "image" if ext == ".idx" else "text",
            "language": lang,
            "flags": flags,
            "name": entry.name,
            "format": "VobSub" if ext == ".idx" else ext.lstrip(".").upper(),
        })
    return out


# ── identity ─────────────────────────────────────────────────────────────
# Enough of the file to be unique, cheap enough to compute on a network mount:
# two 64 KB reads and the size, rather than hashing 19 GB at 30 MB/s.
_FP_CHUNK = 64 * 1024
_fp_cache: dict[str, str] = {}
_fp_lock = threading.Lock()


def fingerprint(path: Path) -> str:
    """A stable id for a film, derived from the file itself rather than from
    where it happens to live.

    Uploaded subtitles are stored outside the library and linked to a film by
    this, so it has to survive the things that happen to a media folder:
    renaming, reorganising, moving the whole library to another disk. A path
    would not. A full content hash would, but costs ten minutes on a 19 GB
    file — while size plus the head and tail is unique across any real
    library and costs two reads."""
    st = path.stat()
    key = f"{path}|{st.st_mtime_ns}|{st.st_size}"
    with _fp_lock:
        hit = _fp_cache.get(key)
    if hit:
        return hit
    h = hashlib.sha1(str(st.st_size).encode())
    with path.open("rb") as f:
        h.update(f.read(_FP_CHUNK))
        if st.st_size > _FP_CHUNK * 2:
            f.seek(-_FP_CHUNK, os.SEEK_END)
            h.update(f.read(_FP_CHUNK))
    out = h.hexdigest()[:16]
    with _fp_lock:
        _fp_cache[key] = out
    return out


# ── subtitle naming ──────────────────────────────────────────────────────
# Sidecar subtitles carry their language in the filename and nowhere else, so
# this is the only chance to read it. Both the 2- and 3-letter codes turn up
# in the wild, and so do plain English names.
# Display name -> every spelling that turns up in a filename or a stream tag:
# ISO 639-1, and both ISO 639-2 variants (bibliographic `ger`/`fre`, and
# terminological `deu`/`fra`), because subtitle files in the wild use all of
# them interchangeably. The display name itself is also a valid spelling —
# this library has files called `Vietnamese.srt` and `Serbian.srt`.
LANGUAGES: dict[str, list[str]] = {
    "English": ["en", "eng"],
    "Italian": ["it", "ita"],
    "French": ["fr", "fre", "fra"],
    "Spanish": ["es", "spa"],
    "German": ["de", "ger", "deu"],
    "Portuguese": ["pt", "por"],
    "Dutch": ["nl", "dut", "nld"],
    "Russian": ["ru", "rus"],
    "Polish": ["pl", "pol"],
    "Swedish": ["sv", "swe"],
    "Norwegian": ["no", "nor"],
    "Danish": ["da", "dan"],
    "Finnish": ["fi", "fin"],
    "Icelandic": ["is", "ice", "isl"],
    "Greek": ["el", "gre", "ell"],
    "Czech": ["cs", "cze", "ces"],
    "Slovak": ["sk", "slo", "slk"],
    "Slovenian": ["sl", "slv"],
    "Hungarian": ["hu", "hun"],
    "Romanian": ["ro", "rum", "ron"],
    "Bulgarian": ["bg", "bul"],
    "Croatian": ["hr", "hrv"],
    "Serbian": ["sr", "srp"],
    "Bosnian": ["bs", "bos"],
    "Macedonian": ["mk", "mac", "mkd"],
    "Albanian": ["sq", "alb", "sqi"],
    "Ukrainian": ["uk", "ukr"],
    "Turkish": ["tr", "tur"],
    "Hebrew": ["he", "heb"],
    "Arabic": ["ar", "ara"],
    "Persian": ["fa", "per", "fas"],
    "Kurdish": ["ku", "kur"],
    "Hindi": ["hi", "hin"],
    "Bengali": ["bn", "ben"],
    "Tamil": ["ta", "tam"],
    "Urdu": ["ur", "urd"],
    "Thai": ["th", "tha"],
    "Vietnamese": ["vi", "vie"],
    "Indonesian": ["id", "ind"],
    "Malay": ["ms", "may", "msa"],
    "Filipino": ["tl", "tgl", "fil"],
    "Chinese": ["zh", "chi", "zho"],
    "Japanese": ["ja", "jpn"],
    "Korean": ["ko", "kor"],
    "Estonian": ["et", "est"],
    "Latvian": ["lv", "lav"],
    "Lithuanian": ["lt", "lit"],
    "Catalan": ["ca", "cat"],
}

# Spellings that aren't codes at all — what people actually type, including
# one misspelling this library contains (`Servian.srt`).
_LANGUAGE_ALIASES = {
    "brazilian": "Portuguese", "brasil": "Portuguese", "ptbr": "Portuguese",
    "italiano": "Italian", "esp": "Spanish", "castellano": "Spanish",
    "espanol": "Spanish", "deutsch": "German", "francais": "French",
    "farsi": "Persian", "servian": "Serbian", "simplified": "Chinese",
    "traditional": "Chinese", "mandarin": "Chinese", "cantonese": "Chinese",
    "latino": "Spanish", "nederlands": "Dutch", "svenska": "Swedish",
}

_LOOKUP: dict[str, str] = {}
for _display, _codes in LANGUAGES.items():
    _LOOKUP[_display.lower()] = _display
    for _c in _codes:
        _LOOKUP[_c] = _display
_LOOKUP.update(_LANGUAGE_ALIASES)

# Tags that qualify a track rather than name it.
_SUB_FLAGS = {"forced", "sdh", "cc", "hi", "foreign"}


def language_name(code: str) -> str:
    """"ita" / "it" / "Italiano" -> "Italian". Anything unrecognised comes
    back upper-cased rather than blank, so an odd code still labels a track."""
    code = (code or "").strip().lower()
    return _LOOKUP.get(code, code.upper() if code else "")


def parse_sub_name(name: str, video_stem: str) -> tuple[str, list[str]]:
    """Pull a language and any flags out of a sidecar filename.

    ``A Star Is Born (2018).fr.forced.srt`` -> ("fra", ["forced"])
    ``Brazilian Portuguese.srt``            -> ("por", [])

    Whatever is left of the name after stripping the film's own title is what
    carries the meaning, so that part is what gets inspected — but a file
    named after nothing but its language works too, which is what a folder
    like Downfall's `Vietnamese.srt` relies on."""
    stem = Path(name).stem
    trimmed = stem[len(video_stem):] if stem.lower().startswith(video_stem.lower()) else stem
    tokens = [t for t in re.split(r"[.\-_ \[\]()]+", trimmed.lower()) if t]
    lang, flags = "", []
    for token in tokens:
        if token in _SUB_FLAGS:
            flags.append(token)
        elif not lang and token in _LOOKUP:
            lang = _LOOKUP[token]
    return lang, flags


_probe_cache: dict[str, dict] = {}
_probe_lock = threading.Lock()


def forget(movie_id: str) -> None:
    """Drop a film's cached probe. The probe key is (path, mtime, size), which
    is exactly right for the file and exactly wrong for the subtitles attached
    to it from outside — uploading one changes nothing about the film."""
    try:
        path = resolve(movie_id)
    except MovieError:
        return
    st = path.stat()
    with _probe_lock:
        _probe_cache.pop(f"{path}|{st.st_mtime_ns}|{st.st_size}", None)


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
                    "key": f"audio:{n}",
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
                    "key": f"embedded:{n}",
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
                    "source": "embedded",
                    "language": _lang(tags),
                    "label": _sub_label(
                        n, _lang(tags), CODEC_NAMES.get(codec, codec.upper()),
                        [f for f in ("forced", "hearing_impaired")
                         if (s.get("disposition") or {}).get(f)],
                        "embedded", (tags.get("title") or "").strip(),
                    ),
                }
            )

    for found in _folder_subs(path):
        n = len(subs)
        width = height = None
        if found["kind"] == "image":
            # A VobSub's canvas is almost never the video's size, and the
            # overlay has to reconcile the two -- see build_command. The .idx
            # states it, so ask.
            width, height = _sub_canvas(found["path"])
        subs.append({
            "id": n,
            "stream": None,
            "external": str(found["path"]),
            "key": f"folder:{found['name']}",
            "source": "folder",
            "kind": found["kind"],
            "width": width,
            "height": height,
            "language": found["language"],
            "label": _sub_label(n, found["language"], found["format"],
                                found["flags"], "folder", found["name"]),
        })

    for record in movie_subs.for_movie(fingerprint(path)):
        n = len(subs)
        stored = movie_subs.path_for(fingerprint(path), record)
        if not stored.exists():
            continue  # index and disk disagree; the file is what matters
        lang, flags = parse_sub_name(record["name"], path.stem)
        kind = record.get("kind", "text")
        # Uploaded bitmaps need the same canvas reconciliation as ones found
        # in the folder — a .sup or .idx states the size it was authored for,
        # and it is rarely the video's.
        width, height = _sub_canvas(stored) if kind == "image" else (None, None)
        subs.append({
            "id": n,
            "stream": None,
            "external": str(stored),
            "key": f"uploaded:{record['id']}",
            "source": "uploaded",
            "upload_id": record["id"],
            "kind": kind,
            "width": width,
            "height": height,
            "language": lang,
            "label": _sub_label(n, lang,
                                "VobSub" if record.get("aux") else
                                Path(record["name"]).suffix.lstrip(".").upper(),
                                flags, "uploaded", record["name"]),
        })

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
                  sub: int | None, height: int, sub_delay: float = 0.0,
                  audio_delay: float = 0.0) -> list[str]:
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

    # A bitmap sidecar (.idx/.sub) is a second file, so it becomes a second
    # input — and it needs the same -ss, or its timestamps would start at zero
    # while the video starts at `start` and every subtitle would appear early
    # by exactly the seek distance.
    if chosen and chosen["kind"] == "image" and chosen["external"]:
        if start > 0:
            cmd += ["-ss", f"{start:.3f}"]
        cmd += ["-i", chosen["external"]]

    if not remux:
        cmd += ["-filter_complex",
                _video_graph(path, meta, start, chosen, height, sub_delay),
                "-map", "[v]"]
    else:
        cmd += ["-map", "0:v:0"]

    if meta["audio"]:
        track = audio if audio is not None and 0 <= audio < len(meta["audio"]) else 0
        # Downmix to stereo: browsers can decode 5.1 AAC but most people are
        # listening on two channels, where a straight passthrough buries the
        # dialogue in the centre channel.
        cmd += ["-map", f"0:a:{track}"]
        if audio_delay:
            # Positive means the audio should arrive later, so it is padded
            # with that much silence; negative means it is running late
            # already, so the head is trimmed off. asetpts rebases afterwards
            # because atrim leaves the original timestamps behind, which the
            # muxer would otherwise honour and undo the trim.
            ms = int(round(audio_delay * 1000))
            cmd += ["-af", f"adelay=all=1:delays={ms}ms" if ms > 0
                    else f"atrim=start={abs(audio_delay):.3f},asetpts=PTS-STARTPTS"]
        cmd += ["-c:a", "aac", "-ac", "2", "-b:a", abr]
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
                 height: int, sub_delay: float = 0.0) -> str:
    """The -filter_complex for a transcode, ending in [v].

    ``sub_delay`` is in seconds, positive meaning the subtitles should appear
    *later*. It is applied differently for the two subtitle kinds, because
    they reach the graph by different routes — see below."""
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
        # authored for, and overlay honours them literally — so the two
        # coordinate spaces have to be made one before overlaying.
        #
        # The canvas differs from the video in two quite different ways, and
        # treating them alike gets one of them badly wrong:
        #
        #   1920x1080 subs over 1920x800 video — same width. The film was
        #   encoded with the letterbox cropped off; the subtitles still sit
        #   where the bar used to be. Give the picture the bar back.
        #
        #   1920x1080 subs over 720x384 video — different width. Same film at
        #   a different size, nothing cropped. Padding to 1920x1080 here would
        #   strand a small picture in the middle of a huge black frame.
        #
        # Matching widths first tells them apart: scale the subtitle canvas so
        # its width equals the video's, and whatever height that lands on is
        # in the video's own units. If it is taller, the difference really is
        # letterbox and the picture gets padded to meet it.
        pre += tonemap
        sw = chosen.get("width") or 0
        sh = chosen.get("height") or 0
        # Input 1 when the bitmaps came from a sidecar file, input 0 when
        # they were muxed into the film.
        sub_in = "[1:s:0]" if chosen["external"] else f"[0:s:{chosen['stream']}]"
        extra = ""
        steps: list[str] = []
        if sw and sh and vw and vh and (sw, sh) != (vw, vh):
            scaled_h = max(1, round(sh * vw / sw))
            canvas_h = max(vh, scaled_h)
            # rgba before scaling: the decoded bitmaps are paletted, and
            # resampling without an alpha channel would fill the transparent
            # area with solid colour and black out the picture behind it.
            steps = [f"format=rgba", f"scale={vw}:{scaled_h}"]
            if scaled_h < canvas_h:
                steps.append(f"pad={vw}:{canvas_h}:(ow-iw)/2:(oh-ih)/2:color=0x00000000")
            if canvas_h > vh:
                pre.append(f"pad={vw}:{canvas_h}:(ow-iw)/2:(oh-ih)/2")
        # Bitmaps arrive as their own stream, so the delay is simply a shift
        # of that stream's timestamps — push them forward and they land on
        # later frames. Applied first, before any resampling.
        if sub_delay:
            steps.insert(0, f"setpts=PTS+{sub_delay:.3f}/TB")
        if steps:
            extra = f"{sub_in}{','.join(steps)}[sub];"
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
        # libass renders against the *file's* clock, so the frames are put
        # back on it for the duration of this filter and rebased afterwards.
        # The delay rides on that same shift: asking libass for the cue at
        # (t - delay) instead of t is what makes a subtitle appear `delay`
        # seconds later. Positive shifts subtitles later, negative earlier.
        shift = start - sub_delay
        if shift:
            pre.append(f"setpts=PTS+{shift:.3f}/TB")
        pre.append(f"subtitles=filename='{ass}'")
        if shift:
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
            sub: int | None = None, height: int = DEFAULT_HEIGHT,
            sub_delay: float = 0.0, audio_delay: float = 0.0) -> list[str]:
    """Everything that blocks — resolving the path, ffprobe, and extracting a
    subtitle track if this is the first time anyone asked for it. Belongs in a
    threadpool; `open_stream` below must not block the event loop."""
    path = resolve(movie_id)
    meta = info(movie_id)
    duration = meta["duration"]
    start = max(0.0, min(start, max(0.0, duration - 1))) if duration else max(0.0, start)
    return build_command(path, meta, start, audio, sub, height,
                         sub_delay, audio_delay)


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
