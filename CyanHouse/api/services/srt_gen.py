"""Subtitles generated from a film's own audio, as the first stage of a remux.

The transcription itself is done by the speech-to-text service of CyanManager
on the fn host (CONTROLS_FN_URL — its `/transcribe_movie` endpoints), the same
one videoProcessing/generateSrt drives from the desktop: send it one audio
track, poll the job, get an SRT back. Whisper on a GPU still takes a good
fraction of the film's running time, which is why this runs inside the remux
queue rather than behind a button of its own.

An audio track marked `gen_srt` in the plan gets one subtitle track, in the
audio's language and with the audio's delay — the timings Whisper produces
are the audio stream's own, so they shift with it.

What was generated is kept (MOVIES_DATA_DIR/generated_srt/<fingerprint>/)
until the remux succeeds: an hour of transcription is not thrown away because
the mux after it failed, or because this process restarted half way. The
server's job id is kept on the queue job too, so a restart resumes polling
the transcription already running instead of starting a second one.
"""
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

from api.auth import basic_header
from api.config import CONTROLS_FN_URL, FFMPEG, MOVIES_DATA_DIR
from api.services import movies
from api.services.movie_prep import PrepError

POLL_SECONDS = 3
# How long the service may be unreachable before the remux gives up on it.
# A blip (a Wi-Fi hiccup, the PC busy) is ridden out; a service that has
# stopped is not waited for.
UNREACHABLE_SECONDS = 90
# Mono 16 kHz Opus at 32k: what Whisper resamples everything to anyway, and
# small enough to upload quickly (~30 MB for two hours).
AUDIO_ARGS = ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "32k"]

_OUT_TIME = re.compile(rb"out_time_(?:ms|us)=(\d+)")


class Stopped(Exception):
    """The job was stopped while generating."""


def wanted(plan: dict) -> list[dict]:
    """The audio tracks a subtitle is to be generated from."""
    return [t for t in plan.get("tracks", [])
            if t.get("type") == "audio" and t.get("keep") and t.get("gen_srt")
            and t.get("language")]


def _whisper_language(code: str) -> str | None:
    """Whisper takes two-letter codes; the plan keeps ISO 639-2 ones."""
    for codes in movies.LANGUAGES.values():
        if code.lower() in (c.lower() for c in codes):
            two = [c for c in codes if len(c) == 2]
            return two[0] if two else None
    return None


def _dir(fingerprint: str) -> Path:
    return MOVIES_DATA_DIR.resolve() / "generated_srt" / re.sub(r"[^\w.-]", "_", fingerprint)


def _cached(fingerprint: str, track: dict) -> Path:
    key = re.sub(r"[^\w.-]", "_", track["key"])
    return _dir(fingerprint) / f"{key}.{track['language']}.srt"


def forget(fingerprint: str) -> None:
    """Drop what was generated for a film — once it is muxed in, it is in the file."""
    shutil.rmtree(_dir(fingerprint), ignore_errors=True)


def _url(path: str) -> str:
    if not CONTROLS_FN_URL:
        raise PrepError("no speech-to-text service configured (CONTROLS_FN_HOST in secrets.json)")
    return CONTROLS_FN_URL + path


def _extract(video: Path, track: dict, out: Path, duration: float, report, cancelled) -> None:
    """One audio track, as the service wants it, with its progress reported."""
    cmd = [FFMPEG, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
           "-i", str(video), "-map", f"0:{track['index']}", *AUDIO_ARGS,
           "-progress", "pipe:1", "-nostats", str(out)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    report(pid=proc.pid)
    last = -1
    try:
        while True:
            chunk = proc.stdout.read(4096) if proc.stdout else b""
            if not chunk:
                break
            found = _OUT_TIME.findall(chunk)
            if found and duration:
                pct = min(99, int(int(found[-1]) / 1e6 / duration * 100))
                if pct != last:
                    last = pct
                    report(percent=pct)
    finally:
        err = proc.stderr.read() if proc.stderr else b""
        proc.wait()
        report(pid=None)
    if cancelled():
        raise Stopped()
    if proc.returncode != 0:
        tail = err.decode("utf-8", "replace").strip().splitlines()[-2:]
        raise PrepError("extracting the audio failed: " + " | ".join(tail), 502)


def _status(job_id: str, cancelled, user: str) -> dict:
    """The service's view of a transcription, riding out short outages."""
    down_since = None
    while True:
        try:
            r = requests.get(_url(f"/transcribe_movie/status/{job_id}"), headers=basic_header(user),
                             timeout=15)
            # 404 is the service's own answer for a job it does not know —
            # it was restarted, and the transcription went with it.
            if r.status_code == 404:
                return {"status": "unknown"}
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            now = time.time()
            down_since = down_since or now
            if now - down_since > UNREACHABLE_SECONDS:
                raise PrepError(f"the speech-to-text service stopped answering ({e.__class__.__name__})", 502)
            if cancelled():
                raise Stopped()
            time.sleep(POLL_SECONDS)


def generate(plan: dict, track: dict, *, stt_jobs: dict, report, cancelled, user: str) -> Path:
    """The subtitle for one audio track: from the cache, from a transcription
    already running on the service, or generated from scratch.

    `stt_jobs` maps track keys to the service's job ids and is saved with the
    queue job (report(stt_jobs=...)), which is what lets a restart resume.
    Raises PrepError when the service reports a failure or loses the job —
    the remux must not go ahead without the subtitle it was asked for.
    `user` (who queued the remux) is who the service is asked as: it signs
    people in with the CyanHouse users."""
    fp = plan["fingerprint"]
    done = _cached(fp, track)
    if done.is_file():
        return done
    done.parent.mkdir(parents=True, exist_ok=True)
    lang = track["language"]

    job_id = stt_jobs.get(track["key"])
    if job_id:
        st = _status(job_id, cancelled, user)
        if st.get("status") not in ("running", "done"):
            job_id = None   # lost with a service restart, or failed: start over

    if not job_id:
        if cancelled():
            raise Stopped()
        audio = done.with_suffix(".opus")
        try:
            report(detail="extracting audio", percent=0)
            _extract(Path(plan["video"]), track, audio, float(plan.get("duration") or 0),
                     report, cancelled)
            report(detail="uploading", percent=None)
            params = {"ext": ".opus"}
            whisper = _whisper_language(lang)
            if whisper:
                params["language"] = whisper
            try:
                r = requests.post(_url("/transcribe_movie/start"), params=params,
                                  data=audio.read_bytes(), headers=basic_header(user), timeout=600)
                r.raise_for_status()
                job_id = r.json()["job_id"]
            except (requests.RequestException, KeyError, ValueError) as e:
                raise PrepError(f"could not reach the speech-to-text service: {e}", 502)
        finally:
            audio.unlink(missing_ok=True)
        stt_jobs[track["key"]] = job_id
        report(stt_jobs=dict(stt_jobs))

    report(detail="transcribing", percent=0)
    last = -1.0
    while True:
        if cancelled():
            raise Stopped()
        st = _status(job_id, cancelled, user)
        state = st.get("status")
        if state == "running":
            pct = float(st.get("percent") or 0)
            if pct != last:
                last = pct
                report(percent=int(pct))
        elif state == "done":
            srt = st.get("srt") or ""
            if not srt.strip():
                raise PrepError(f"the {lang} subtitle came back empty", 502)
            tmp = done.with_suffix(".tmp")
            tmp.write_text(srt, encoding="utf-8")
            tmp.replace(done)
            return done
        elif state == "unknown":
            raise PrepError(f"the speech-to-text service lost the {lang} transcription "
                            f"(was it restarted?)", 502)
        else:
            raise PrepError(f"generating the {lang} subtitle failed: "
                            f"{st.get('error') or state}", 502)
        time.sleep(POLL_SECONDS)


def attach(plan: dict, generated: dict[str, Path]) -> tuple[dict, list[Path]]:
    """The plan with each generated subtitle added as a track.

    Each file is copied into the film's own folder first — a hidden file, so
    no scan mistakes it for a download — because every track a remux reads
    must come from there (movie_prep._checked_paths), and because clearing
    the folder afterwards then takes the copy with it. Returns the new plan
    and the copies, for the caller to remove if the remux does not happen."""
    video = Path(plan["video"])
    folder = video.parent
    tracks = list(plan["tracks"])
    copies: list[Path] = []
    for audio in wanted(plan):
        src = generated.get(audio["key"])
        if not src:
            continue
        copy = folder / f".{video.stem}.gen-{audio['language']}.srt"
        shutil.copyfile(src, copy)
        copies.append(copy)
        tracks.append({
            "key": f"gen:{audio['key']}", "type": "subtitle", "external": str(copy),
            "codec": "subrip", "label": f"generated from {audio['label']}",
            "keep": True, "language": audio["language"], "language_guessed": False,
            "delay_ms": int(audio.get("delay_ms") or 0), "default": False,
            "generated_from": audio["key"],
        })
    return {**plan, "tracks": tracks}, copies
