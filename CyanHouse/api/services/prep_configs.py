"""The decisions made about a film before it is remuxed, remembered.

Choosing a film's name, which audio and subtitles it keeps, what language
each one is and how far each is out of sync takes a while — and it used to
live only in the browser tab where it was made. Now every change is sent
here, so the choices survive a reload, are the same in every browser, and
are what a *queued* remux actually uses when its turn comes, however long
after the button was pressed.

Keyed by the film's fingerprint (movies.fingerprint), not its path: a
download folder gets renamed as often as anything gets done to it, and the
choices belong to the film, not to where it was sitting.

Only what a person decided is stored — the name, and per track the
language, delay, keep and default flags, and whether a subtitle is to be
generated from it (srt_gen) — never the whole plan. The plan is
rebuilt from the file on every scan and these are laid over it, so a track
that has since disappeared is simply ignored and a new one arrives with its
own defaults.
"""
import json
import os
import threading
import time
from pathlib import Path

from api.config import MOVIES_DATA_DIR

_lock = threading.Lock()

# The identity fields worth remembering, and the per-track ones.
PLAN_FIELDS = ("title", "year", "tmdb_id", "target")
TRACK_FIELDS = ("language", "delay_ms", "keep", "default", "gen_srt")


def _path() -> Path:
    root = MOVIES_DATA_DIR.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root / "prep_configs.json"


def _load() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        # Never overwrite what could not be read — a stale file is fixable
        # by hand, a replaced one is gone.
        print(f"prep: config store unreadable ({e}); not using it")
        return {}


def _save_all(data: dict) -> None:
    path = _path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def save(fingerprint: str, plan: dict, where: str = "") -> dict:
    """Remember what was decided about this film."""
    entry = {k: plan.get(k) for k in PLAN_FIELDS}
    entry["tracks"] = {
        t["key"]: {k: t.get(k) for k in TRACK_FIELDS}
        for t in plan.get("tracks", [])
        if isinstance(t, dict) and t.get("key") and t.get("type") != "video"
    }
    # For whoever reads this file by hand; the fingerprint is the link.
    entry["seen_at"] = where
    entry["saved"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _lock:
        data = _load()
        data[fingerprint] = entry
        _save_all(data)
    return entry


def get(fingerprint: str) -> dict | None:
    with _lock:
        return _load().get(fingerprint)


def overlay(plan: dict, saved: dict | None) -> dict:
    """The freshly analysed plan, with what was decided laid over it."""
    if not saved:
        return plan
    out = dict(plan)
    for k in PLAN_FIELDS:
        if k in saved:
            out[k] = saved[k]
    decided = saved.get("tracks") or {}
    out["tracks"] = [
        {**t, **{k: v for k, v in decided[t["key"]].items() if k in TRACK_FIELDS}}
        if t.get("key") in decided else t
        for t in plan.get("tracks", [])
    ]
    # The language was chosen by a person, so it is no longer a guess.
    for t in out["tracks"]:
        if t.get("key") in decided and "language" in decided[t["key"]]:
            t["language_guessed"] = False
    out["saved"] = True
    return out


def forget(fingerprint: str) -> None:
    """Drop a film's decisions — once it is remuxed they have been used."""
    with _lock:
        data = _load()
        if data.pop(fingerprint, None) is not None:
            _save_all(data)
