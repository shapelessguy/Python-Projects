"""Ask MusicBrainz about every song in songs.txt in several different ways,
and record everything it answers, for tuning the matching offline.

Input: songs.txt — file names as `ls` prints them (shell-quoted). Only the
names are used; no file is opened, nothing is moved.

Each song is run through every strategy in STRATEGIES (a way of turning the
name into a search). Each distinct search is sent once — MusicBrainz allows
one a second — and its answer is stored whole in harvest.sqlite:

    songs       one row per name, with how it was split
    runs        (song, strategy) -> the search it produced
    searches    one row per distinct search: how many hits in total
    recordings  the recordings a search returned, in its order
    releases    the releases each recording is on

Resumable: run it again and it carries on where it stopped.

    cd CyanHouse && ../.venv/bin/python scripts/music_match/harvest.py
"""
import json
import re
import shlex
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
SONGS = HERE / "songs.txt"
DB = HERE / "harvest.sqlite"
URL = "https://musicbrainz.org/ws/2/recording"
AGENT = "CyanHouse/1.0 ( https://github.com/shapelessguy/Python-Projects )"
LIMIT = 50          # recordings asked for per search (music_match.RESULTS)
KEEP_RELEASES = 15  # releases kept per recording
SPACING = 1.1       # seconds between requests


# ── reading a name, and the searches ────────────────────────────────────
# The very ones the music inbox uses (api/services/music_match), so what is
# harvested is what the inbox would ask.
sys.path.insert(0, str(HERE.parents[1]))
from api.services.music_match import STRATEGIES, split_name  # noqa: E402


def strategies() -> dict:
    return STRATEGIES


# ── storage ──────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (id INTEGER PRIMARY KEY, name TEXT UNIQUE, stem TEXT, parts TEXT);
CREATE TABLE IF NOT EXISTS runs (song_id INTEGER, strategy TEXT, query TEXT,
    PRIMARY KEY (song_id, strategy));
CREATE TABLE IF NOT EXISTS searches (query TEXT PRIMARY KEY, total INTEGER, returned INTEGER,
    error TEXT, at REAL);
CREATE TABLE IF NOT EXISTS recordings (query TEXT, rank INTEGER, score INTEGER, rec_id TEXT,
    title TEXT, artist TEXT, artists TEXT, length REAL, disambiguation TEXT, video INTEGER,
    n_releases INTEGER, PRIMARY KEY (query, rank));
CREATE TABLE IF NOT EXISTS releases (query TEXT, rank INTEGER, rel_rank INTEGER, release_id TEXT,
    release TEXT, album_artist TEXT, status TEXT, date TEXT, country TEXT,
    rg_id TEXT, rg_title TEXT, primary_type TEXT, secondary_types TEXT,
    track_number TEXT, track_position INTEGER, medium_position INTEGER, medium_tracks INTEGER,
    release_tracks INTEGER, PRIMARY KEY (query, rank, rel_rank));
CREATE INDEX IF NOT EXISTS runs_query ON runs (query);
"""


def credit(c) -> str:
    return "".join(x.get("name", "") + x.get("joinphrase", "") for x in c or []).strip()


def store(db, query: str, answer: dict | None, error: str = "") -> None:
    recs = (answer or {}).get("recordings") or []
    db.execute("INSERT OR REPLACE INTO searches VALUES (?,?,?,?,?)",
               (query, (answer or {}).get("count"), len(recs), error, time.time()))
    for rank, r in enumerate(recs):
        rels = r.get("releases") or []
        db.execute("INSERT OR REPLACE INTO recordings VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            query, rank, r.get("score"), r.get("id"), r.get("title"), credit(r.get("artist-credit")),
            json.dumps([c.get("name") for c in r.get("artist-credit") or []], ensure_ascii=False),
            (r.get("length") or 0) / 1000 or None, r.get("disambiguation") or "",
            int(bool(r.get("video"))), len(rels)))
        for i, rel in enumerate(rels[:KEEP_RELEASES]):
            g = rel.get("release-group") or {}
            media = rel.get("media") or [{}]
            m = media[0]
            t = (m.get("track") or [{}])[0]
            db.execute("INSERT OR REPLACE INTO releases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                query, rank, i, rel.get("id"), rel.get("title"),
                credit(rel.get("artist-credit")) or credit(r.get("artist-credit")),
                rel.get("status"), rel.get("date"), rel.get("country"),
                g.get("id"), g.get("title"), g.get("primary-type"),
                json.dumps(g.get("secondary-types") or []),
                t.get("number"),
                (m["track-offset"] + 1) if m.get("track-offset") is not None else None,
                m.get("position"), m.get("track-count"), rel.get("track-count")))


# ── asking ───────────────────────────────────────────────────────────────
_last = 0.0


def ask(query: str) -> dict:
    global _last
    for attempt in range(6):
        wait = SPACING - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(URL, params={"query": query, "fmt": "json", "limit": LIMIT},
                             headers={"User-Agent": AGENT}, timeout=30)
        except requests.RequestException:
            r = None
        _last = time.time()
        if r is not None and r.status_code == 200:
            return r.json()
        if r is not None and r.status_code == 400:
            raise ValueError(f"MusicBrainz refused the query ({r.text[:120]})")
        time.sleep(2 * (attempt + 1))          # 503 (slow down) or a network hiccup
    raise RuntimeError("no answer after retries")


def load_songs() -> list[str]:
    out = []
    for line in SONGS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(shlex.split(line)[0] if line[0] in "'\"" else line)
    return out


def main() -> None:
    db = sqlite3.connect(DB)
    db.executescript(SCHEMA)
    strat = strategies()
    names = load_songs()
    for name in names:
        s = split_name(name)
        db.execute("INSERT OR IGNORE INTO songs (name, stem, parts) VALUES (?,?,?)",
                   (name, s["stem"], json.dumps(s["parts"], ensure_ascii=False)))
        sid = db.execute("SELECT id FROM songs WHERE name = ?", (name,)).fetchone()[0]
        # Rebuilt each time, so a change to split_name or a strategy replaces
        # the searches it no longer makes.
        db.execute("UPDATE songs SET stem = ?, parts = ? WHERE id = ?",
                   (s["stem"], json.dumps(s["parts"], ensure_ascii=False), sid))
        db.execute("DELETE FROM runs WHERE song_id = ?", (sid,))
        for key, build in strat.items():
            q = build(s) or None
            if q:
                db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?)", (sid, key, q))
    db.commit()

    todo = [q for (q,) in db.execute(
        "SELECT DISTINCT query FROM runs WHERE query NOT IN (SELECT query FROM searches WHERE error = '')")]
    print(f"{len(names)} songs, {len(strat)} strategies, {len(todo)} searches to send "
          f"(~{len(todo) * SPACING / 3600:.1f} h)", flush=True)
    for i, q in enumerate(todo, 1):
        try:
            store(db, q, ask(q))
        except Exception as e:
            store(db, q, None, f"{e.__class__.__name__}: {e}")
        db.commit()
        if i % 50 == 0 or i == len(todo):
            print(f"{i}/{len(todo)}  {time.strftime('%H:%M:%S')}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
