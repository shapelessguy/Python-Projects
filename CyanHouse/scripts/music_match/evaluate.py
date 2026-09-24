"""Measure the song-recognition rules offline, against the ground truth.

The rules are the ones the music inbox really uses — api/services/music_match
— so what is measured here is what the inbox does. Everything comes from
files, no MusicBrainz, no music folder:

    harvest.sqlite      what MusicBrainz answered to every strategy's search
    ground_truth.xlsx   per raw name: the right artist and song when Check is V
    ground_truth.csv    per raw name: the file's length in seconds

Each song's raw name, length and harvested answers go through decide(); the
result is scored on the V rows:

    right   it matched, and to the labelled song
    wrong   it matched, but to another song      <- must stay 0
    review  it did not match

plus how many of the unlabelled songs (not recognised so far) it would now
match. Try a variant by changing a Params field:

    from dataclasses import replace
    report(songs, {"current": PARAMS, "slack 10": replace(PARAMS, slack=10)})

    cd CyanHouse && ../.venv/bin/python scripts/music_match/evaluate.py
"""
import csv
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from api.services.music_match import (  # noqa: E402
    PARAMS, STRATEGIES, Cand, Params, alike, artist_keys, decide, loose_title, title_key)


@dataclass
class Song:
    name: str
    parts: list
    seconds: float | None
    label: tuple | None          # (artist, title) when Check is V
    check: str
    cands: list = field(default_factory=list)


def load() -> list[Song]:
    db = sqlite3.connect(HERE / "harvest.sqlite")
    rels: dict[tuple, list] = {}
    for row in db.execute(
            "SELECT query, rank, rel_rank, release, album_artist, status, date, primary_type, secondary_types,"
            " country, release_id, rg_id, track_number, track_position, medium_position, medium_tracks,"
            " release_tracks FROM releases"):
        rels.setdefault(row[:2], []).append(row[2:])
    recs: dict[str, list] = {}
    for row in db.execute(
            "SELECT query, rank, title, artist, artists, length, disambiguation, rec_id FROM recordings"):
        recs.setdefault(row[0], []).append(row[1:])

    seconds = {}
    with (HERE / "ground_truth.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            seconds[r["name"]] = float(r["seconds"]) if r["seconds"] else None
    labels = {}
    import openpyxl
    ws = openpyxl.load_workbook(HERE / "ground_truth.xlsx", read_only=True)["Songs"]
    for name, artist, song, check in ws.iter_rows(min_row=2, max_col=4, values_only=True):
        labels[name] = ((artist or "", song or ""), (check or "").strip().upper())

    songs = []
    for sid, name, parts in db.execute("SELECT id, name, parts FROM songs"):
        (artist, title), check = labels.get(name, (("", ""), ""))
        s = Song(name, json.loads(parts), seconds.get(name),
                 (artist, title) if check == "V" and title else None, check)
        for strategy, q in db.execute("SELECT strategy, query FROM runs WHERE song_id = ?", (sid,)):
            for rank, title_, artist_, artists, length, dis, rec_id in recs.get(q, []):
                base = dict(strategy=strategy, title=title_ or "", artist=artist_ or "",
                            artists=json.loads(artists or "[]"), length=length,
                            disambiguation=dis or "", recording_id=rec_id or "")
                rows = sorted(rels.get((q, rank), []))
                if not rows:
                    s.cands.append(Cand(**base))
                for (_, release, aa, status, date, prim, sec, country, rel_id, rg_id,
                     tnum, tpos, mpos, mtracks, rtracks) in rows:
                    s.cands.append(Cand(
                        **base, release=release or "", album_artist=aa or "", status=status or "",
                        date=date or "", primary=prim or "", secondary=json.loads(sec or "[]"),
                        country=country or "", release_id=rel_id or "", release_group_id=rg_id or "",
                        track_number=tnum or "", track_position=tpos, medium_position=mpos,
                        medium_tracks=mtracks, release_tracks=rtracks))
        songs.append(s)
    return songs


_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}


def _numbered(t: str) -> str:
    """For comparing a result with its label only: "Part 2", "Pt. 2" and a
    closing "II" all say the same thing."""
    t = re.sub(r",?\s*\b(?:part|pt)\.?\s*", " ", t or "", flags=re.I)
    return re.sub(r"\b(i{1,3}|iv|v)\s*$", lambda m: _ROMAN[m.group(1).lower()], t.strip(), flags=re.I)


def same_song(c: Cand, label: tuple) -> bool:
    la, lt = label
    ct, lt = _numbered(c.title), _numbered(lt)
    ta = title_key(ct) == title_key(lt) or loose_title(ct) == loose_title(lt) \
        or alike(loose_title(ct), loose_title(lt), 0.9)
    credited = set().union(*(artist_keys(x) for x in c.artists or [c.artist])) | artist_keys(c.artist)
    return ta and bool(credited & artist_keys(la))


def cached_lookup(recording_id: str) -> dict | None:
    """A recording's full entry, only if the inbox (or a test) has already
    fetched it — the evaluation never asks MusicBrainz. Songs whose lookups
    are missing are scored as if the lookup found nothing."""
    import sqlite3 as _sq
    db = _sq.connect(HERE.parents[1] / "data" / "api" / "data" / "music" / "searches.sqlite")
    row = db.execute("SELECT answer FROM search WHERE query = ?", (f"lookup|{recording_id}",)).fetchone()
    return json.loads(row[0]) if row else None


def score(songs: list[Song], p: Params, show: str = "") -> dict:
    out = {"right": 0, "wrong": 0, "review": 0, "new": 0, "unlabelled": 0}
    for s in songs:
        c, why = decide(s.parts, s.seconds, s.cands, p, lookup=cached_lookup)
        if s.label:
            if c is None:
                out["review"] += 1
            elif same_song(c, s.label):
                out["right"] += 1
            else:
                out["wrong"] += 1
                if "wrong" in show:
                    print(f"   WRONG {s.name}  label={s.label}  got={c.artist} - {c.title} [{c.release}]")
        elif s.check == "":
            out["unlabelled"] += 1
            if c is not None:
                out["new"] += 1
                if "new" in show:
                    print(f"   NEW   {s.name}  ->  {c.artist} - {c.title} [{c.release}]")
    return out


def report(songs, variants: dict, show: str = "wrong"):
    print(f"{sum(1 for s in songs if s.label)} labelled (V) songs, "
          f"{sum(1 for s in songs if not s.label and s.check == '')} unlabelled\n")
    print(f"{'rules':40} {'right':>6} {'wrong':>6} {'review':>7}   {'new of unlabelled':>18}")
    for name, p in variants.items():
        r = score(songs, p, show)
        print(f"{name:40} {r['right']:6d} {r['wrong']:6d} {r['review']:7d}   {r['new']:6d} / {r['unlabelled']}")


if __name__ == "__main__":
    from dataclasses import replace
    songs = load()
    report(songs, {
        "current (PARAMS)": PARAMS,
        "all 15 strategies": replace(PARAMS, strategies=tuple(STRATEGIES)),
    })
