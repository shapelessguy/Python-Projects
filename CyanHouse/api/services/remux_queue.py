"""The remux queue: every remux the server has been asked for, done in order.

A remux takes minutes and belongs to the server, not to whichever browser
asked for it — so asking only puts a film in this queue, and a single worker
takes them one at a time. One at a time is deliberate: two mkvmerge runs
writing gigabytes to the same disk only make both of them slow.

A queued job holds no plan of its own. It names a film — by fingerprint,
so a renamed folder is still found — and when its turn comes the plan is
rebuilt from the file and the decisions saved for it (prep_configs). What
gets muxed is therefore whatever was last decided, not a snapshot of the
moment the button was pressed.

A job runs in steps. Any subtitle to be generated from the film's audio
comes first (api/services/srt_gen.py — minutes to an hour each, on the fn
host's speech-to-text service), then the mux. If a generation fails the job
fails with it: a remux asked to carry a subtitle does not quietly go ahead
without one.

The queue is kept on disk as it changes. This process reloads itself when
its code changes, which cuts off a running mux; on startup the leftover
muxer is stopped, its half-written file removed, and the job goes back to
the front of the queue to run again.
"""
import json
import os
import signal
import threading
import time
import uuid
from pathlib import Path

from api.config import MOVIES_DATA_DIR
from api.services import movie_prep, prep_configs, srt_gen
from api.services.movie_prep import PrepError

# Finished jobs kept for display, newest first, until cleared.
HISTORY = 30
# A job cut off by restarts more often than this is not going to finish by
# being retried; it is reported instead.
MAX_ATTEMPTS = 3

_jobs: list[dict] = []
_cond = threading.Condition()

ACTIVE = ("queued", "running")


class _Stopped(Exception):
    """Raised inside the worker when a running job has been stopped."""


def _file() -> Path:
    root = MOVIES_DATA_DIR.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root / "remux_queue.json"


def _persist() -> None:
    """Callers hold _cond."""
    path = _file()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_jobs, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _find(job_id: str) -> dict | None:
    return next((j for j in _jobs if j["id"] == job_id), None)


def _public(j: dict) -> dict:
    return {k: v for k, v in j.items() if k not in ("cancel",)}


def jobs() -> list[dict]:
    """Running first, then the queue in order, then what has finished."""
    with _cond:
        running = [j for j in _jobs if j["state"] == "running"]
        queued = [j for j in _jobs if j["state"] == "queued"]
        done = sorted((j for j in _jobs if j["state"] not in ACTIVE),
                      key=lambda j: j.get("finished") or 0, reverse=True)
        out = []
        for i, j in enumerate(queued):
            out.append({**_public(j), "position": i + 1})
        return [_public(j) for j in running] + out + [_public(j) for j in done]


# ── asking ───────────────────────────────────────────────────────────────
def _check(area_name: str, fingerprint: str) -> dict:
    """The film's current plan, if it is one that can be remuxed now.

    Everything knowable up front is refused here, so asking gets an answer
    rather than a job that fails a moment later: not identified, languages
    in conflict, a film by that name already in the output, or another
    queued film that will be written under the same name."""
    plan = movie_prep.find_plan(area_name, fingerprint)
    if plan is None:
        raise PrepError("that film is no longer in the inbox", 404)
    if plan.get("tmdb_id") is None or not plan.get("target"):
        raise PrepError(f"{Path(plan['folder']).name}: not identified yet — look it up first")
    inbox, library = movie_prep.area(area_name)
    movie_prep.execute(plan, library, dry_run=True, inbox=inbox)   # raises if it cannot run
    return plan


def enqueue(area_name: str, plan: dict, user: str) -> dict:
    """Queue one film. The plan the browser sends is saved first, so the
    queue runs exactly what was on screen when REMUX was pressed — and
    whatever is changed after that, since it is read again when its turn
    comes."""
    fp = movie_prep.save_plan(area_name, plan)["fingerprint"]
    return _enqueue(area_name, fp, user)


def _enqueue(area_name: str, fp: str, user: str) -> dict:
    current = _check(area_name, fp)
    with _cond:
        same = next((j for j in _jobs if j["fingerprint"] == fp and j["state"] in ACTIVE), None)
        if same:
            return {**_public(same), "already": True}
        clash = next((j for j in _jobs if j["state"] in ACTIVE and j["target"] == current["target"]), None)
        if clash:
            raise PrepError(
                f"{current['target']} is already queued from another film — "
                f"two films cannot be written under one name", 409)
        job = {
            "id": uuid.uuid4().hex[:10],
            "area": area_name,
            "fingerprint": fp,
            "movie_id": current.get("movie_id") or "",
            "target": current["target"],
            "folder": Path(current["folder"]).name,
            "by": user,
            "created": time.time(),
            "started": None,
            "finished": None,
            "state": "queued",
            "phase": "",
            # Steps: one per subtitle to generate, then the mux.
            "step": 0,
            "steps": 0,
            "step_label": "",
            "detail": "",
            "percent": None,
            # The speech-to-text service's job id per audio track, so a
            # restart resumes a transcription rather than starting another.
            "stt_jobs": {},
            "error": "",
            "output": "",
            "temp": "",
            "pid": None,
            "attempts": 0,
            "cancel": False,
        }
        _jobs.append(job)
        _persist()
        _cond.notify_all()
        snapshot = _public(job)
    movie_prep._bump()
    return snapshot


def enqueue_all(area_name: str, user: str) -> dict:
    """Queue every film in an inbox that can be remuxed, and say why each
    of the others cannot. Films already queued are left where they are."""
    queued, skipped = [], []
    for plan in movie_prep.scan_area(area_name):
        name = Path(plan.get("folder", "?")).name
        if plan.get("error"):
            skipped.append({"folder": name, "reason": plan["error"]})
            continue
        try:
            job = _enqueue(area_name, plan["fingerprint"], user)
            if job.get("already"):
                skipped.append({"folder": name, "reason": "already queued"})
            else:
                queued.append(job)
        except PrepError as e:
            skipped.append({"folder": name, "reason": str(e)})
    return {"queued": queued, "skipped": skipped}


# ── cancelling ───────────────────────────────────────────────────────────
def remove(job_id: str) -> dict:
    """Take a job out: a queued one is dropped, a running one is stopped,
    a finished one is cleared from the list.

    A running job can be stopped while it is generating subtitles or muxing. After that it is
    checking the new file and then moving it into place and clearing the
    sources away — stopping it half way through *that* is exactly the kind
    of interruption this whole pipeline is arranged to avoid, and it is
    seconds from done anyway."""
    with _cond:
        j = _find(job_id)
        if not j:
            raise PrepError("no such remux", 404)
        if j["state"] == "running":
            if j.get("phase") not in ("", "generating", "muxing"):
                raise PrepError("it is finishing up — too late to stop it", 409)
            j["cancel"] = True
            pid = j.get("pid")
            _persist()
        else:
            _jobs.remove(j)
            _persist()
            pid = None
        snapshot = _public(j)
    if pid:
        # Our own child, still unreaped, so the pid cannot have been reused.
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    movie_prep._bump()
    return snapshot


def clear_finished() -> None:
    with _cond:
        _jobs[:] = [j for j in _jobs if j["state"] in ACTIVE]
        _persist()
    movie_prep._bump()


def job_area(job_id: str) -> str:
    with _cond:
        j = _find(job_id)
        if not j:
            raise PrepError("no such remux", 404)
        return j["area"]


# ── the worker ───────────────────────────────────────────────────────────
def _update(job: dict, **fields) -> None:
    with _cond:
        job.update(fields)
        _persist()


def _worker() -> None:
    while True:
        with _cond:
            while not any(j["state"] == "queued" for j in _jobs):
                _cond.wait()
            job = next(j for j in _jobs if j["state"] == "queued")
            job.update(state="running", started=time.time(), phase="",
                       percent=0, error="", attempts=job.get("attempts", 0) + 1)
            _persist()
        movie_prep._bump()
        _run(job)
        _trim()


def _run(job: dict) -> None:
    def report(**fields):
        # The muxer's pid arrives as soon as it starts; a stop that came in
        # before it existed is carried out now.
        _update(job, **fields)
        if fields.get("pid") and job.get("cancel"):
            try:
                os.kill(fields["pid"], signal.SIGTERM)
            except OSError:
                pass

    copies = []
    try:
        inbox, library = movie_prep.area(job["area"])
        plan = movie_prep.find_plan(job["area"], job["fingerprint"])
        if plan is None:
            raise PrepError("the film is no longer in the inbox")
        preview = movie_prep.execute(plan, library, dry_run=True, inbox=inbox)
        gen = srt_gen.wanted(plan)
        steps = len(gen) + 1
        _update(job, target=plan["target"], output=preview["output"], temp=preview["temp"],
                steps=steps)
        if job.get("cancel"):
            raise _Stopped()

        generated = {}
        stt_jobs = dict(job.get("stt_jobs") or {})
        for i, track in enumerate(gen, 1):
            report(phase="generating", step=i, step_label=track["language"], detail="",
                   percent=None)
            generated[track["key"]] = srt_gen.generate(
                plan, track, stt_jobs=stt_jobs, report=report,
                cancelled=lambda: bool(job.get("cancel")), user=job.get("by") or "")
        # Subtitles uploaded in the player, and the generated ones, are
        # copied into the film's folder for the mux to read.
        plan, copies = movie_prep.stage_uploads(plan)
        if gen:
            plan, more = srt_gen.attach(plan, generated)
            copies += more

        report(step=steps, step_label="", detail="")
        result = movie_prep.execute(plan, library, dry_run=False, inbox=inbox, report=report)
        # The decisions have been used; the film they belonged to is now in
        # the trash and its result in the output.
        prep_configs.forget(job["fingerprint"])
        srt_gen.forget(job["fingerprint"])
        _update(job, state="done", phase="done", percent=100, finished=time.time(),
                pid=None, detail="", output=result["output"], seconds=result["seconds"])
    except Exception as e:  # a job fails; the worker never does
        # Subtitles copied in for the mux, which did not happen. The
        # originals stay where they were (a generated one stays cached).
        for c in copies:
            movie_prep._unlink(c)
        if job.get("cancel") or isinstance(e, srt_gen.Stopped):
            _update(job, state="cancelled", phase="", detail="", finished=time.time(),
                    pid=None, error="stopped")
        else:
            _update(job, state="failed", phase="", detail="", finished=time.time(), pid=None,
                    error=str(e)[:500])
    finally:
        movie_prep._bump()


def _trim() -> None:
    with _cond:
        finished = sorted((j for j in _jobs if j["state"] not in ACTIVE),
                          key=lambda j: j.get("finished") or 0, reverse=True)
        drop = {j["id"] for j in finished[HISTORY:]}
        if drop:
            _jobs[:] = [j for j in _jobs if j["id"] not in drop]
            _persist()


# ── startup ──────────────────────────────────────────────────────────────
def _recover() -> None:
    """Pick the queue back up after a restart, repairing what a cut-off mux
    left behind: the muxer may still be writing, the half-written file is
    in the film's folder, and the output folder was made up front."""
    try:
        saved = json.loads(_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except Exception as e:
        print(f"remux: queue file unreadable ({e}); starting empty")
        return
    requeued = []
    for j in saved:
        if j.get("state") != "running":
            continue
        pid = j.get("pid")
        if pid:
            try:
                cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
                # After a restart the pid is no longer ours to trust: only a
                # process that is really a muxer gets stopped.
                if b"mkvmerge" in cmdline or b"ffmpeg" in cmdline:
                    os.kill(pid, signal.SIGTERM)
            except (OSError, ValueError):
                pass
        if j.get("temp"):
            movie_prep._unlink(Path(j["temp"]))
        if j.get("output"):
            movie_prep._drop_if_empty(Path(j["output"]).parent)
        if j.get("cancel"):
            j.update(state="cancelled", finished=time.time(), pid=None, error="stopped")
        elif j.get("attempts", 0) >= MAX_ATTEMPTS:
            j.update(state="failed", finished=time.time(), pid=None,
                     error=f"interrupted {j['attempts']} times by server restarts — giving up")
        else:
            # Nothing was moved, so running it again is safe; it goes back to
            # the front, ahead of anything queued after it.
            # stt_jobs is kept: a transcription still running on the
            # speech-to-text service is picked up again, not restarted.
            j.update(state="queued", phase="", percent=None, pid=None, temp="",
                     detail="", error="restarted after the server restarted")
            requeued.append(j)
            print(f"remux: {j.get('target')!r} was interrupted by a restart; requeued")
    with _cond:
        # What was cut off goes back to the front: it was next before the
        # restart, and nothing queued after it should overtake it.
        _jobs[:] = requeued + [j for j in saved if j not in requeued]
        _persist()


def init() -> None:
    _recover()
    threading.Thread(target=_worker, name="remux worker", daemon=True).start()
