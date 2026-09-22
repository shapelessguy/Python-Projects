"""Prepare a "dirty" download into one clean, self-contained MKV.

This is the CyanHouse counterpart of videoProcessing/preparePlex, which does
the same job as a blocking Windows terminal wizard. The pipeline it encodes is
sound and is kept: identify the film, give every audio and subtitle track a
correct language code, resolve duplicate languages, fix per-track sync, fold
the external subtitles in, drop the junk, emit one file.

What changes is where the decisions get made. In preparePlex you type an
offset, remux, open VLC, discover it's still wrong, and remux again — the
feedback loop runs through a full mux every time. CyanHouse can already play
any track at any delay with the subtitles burned in (see api/services/
movies.py), so the loop closes in the player instead: you *watch* the offset
until it's right, and the remux happens once, at the end, with numbers you
have already seen working.

Three deliberate differences from preparePlex:

* **Nothing is destroyed before the result is checked.** The new file is
  probed and compared against the plan that produced it, and only then do the
  sources move — to a trash folder, not to oblivion.
* **The plan is data.** A dict, saved and replayable, so a batch can be
  decided in one sitting and executed later, and so a failed run can be
  retried without redoing the decisions.
* **It runs headless on Linux.** preparePlex shells out to `tasklist`,
  `taskkill`, `attrib` and `os.startfile`, none of which exist here.

mkvmerge does the muxing, with ffmpeg only as a fallback. That order is not
a preference — it is measured. ffmpeg's matroska muxer refuses to stream-copy
some perfectly good HEVC streams ("Could not write header (incorrect codec
parameters?)"), and the same stream copies into mp4 and ts without complaint,
so it is the MKV muxer specifically. One film in fifteen sampled from this
library hits it; mkvmerge remuxes it without a murmur. ffmpeg also needs
`-fflags +genpts` to survive a track carrying packets with no timestamps,
which an MKV remuxed from AVI commonly does.
"""
import hashlib
import json
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from api.config import (
    FFMPEG,
    FFPROBE,
    MOVIES_DIR,
    MOVIE_STAGING,
)
from api.services import movies

VIDEO_EXT = movies.VIDEO_EXT
SUB_EXT = movies.SUB_EXT | {".idx"}
# Files that come along with a download and never belong in the library.
JUNK_NAMES = {"rarbg.txt", "downloaded_from.txt", "readme.txt", "desktop.ini", "thumbs.db"}
JUNK_EXT = {".nfo", ".txt", ".url", ".sfv", ".md5", ".jpg", ".png", ".exe"}

TRASH_DIR = ".trash"


class PrepError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ── staging areas ────────────────────────────────────────────────────────
def areas() -> dict[str, dict]:
    """The configured staging areas, resolved and checked.

    `library` falls back to MOVIES_DIR so an area can prepare straight into
    the real library; the test area points somewhere else entirely, which is
    the whole reason this is configuration and not a constant."""
    out: dict[str, dict] = {}
    for name, cfg in (MOVIE_STAGING or {}).items():
        inbox = Path(str(cfg.get("inbox", ""))).expanduser()
        # "output" is where finished films are moved to. "library" is the
        # older spelling and still works, because renaming a config key
        # should not silently change where files land.
        dest = cfg.get("output") or cfg.get("library") or MOVIES_DIR
        library = Path(str(dest)).expanduser()
        out[name] = {
            "name": name,
            "inbox": str(inbox),
            "library": str(library),
            "ready": inbox.is_dir(),
            "problem": "" if inbox.is_dir() else f"inbox not found: {inbox}",
        }
    return out


def sources() -> list[dict]:
    """Every folder the panel can browse, in the order it should show them.

    The real library first, named after the folder it actually is rather than
    the word "Library" — and each staging area contributes both its inbox and
    the folder its finished films land in, because seeing what came out is
    part of trusting what went in."""
    out = [{
        "key": "", "label": MOVIES_DIR.name or str(MOVIES_DIR),
        "path": str(MOVIES_DIR), "kind": "library", "ready": MOVIES_DIR.is_dir(),
    }]
    for name, cfg in areas().items():
        out.append({
            "key": name, "label": name, "path": cfg["inbox"],
            "kind": "inbox", "ready": cfg["ready"],
        })
        library = Path(cfg["library"])
        out.append({
            # Qualified by the area: every area's output folder tends to be
            # called the same thing, and two buttons reading "library" say
            # nothing about which one you are about to open.
            "key": f"{name}:library", "label": f"{name} / {library.name or library}",
            "path": str(library), "kind": "output", "ready": library.is_dir(),
        })
    return out


def area(name: str) -> tuple[Path, Path]:
    """One area's (inbox, library), or a clear error naming what is missing.

    A name ending ":library" addresses that area's *output* folder as the
    thing to browse — the same plumbing, pointed the other way."""
    if name.endswith(":library"):
        found = areas().get(name[: -len(":library")])
        if found:
            out = Path(found["library"])
            if not out.is_dir():
                raise PrepError(f"output folder not found: {out}", 503)
            return out, out
    found = areas().get(name)
    if not found:
        known = ", ".join(areas()) or "none configured"
        raise PrepError(f"no staging area called {name!r} (have: {known})", 404)
    if not found["ready"]:
        raise PrepError(found["problem"], 503)
    return Path(found["inbox"]), Path(found["library"])


# ── scanning ─────────────────────────────────────────────────────────────
@dataclass
class Candidate:
    """One folder in a staging area that looks like a film to prepare."""
    folder: Path
    video: Path
    subs: list[Path] = field(default_factory=list)
    junk: list[Path] = field(default_factory=list)
    extra_videos: list[Path] = field(default_factory=list)


def scan(root: Path) -> list[Candidate]:
    """Every folder under `root` holding exactly one film.

    A loose video file directly in the staging root counts too — that is how
    half of them arrive. Folders with more than one video are reported with
    the extras listed rather than skipped silently, which is what preparePlex
    does and it makes them easy to miss."""
    if not root.is_dir():
        raise PrepError(f"staging folder not found: {root}", 503)
    out: list[Candidate] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith(".") or entry.name == TRASH_DIR:
            continue
        if entry.is_file() and entry.suffix.lower() in VIDEO_EXT:
            out.append(Candidate(folder=entry.parent, video=entry))
            continue
        if not entry.is_dir():
            continue
        vids, subs, junk = [], [], []
        for f in sorted(entry.rglob("*")):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext in VIDEO_EXT:
                vids.append(f)
            elif ext in SUB_EXT or ext == ".sub":
                subs.append(f)
            elif ext in JUNK_EXT or f.name.lower() in JUNK_NAMES:
                junk.append(f)
        if not vids:
            continue
        # The biggest file is the film; the rest are samples and extras.
        vids.sort(key=lambda p: p.stat().st_size, reverse=True)
        out.append(Candidate(folder=entry, video=vids[0], subs=subs,
                             junk=junk, extra_videos=vids[1:]))
    return out


# ── naming ───────────────────────────────────────────────────────────────
# Everything a release name puts after the title. Cut at the first of these
# and what is left is the title — the year included, when it is there.
_RELEASE_NOISE = re.compile(
    r"\b(1080p|2160p|720p|480p|4k|uhd|bluray|blu-ray|bdrip|brrip|dvdrip|webrip|"
    r"web-dl|webdl|hdtv|hdrip|x264|x265|h264|h265|hevc|avc|xvid|divx|aac|ac3|"
    r"eac3|dts|truehd|atmos|flac|10bit|8bit|hdr|sdr|remux|proper|repack|extended|"
    r"unrated|directors?\.?cut|ita|eng|multi|sub|subs|dual|imax|pc)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"(?:^|[^\d])((?:19|20)\d{2})(?:[^\d]|$)")


def guess_title(name: str) -> tuple[str, str]:
    """Pull a title and year out of a release name.

    ``A.Star.Is.Born.2018.1080p.BluRay.x264.iTA.ENG.AC3-GRP``
        -> ("A Star Is Born", "2018")

    Only a guess: it feeds the metadata search, which is what actually decides
    the name. Getting it approximately right is enough to make the first
    search hit correct most of the time."""
    stem = Path(name).stem
    year = ""
    m = _YEAR.search(stem)
    if m:
        year = m.group(1)
        stem = stem[: m.start(1)]
    stem = _RELEASE_NOISE.split(stem)[0]
    # Scene names use dots and underscores as spaces; real titles use spaces.
    title = re.sub(r"[._]+", " ", stem)
    title = re.sub(r"\s*[-–]\s*$", "", title)
    title = re.sub(r"\s+", " ", title).strip(" -_")
    return title, year


def target_name(title: str, year: str) -> str:
    """The canonical folder and file name. Matches the library's convention
    and strips what a filesystem (or Plex) objects to."""
    name = f"{title} ({year})" if year else title
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()


# ── planning ─────────────────────────────────────────────────────────────
def analyse(candidate: Candidate) -> dict:
    """Probe a candidate and propose a plan, with every guess marked.

    Nothing here is destructive and nothing is final: the plan is what the UI
    edits and what `execute` later runs."""
    probe = _probe(candidate.video)
    title, year = guess_title(candidate.video.name if candidate.folder == candidate.video.parent
                              and candidate.video.parent.name in (candidate.video.parent.name,)
                              else candidate.folder.name)
    # A folder name is usually richer than the file inside it; fall back the
    # other way when the folder is just the staging root.
    if len(candidate.folder.name) > len(candidate.video.stem):
        title, year = guess_title(candidate.folder.name)

    tracks: list[dict] = []
    for s in probe.get("streams", []):
        kind = s.get("codec_type")
        disp = s.get("disposition") or {}
        tags = s.get("tags") or {}
        if kind == "video":
            tracks.append({
                "key": f"v:{s['index']}", "type": "video", "index": s["index"],
                "codec": s.get("codec_name", ""),
                "label": f"{s.get('codec_name','?')} {s.get('width')}x{s.get('height')}",
                # Cover art is a video stream too, and must never become the
                # film's video track.
                "keep": not disp.get("attached_pic"),
                "cover_art": bool(disp.get("attached_pic")),
                "attach_index": s["index"] if disp.get("attached_pic") else None,
                "language": "", "delay_ms": 0, "default": False,
            })
        elif kind in ("audio", "subtitle"):
            raw = (tags.get("language") or "").strip()
            guess = movies._LOOKUP.get(raw.lower(), "")
            code = _code_for(guess) if guess else ""
            # Same key scheme as movies.info() -- "audio:<n>" / "embedded:<n>"
            # by ordinal within the type -- so the player's track and this
            # plan's track are the same row in the UI rather than two lists
            # the user has to reconcile by eye.
            ordinal = len([t for t in tracks if t["type"] == kind])
            tracks.append({
                "key": (f"audio:{ordinal}" if kind == "audio" else f"embedded:{ordinal}"),
                "type": kind, "index": s["index"],
                "codec": s.get("codec_name", ""),
                "label": _track_label(s, kind),
                "keep": True,
                "language": code,
                # Flagged so the UI can ask rather than silently shipping
                # a track tagged "und".
                "language_guessed": bool(code) and raw.lower() not in ("und", ""),
                "delay_ms": 0,
                "default": bool(disp.get("default")),
            })
        # Attachments (fonts, cover art, kodi metadata) are not tracks anyone
        # wants to curate, and cover art is an attachment that ffprobe reports
        # as a video stream. Both are carried across wholesale by build_remux
        # rather than modelled here.

    # External subtitle files become tracks in exactly the same shape, so the
    # UI and the muxer never have to care where a subtitle came from.
    for path in candidate.subs:
        if path.suffix.lower() == ".sub":
            continue  # carried by its .idx
        lang, flags = movies.parse_sub_name(path.name, candidate.video.stem)
        tracks.append({
            "key": f"folder:{path.name}", "type": "subtitle", "external": str(path),
            "codec": "vobsub" if path.suffix.lower() == ".idx" else path.suffix.lstrip("."),
            "label": f"{path.name}",
            "keep": True,
            "language": _code_for(lang) if lang else "",
            "language_guessed": bool(lang),
            "flags": flags, "delay_ms": 0, "default": False,
        })

    return {
        "folder": str(candidate.folder),
        "video": str(candidate.video),
        "destination": "",   # filled in by scan_area, which knows the area
        "title": title, "year": year, "tmdb_id": None,
        "target": target_name(title, year),
        "duration": float(probe.get("format", {}).get("duration") or 0),
        "size": candidate.video.stat().st_size,
        "tracks": tracks,
        "junk": [str(p) for p in candidate.junk],
        "extra_videos": [str(p) for p in candidate.extra_videos],
        "conflicts": _conflicts(tracks),
    }


# The codes a muxer will accept. mkvmerge validates strictly and aborts on an
# unknown one ("Error: 'po8' is not a valid ISO 639-2 language code"), which
# is a poor way to find out — better to refuse before spending the mux.
VALID_CODES = {c for codes in movies.LANGUAGES.values() for c in codes if len(c) == 3} | {"und"}


def _conflicts(tracks: list[dict]) -> list[str]:
    """What a human has to decide before this can be muxed."""
    out = []
    bad = sorted({t["language"] for t in tracks
                  if t.get("keep") and t["type"] in ("audio", "subtitle")
                  and t.get("language") and t["language"] not in VALID_CODES})
    if bad:
        out.append(f"not valid ISO 639-2 language codes: {', '.join(bad)}")
    for kind in ("audio", "subtitle"):
        kept = [t for t in tracks if t["type"] == kind and t["keep"]]
        missing = [t for t in kept if not t["language"]]
        if missing:
            out.append(f"{len(missing)} {kind} track(s) have no language code")
        seen: dict[str, int] = {}
        for t in kept:
            if t["language"]:
                seen[t["language"]] = seen.get(t["language"], 0) + 1
        for code, n in seen.items():
            if n > 1:
                out.append(f"{n} {kind} tracks share the language '{code}'")
    if not [t for t in tracks if t["type"] == "video" and t["keep"]]:
        out.append("no video track selected")
    return out


def language_options() -> list[dict]:
    """The languages a track may be tagged with, for the picker.

    Codes are the bibliographic ISO 639-2 spelling — the one Matroska keeps —
    so what is chosen is what ends up in the file. See `_code_for`."""
    out = [{"code": _code_for(name), "name": name} for name in movies.LANGUAGES]
    out = [x for x in out if x["code"]]
    out.sort(key=lambda x: x["name"])
    return out


def _code_for(display: str) -> str:
    """The 3-letter code to write into the file.

    Deliberately the FIRST 3-letter spelling, not the last. Seven languages
    have two ISO 639-2 codes — bibliographic and terminological — and Matroska
    stores the bibliographic one: ask mkvmerge for `deu` and it writes `ger`,
    for `fra` it writes `fre`, and likewise nld/dut, ell/gre, ces/cze,
    ron/rum, fas/per. It does *not* rewrite the track name, so asking for the
    terminological code yields a track reading `language=ger, name=deu` —
    precisely the inconsistency this pipeline exists to remove.

    preparePlex's `get_extended()` takes the last entry and so hits this; in
    LANGUAGES the lists are ordered with the bibliographic code first, so the
    first 3-letter entry is the one the container will keep."""
    codes = [c for c in movies.LANGUAGES.get(display, []) if len(c) == 3]
    return codes[0] if codes else ""


def _same_language(a: str, b: str) -> bool:
    """Are these two codes the same language? Covers the bibliographic /
    terminological pairs (ger/deu, fre/fra, ...) that a muxer may swap."""
    for codes in movies.LANGUAGES.values():
        low = [c.lower() for c in codes]
        if a in low and b in low:
            return True
    return a == b


def _track_label(s: dict, kind: str) -> str:
    tags = s.get("tags") or {}
    bits = [s.get("codec_name", "?")]
    if kind == "audio" and s.get("channels"):
        bits.append(f"{s['channels']}ch")
    raw = (tags.get("language") or "").strip()
    if raw:
        bits.append(raw)
    if tags.get("title"):
        bits.append(tags["title"])
    return " · ".join(bits)


def have_mkvmerge() -> bool:
    return shutil.which("mkvmerge") is not None


def _probe(path: Path) -> dict:
    res = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", str(path)],
        capture_output=True, timeout=120,
    )
    if res.returncode != 0:
        raise PrepError(f"could not probe {path.name}", 502)
    return json.loads(res.stdout.decode("utf-8", "replace"))


# ── muxing ───────────────────────────────────────────────────────────────
def build_remux(plan: dict, output: Path) -> list[str]:
    """One ffmpeg command producing the finished file.

    Everything is stream-copied — this re-containers, it never re-encodes.

    Per-track delay is the awkward part. ffmpeg's `-itsoffset` shifts a whole
    *input*, not a stream, so a track that needs shifting has to arrive from
    its own input: the source file is listed again with that offset and only
    that track is mapped from it. Inputs are shared between tracks wanting the
    same offset, so the common case (one delay, or none) adds nothing.

    Every kept track is tagged with its language code and *named* with the
    same code, which is the whole point of the exercise: a finished file
    should say `ita`, not `Italian [Forced] (DTS 5.1)`."""
    inputs: list[tuple[str, int]] = [(plan["video"], 0)]

    def input_for(path: str, delay_ms: int) -> int:
        for i, (p, d) in enumerate(inputs):
            if p == path and d == delay_ms:
                return i
        inputs.append((path, delay_ms))
        return len(inputs) - 1

    kept = [t for t in plan["tracks"] if t.get("keep")]
    order = {"video": 0, "audio": 1, "subtitle": 2, "attachment": 3}
    kept.sort(key=lambda t: (order.get(t["type"], 9), t.get("index", 1 << 30)))

    maps: list[str] = []
    meta: list[str] = []
    counts = {"v": 0, "a": 0, "s": 0, "t": 0}
    for t in kept:
        short = {"video": "v", "audio": "a", "subtitle": "s", "attachment": "t"}[t["type"]]
        n = counts[short]
        counts[short] += 1
        if t.get("external"):
            idx = input_for(t["external"], t.get("delay_ms", 0))
            maps += ["-map", f"{idx}:0"]
        else:
            idx = input_for(plan["video"], t.get("delay_ms", 0))
            maps += ["-map", f"{idx}:{t['index']}"]
        if t["type"] == "video":
            # The source's video track is named after the release
            # ("Angels.Egg.1985.PC.1080p.BluRay.x265-SARTRE"). Blank it.
            meta += [f"-metadata:s:v:{n}", "title="]
        if t["type"] in ("audio", "subtitle"):
            code = t.get("language") or "und"
            meta += [f"-metadata:s:{short}:{n}", f"language={code}",
                     f"-metadata:s:{short}:{n}", f"title={code}"]
            meta += [f"-disposition:{short}:{n}",
                     "default" if code == "eng" else "0"]

    # +genpts: a track carrying packets with no timestamps (common in an MKV
    # remuxed from AVI) otherwise aborts the mux with "Can't write packet with
    # unknown timestamp". Verified to fix it on Army of Darkness.
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-fflags", "+genpts"]
    for path, delay_ms in inputs:
        if delay_ms:
            cmd += ["-itsoffset", f"{delay_ms / 1000:.3f}"]
        cmd += ["-i", path]
    # Fonts, cover art and the like. `?` so a file without any still muxes.
    # Cover art is an attached_pic *video* stream to ffprobe, so it needs its
    # own map on top of the attachment streams.
    maps += ["-map", "0:t?"]
    for t in plan["tracks"]:
        if t.get("attach_index") is not None:
            maps += ["-map", f"0:{t['attach_index']}"]

    cmd += maps
    cmd += ["-c", "copy"]
    cmd += meta
    # Drop the release's own metadata, keep the chapters, set our own title.
    cmd += ["-map_metadata", "-1", "-map_chapters", "0",
            "-metadata", f"title={plan['target']}"]
    cmd += [str(output)]
    return cmd


def verify(output: Path, plan: dict) -> list[str]:
    """Compare what came out against what was asked for.

    preparePlex deletes the source the moment mkvmerge returns 0, which is a
    thin guarantee — a mux can succeed and still have quietly dropped a track
    ffmpeg couldn't copy. Nothing here is thrown away until these checks pass."""
    problems: list[str] = []
    if not output.exists() or output.stat().st_size == 0:
        return ["the muxed file is missing or empty"]

    # Verify with mkvmerge when it is there. ffprobe reads MKV track metadata
    # incompletely: given a track mkvmerge wrote as language='alb', ffprobe
    # returns language=None -- it does not recognise every ISO 639-2
    # bibliographic code. Checking mkvmerge's output with ffprobe therefore
    # invents failures on correct files, which is worse than not checking.
    if have_mkvmerge():
        return _verify_mkv(output, plan)
    try:
        probe = _probe(output)
    except PrepError:
        return ["the muxed file could not be probed"]

    got = {"video": [], "audio": [], "subtitle": [], "attachment": []}
    for s in probe.get("streams", []):
        # Cover art is an MKV *attachment*, which ffprobe surfaces as a video
        # stream flagged attached_pic. mkvmerge rightly preserves it (Plex
        # uses it as the poster), so counting it as a video track would fail
        # every file that has one.
        if (s.get("disposition") or {}).get("attached_pic"):
            got["attachment"].append(s)
            continue
        got.setdefault(s.get("codec_type"), []).append(s)
    want = {k: [t for t in plan["tracks"] if t.get("keep") and t["type"] == k]
            for k in got}

    for kind in ("video", "audio", "subtitle"):
        if len(got[kind]) != len(want[kind]):
            problems.append(
                f"expected {len(want[kind])} {kind} track(s), got {len(got[kind])}")

    for kind, short in (("audio", "a"), ("subtitle", "s")):
        for i, (t, s) in enumerate(zip(want[kind], got[kind])):
            tag = ((s.get("tags") or {}).get("language") or "").lower()
            expected = (t.get("language") or "und").lower()
            # A container is allowed to store the other ISO 639-2 variant of
            # the same language; that is a spelling, not a mismatch.
            if tag != expected and not _same_language(tag, expected):
                problems.append(
                    f"{kind} track {i} is tagged '{tag}', expected '{expected}'")

    src = float(plan.get("duration") or 0)
    out = float(probe.get("format", {}).get("duration") or 0)
    # A delayed track legitimately lengthens the file; a truncated mux does
    # not shorten it by a little.
    if src and out and out < src - 2:
        problems.append(f"output is {src - out:.0f}s shorter than the source")
    return problems


def _verify_mkv(output: Path, plan: dict) -> list[str]:
    """The same checks as `verify`, asked of the tool that wrote the file."""
    problems: list[str] = []
    res = subprocess.run(["mkvmerge", "-J", str(output)], capture_output=True, timeout=180)
    if res.returncode >= 2:
        return ["the muxed file could not be read back"]
    data = json.loads(res.stdout.decode("utf-8", "replace"))
    got: dict[str, list[dict]] = {"video": [], "audio": [], "subtitles": []}
    for t in data.get("tracks", []):
        got.setdefault(t["type"], []).append(t)

    pairs = (("video", "video"), ("audio", "audio"), ("subtitle", "subtitles"))
    for plan_kind, mkv_kind in pairs:
        want = [t for t in plan["tracks"] if t.get("keep") and t["type"] == plan_kind]
        have = got.get(mkv_kind, [])
        if len(have) != len(want):
            problems.append(
                f"expected {len(want)} {plan_kind} track(s), got {len(have)}")
            continue
        if plan_kind == "video":
            continue
        for i, (t, g) in enumerate(zip(want, have)):
            props = g.get("properties") or {}
            lang = (props.get("language") or "").lower()
            expected = (t.get("language") or "und").lower()
            if lang != expected and not _same_language(lang, expected):
                problems.append(
                    f"{plan_kind} track {i} is tagged {lang!r}, expected {expected!r}")
            name = props.get("track_name") or ""
            if name and name.lower() != lang and not _same_language(name.lower(), lang):
                problems.append(
                    f"{plan_kind} track {i} is named {name!r} but tagged {lang!r}")

    dur = (data.get("container", {}).get("properties", {}) or {}).get("duration")
    src = float(plan.get("duration") or 0)
    if dur and src:
        out_s = dur / 1e9
        if out_s < src - 2:
            problems.append(f"output is {src - out_s:.0f}s shorter than the source")
    return problems


# Progress of in-flight muxes, keyed "<area>:<target>". mkvmerge prints
# "Progress: 42%" as it works; ffmpeg's copy path does not report usefully, so
# its percent stays None and the UI shows an indeterminate bar rather than a
# number it would have to invent.
_progress: dict[str, dict] = {}
_progress_lock = threading.Lock()


def progress(key: str) -> dict:
    with _progress_lock:
        return dict(_progress.get(key) or {"percent": None, "running": False})


def _set_progress(key: str, **fields) -> None:
    if not key:
        return
    with _progress_lock:
        _progress.setdefault(key, {"percent": None, "running": False}).update(fields)


_PROGRESS_RE = re.compile(rb"Progress:\s*(\d+)%")


def _run_muxer(cmd: list[str], key: str, mkvmerge: bool) -> subprocess.CompletedProcess:
    """Run the mux, publishing progress as it goes.

    mkvmerge writes its percentage to stdout with carriage returns rather
    than newlines, so this reads raw chunks instead of lines — readline()
    would block until the whole run finished and report 0% throughout."""
    _set_progress(key, percent=0, running=True, error="")
    # bufsize=0: an unbuffered pipe, so progress arrives as mkvmerge writes
    # it rather than in one block at the end.
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    tail = b""
    try:
        while True:
            # With bufsize=0 this is a raw FileIO, so read() is one syscall
            # returning whatever is available. On a *buffered* pipe the same
            # call would block until all 4096 bytes arrived, holding back the
            # short "Progress: 12%" writes until the mux was already done.
            chunk = proc.stdout.read(4096) if proc.stdout else b""
            if not chunk:
                break
            tail = (tail + chunk)[-4096:]
            if mkvmerge:
                found = _PROGRESS_RE.findall(chunk)
                if found:
                    _set_progress(key, percent=int(found[-1]))
    finally:
        err = proc.stderr.read() if proc.stderr else b""
        proc.wait()
        _set_progress(key, running=False)
    return subprocess.CompletedProcess(cmd, proc.returncode, tail, err)


def execute(plan: dict, dest_root: Path, dry_run: bool = False) -> dict:
    """Mux, verify, then tidy up — in that order, and only in that order."""
    folder = Path(plan["folder"])
    target = plan["target"]
    if not target:
        raise PrepError("the film has no target name yet")
    conflicts = _conflicts(plan["tracks"])
    if conflicts:
        raise PrepError("; ".join(conflicts))

    out_dir = dest_root / target
    output = out_dir / f"{target}.mkv"
    # Never replace a film that is already there. The destination defaults to
    # the real library when an area omits `library`, so a silent overwrite
    # here would destroy an original with no undo — and "a film with this
    # name already exists" is nearly always a duplicate download, not an
    # intended replacement. Refusing costs one manual step; guessing wrong
    # costs the file.
    if output.exists():
        raise PrepError(
            f"{output.name} already exists in {dest_root} "
            f"({output.stat().st_size / 1e9:.2f} GB) — remove or rename it first",
            409,
        )
    temp_path = folder / f".{target}.muxing.mkv"
    use_mkvmerge = have_mkvmerge()
    cmd = (build_remux_mkvmerge if use_mkvmerge else build_remux)(plan, temp_path)
    if dry_run:
        return {"command": cmd, "output": str(output), "conflicts": conflicts}

    out_dir.mkdir(parents=True, exist_ok=True)
    temp = temp_path
    started = time.time()
    key = f"{plan.get('area', '')}:{target}"
    res = _run_muxer(cmd, key, use_mkvmerge)
    # mkvmerge returns 1 for warnings with a perfectly good file; only >=2 is
    # a real failure. ffmpeg has no such distinction.
    if (res.returncode >= 2) if use_mkvmerge else (res.returncode != 0):
        _unlink(temp)
        tail = (res.stderr or res.stdout).decode("utf-8", "replace").strip().splitlines()[-4:]
        raise PrepError("mux failed: " + " | ".join(tail), 502)

    problems = verify(temp, plan)
    if problems:
        _unlink(temp)
        raise PrepError("mux produced the wrong file: " + "; ".join(problems), 502)

    shutil.move(str(temp), str(output))

    # Only now is anything removed, and even then it is moved, not deleted:
    # the one irreversible step in this pipeline deserves an undo.
    trash = folder.parent / TRASH_DIR / time.strftime("%Y-%m-%d_%H-%M-%S") / folder.name
    trash.mkdir(parents=True, exist_ok=True)
    moved = []
    for leftover in sorted(folder.rglob("*")):
        if leftover.is_file():
            rel = leftover.relative_to(folder)
            (trash / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(leftover), str(trash / rel))
            moved.append(str(rel))
    shutil.rmtree(folder, ignore_errors=True)

    _set_progress(key, percent=100, running=False)
    return {
        "muxer": "mkvmerge" if use_mkvmerge else "ffmpeg",
        "output": str(output),
        "size": output.stat().st_size,
        "seconds": round(time.time() - started, 1),
        "trashed": moved,
        "trash": str(trash),
    }


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


# ── muxing with mkvmerge ─────────────────────────────────────────────────
def _mkv_ids(path: Path) -> dict[str, list[int]]:
    """mkvmerge's own track ids, grouped by type.

    Needed because mkvmerge and ffprobe do not number a file the same way:
    ffprobe reports cover art as a video stream and an attachment as a
    stream, mkvmerge counts neither as a track. Mapping by index between the
    two silently picks the wrong track on any file with either, so the plan
    is matched by (type, ordinal) — which both agree on."""
    res = subprocess.run(["mkvmerge", "-J", str(path)], capture_output=True, timeout=180)
    if res.returncode >= 2:
        raise PrepError(f"mkvmerge could not read {path.name}", 502)
    data = json.loads(res.stdout.decode("utf-8", "replace"))
    out: dict[str, list[int]] = {"video": [], "audio": [], "subtitles": []}
    for t in data.get("tracks", []):
        out.setdefault(t["type"], []).append(t["id"])
    return out


_MKV_KIND = {"video": "video", "audio": "audio", "subtitle": "subtitles"}
_MKV_OPTS = {"video": ("--video-tracks", "--no-video"),
             "audio": ("--audio-tracks", "--no-audio"),
             "subtitles": ("--subtitle-tracks", "--no-subtitles")}


def build_remux_mkvmerge(plan: dict, output: Path) -> list[str]:
    """The finished file, muxed by the tool that is actually built for MKV.

    `--sync` is a genuine per-track offset, so a film with three differently
    delayed tracks is still read once — ffmpeg's `-itsoffset` shifts a whole
    input and forces the source to be listed again per distinct delay. And
    chapters, attachments and cover art survive without being enumerated,
    because mkvmerge understands them as MKV structures rather than streams."""
    src = Path(plan["video"])
    ids = _mkv_ids(src)
    kept = [t for t in plan["tracks"] if t.get("keep")]

    cmd = ["mkvmerge", "-o", str(output), "--title", plan["target"]]
    select: dict[str, list[int]] = {"video": [], "audio": [], "subtitles": []}
    flags: list[str] = []

    for kind in ("video", "audio", "subtitle"):
        pool = ids.get(_MKV_KIND[kind], [])
        # Ordinal among the file's own tracks of this kind, cover art excluded
        # because mkvmerge does not count it as one.
        all_of_kind = [x for x in plan["tracks"]
                       if x["type"] == kind and not x.get("external")
                       and not x.get("cover_art")]
        for t in [x for x in kept if x["type"] == kind and not x.get("external")]:
            try:
                tid = pool[all_of_kind.index(t)]
            except (ValueError, IndexError):
                continue
            select[_MKV_KIND[kind]].append(tid)
            if kind == "video":
                # Without this the video track keeps the release name
                # ("Angels.Egg.1985.PC.1080p.BluRay.x265.HEVC.FLAC-SARTRE"),
                # which is exactly the noise this pipeline exists to strip.
                flags += ["--track-name", f"{tid}:"]
            else:
                code = t.get("language") or "und"
                flags += [
                    "--language", f"{tid}:{code}",
                    "--track-name", f"{tid}:{code}",
                    # English is the default track, as it is throughout this
                    # library -- not something worth asking about per film.
                    "--default-track", f"{tid}:{'yes' if code == 'eng' else 'no'}",
                    "--forced-track", f"{tid}:no",
                    "--compression", f"{tid}:none",
                    "--sync", f"{tid}:{int(t.get('delay_ms', 0))}",
                ]

    for mkv_kind, chosen in select.items():
        pick, drop = _MKV_OPTS[mkv_kind]
        cmd += ([pick, ",".join(str(x) for x in chosen)] if chosen else [drop])
    cmd += flags
    cmd += [str(src)]

    # Each external subtitle is its own input; inside it the track is always 0.
    for t in kept:
        if not t.get("external"):
            continue
        code = t.get("language") or "und"
        cmd += [
            "--language", f"0:{code}",
            "--track-name", f"0:{code}",
            "--default-track", f"0:{'yes' if code == 'eng' else 'no'}",
            "--forced-track", "0:no",
            "--compression", "0:none",
            "--sync", f"0:{int(t.get('delay_ms', 0))}",
            t["external"],
        ]
    return cmd


# ── watching the staging folders ─────────────────────────────────────────
# A film appearing in an inbox should show up without anyone pressing
# refresh. Rather than have the browser re-scan on a timer -- which would
# mean an ffprobe per film every few seconds -- a thread takes a cheap
# fingerprint of the folders and bumps a counter when it changes. The SPA
# already polls /api/version once a second, so the counter is all it needs;
# the expensive scan then happens once, on demand, and is cached against the
# same fingerprint.
WATCH_SECONDS = 5

_version = 0
_signatures: dict[str, str] = {}
_scan_cache: dict[str, tuple[str, list[dict]]] = {}
_watch_lock = threading.Lock()


def version() -> int:
    with _watch_lock:
        return _version


def _signature(root: Path) -> str:
    """Names, sizes and mtimes — no ffprobe. Enough to notice a file added,
    removed, renamed or still being copied in."""
    h = hashlib.sha1()
    try:
        for path in sorted(root.rglob("*")):
            if path.name.startswith(".") or TRASH_DIR in path.parts:
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            h.update(f"{path}|{st.st_size}|{st.st_mtime_ns}".encode())
    except OSError:
        return "unreadable"
    return h.hexdigest()


def _watch() -> None:
    global _version
    while True:
        changed = False
        for name, cfg in areas().items():
            if not cfg["ready"]:
                continue
            sig = _signature(Path(cfg["inbox"]))
            with _watch_lock:
                if _signatures.get(name) != sig:
                    _signatures[name] = sig
                    changed = True
        if changed:
            with _watch_lock:
                _version += 1
        time.sleep(WATCH_SECONDS)


def init() -> None:
    threading.Thread(target=_watch, daemon=True).start()


def scan_area(name: str) -> list[dict]:
    """Every film waiting in one staging area, with its proposed plan.

    Cached against the folder fingerprint, so this stays cheap while nothing
    changes and re-probes the moment something does."""
    inbox, library = area(name)
    sig = _signature(inbox)
    with _watch_lock:
        hit = _scan_cache.get(name)
        if hit and hit[0] == sig:
            return hit[1]

    out = []
    for candidate in scan(inbox):
        try:
            plan = analyse(candidate)
        except Exception as e:
            out.append({"folder": str(candidate.folder), "error": str(e)[:200],
                        "target": candidate.folder.name, "tracks": []})
            continue
        plan["area"] = name
        plan["destination"] = str(library)
        # So the player can stream it straight from the staging folder --
        # checking a subtitle's timing before committing the remux is the
        # entire reason this is in the same app as the player.
        plan["movie_id"] = movies._encode_id(Path(plan["video"]), name)
        out.append(plan)
    with _watch_lock:
        _scan_cache[name] = (sig, out)
    return out


# ── browsing a staging folder ────────────────────────────────────────────
# A staging folder is not just films: it holds the subtitles, the release
# notes, the poster the uploader threw in, and the junk. Deciding what to
# keep means being able to look at all of it, so the browser lists
# everything and classifies it by what can usefully be *shown*.
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
TEXT_EXT = {".srt", ".ass", ".ssa", ".vtt", ".idx", ".txt", ".nfo", ".md",
            ".json", ".xml", ".log", ".cfg", ".ini", ".sfv", ".url"}
TEXT_MAX_BYTES = 256 * 1024


def file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    if ext in SUB_EXT or ext == ".sub":
        # .sub is the binary half of a VobSub pair; its .idx is the readable
        # one, so only that gets offered as text.
        return "subtitle" if ext != ".sub" else "binary"
    if ext in TEXT_EXT:
        return "text"
    return "binary"


def browse(area_name: str) -> list[dict]:
    """Every file in a staging area, classified, newest folder first."""
    inbox, _ = area(area_name)
    out: list[dict] = []
    for path in sorted(inbox.rglob("*")):
        if TRASH_DIR in path.parts or path.name.startswith("."):
            continue
        if not path.is_file():
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        kind = file_kind(path)
        rel = path.relative_to(inbox)
        entry = {
            "path": str(rel),
            "folder": str(rel.parent) if str(rel.parent) != "." else "",
            "name": path.name,
            "size": st.st_size,
            "modified": int(st.st_mtime),
            "kind": kind,
            "readable": kind in ("text", "subtitle") and st.st_size <= TEXT_MAX_BYTES,
        }
        if kind == "video":
            try:
                entry["movie_id"] = movies._encode_id(path, area_name)
            except (ValueError, KeyError):
                # A file the player cannot address is still worth listing —
                # losing the whole folder listing because one id could not be
                # built is a bad trade.
                entry["kind"] = "binary"
                entry["playable_error"] = "not reachable from a configured root"
        out.append(entry)
    return out


def resolve_in_area(area_name: str, rel: str) -> Path:
    """A path inside a staging area, refusing anything that escapes it."""
    inbox, _ = area(area_name)
    root = inbox.resolve()
    try:
        path = (root / rel).resolve()
    except OSError as e:
        raise PrepError(f"bad path: {e}")
    if root != path and root not in path.parents:
        raise PrepError("path outside the staging area", 403)
    if not path.is_file():
        raise PrepError("no such file", 404)
    return path


def read_text(area_name: str, rel: str) -> dict:
    """A text file's contents for the viewer, with the same encoding
    tolerance uploads get — subtitles in the wild are rarely UTF-8."""
    path = resolve_in_area(area_name, rel)
    size = path.stat().st_size
    if size > TEXT_MAX_BYTES:
        raise PrepError(f"{path.name} is too large to display "
                        f"({size // 1024} KB)", 413)
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        enc, text = "utf-8 (replaced)", raw.decode("utf-8", "replace")
    return {"path": rel, "name": path.name, "size": size,
            "encoding": enc, "text": text}


def describe(area_name: str, rel: str) -> dict:
    """What can be said about a file that cannot be shown."""
    path = resolve_in_area(area_name, rel)
    st = path.stat()
    info: dict = {
        "path": rel, "name": path.name, "size": st.st_size,
        "modified": int(st.st_mtime), "kind": file_kind(path),
        "suffix": path.suffix.lower(),
    }
    # A media file can still say a lot about itself even when it is not the
    # film — a stray sample, an .idx, an audio-only extra.
    if file_kind(path) in ("video", "binary") and path.suffix.lower() in VIDEO_EXT | {".sub", ".sup"}:
        try:
            probe = _probe(path)
            info["duration"] = float(probe.get("format", {}).get("duration") or 0)
            info["streams"] = [
                {"type": s.get("codec_type"), "codec": s.get("codec_name"),
                 "language": (s.get("tags") or {}).get("language", ""),
                 "size": f"{s.get('width')}x{s.get('height')}" if s.get("width") else ""}
                for s in probe.get("streams", [])
            ]
        except Exception:
            pass
    return info


# ── moving between configured folders ────────────────────────────────────
def move_film(movie_id: str, to_key: str) -> dict:
    """Move a film's folder from wherever it is to another configured folder.

    Destinations are the same roots the panel browses — the library itself,
    any staging inbox, any staging output — so this is the one action that
    shuffles work between stages: a finished film into the library, or one
    that needs redoing back into an inbox.

    The *folder* moves, not the file, because a film here is a folder: the
    mkv plus whatever sidecars have not been embedded yet. A film sitting
    loose in a root has no folder to move, so the file goes on its own.

    It is a move, not a copy. An existing name at the destination is refused
    rather than merged or overwritten — that is nearly always the same film
    arriving twice, and guessing wrong costs the original."""
    src_file = movies.resolve(movie_id)
    roots = movies.roots()
    if to_key not in roots:
        known = ", ".join(repr(k or "library") for k in roots)
        raise PrepError(f"unknown destination {to_key!r} (have: {known})", 404)

    # An inbox holds dirty downloads waiting to be prepared; putting a
    # finished film back into one would queue it for work it has already had.
    # Destinations are outputs and the library only.
    if to_key and not to_key.endswith(":library"):
        raise PrepError(
            f"{to_key!r} is a staging inbox — films move out of those, not into them",
            400)

    dest_root = roots[to_key].expanduser()
    if not dest_root.is_dir():
        raise PrepError(f"destination folder not found: {dest_root}", 503)

    # Which root is it in now? The longest matching one, so ".../inbox" wins
    # over a parent that also happens to be configured.
    source_root = None
    for root in roots.values():
        r = root.expanduser().resolve()
        if r == src_file.parent or r in src_file.parents:
            if source_root is None or len(str(r)) > len(str(source_root)):
                source_root = r
    if source_root is None:
        raise PrepError("that film is not inside a configured folder", 403)

    # The folder directly under the root is the unit that moves.
    rel = src_file.relative_to(source_root)
    moving = source_root / rel.parts[0]
    if moving.resolve() == dest_root.resolve():
        raise PrepError("that film is already there", 409)
    if source_root.resolve() == dest_root.resolve():
        raise PrepError("source and destination are the same folder", 409)

    dest = dest_root / moving.name
    if dest.exists():
        raise PrepError(
            f"{moving.name!r} already exists in {dest_root} — "
            f"remove or rename it first", 409)

    # shutil.move falls back to copy+delete across filesystems, which is what
    # makes this work when the library is on another disk.
    shutil.move(str(moving), str(dest))
    return {
        "moved": moving.name,
        "to": str(dest),
        "was_folder": moving.is_dir() if moving.exists() else True,
        "size": sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
                if dest.is_dir() else dest.stat().st_size,
    }
