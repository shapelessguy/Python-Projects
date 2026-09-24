"""Start ground_truth.csv from what has already been filed.

For every name in songs.txt, find the file it became in the music library
(MUSIC_DIR) or a music pair's output, by comparing the name with the filed
file's artist and title tags, and record what it was filed as — a proposal
for a person to verify, not the truth itself. Songs still in the inbox get
an empty row. Every row carries the song's length when its file is found,
since that is the evidence the matching leans on.

    cd CyanHouse && ../.venv/bin/python scripts/music_match/build_ground_truth.py

Columns: name, seconds, found (filed / inbox / —), how (how the filed file
was matched to the name), artist, title, album, album_artist, year,
release_group_id, release_id, file, verified (yours: y, n, or a fix), notes.
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import mutagen  # noqa: E402

from api.services import movie_prep, music_prep as m  # noqa: E402
import harvest  # noqa: E402

OUT = HERE / "ground_truth.csv"
FIELDS = ["name", "seconds", "found", "how", "artist", "title", "album", "album_artist", "year",
          "release_group_id", "release_id", "file", "verified", "notes"]


def filed_roots() -> list[Path]:
    roots = []
    for key, (_, folder) in movie_prep.MEDIA_LIBRARIES.items():
        if key == ":music" and folder and folder.is_dir():
            roots.append(folder)
    for cfg in movie_prep.areas().values():
        if cfg.get("type") == "music" and Path(cfg["library"]).is_dir():
            roots.append(Path(cfg["library"]))
    return roots


def inboxes() -> list[Path]:
    return [Path(c["inbox"]) for c in movie_prep.areas().values()
            if c.get("type") == "music" and c.get("inbox") and Path(c["inbox"]).is_dir()]


def tags_of(p: Path) -> dict:
    t = mutagen.File(p, easy=True)
    raw = mutagen.File(p)
    first = lambda k: ((t.get(k) or [""])[0] if t is not None and t.tags is not None else "")  # noqa: E731
    ids = {}
    if raw is not None and raw.tags is not None:
        for k, v in raw.tags.items():
            ks = str(k).lower()
            val = str(v.text[0]) if hasattr(v, "text") else str(v[0] if isinstance(v, list) else v)
            if "release group id" in ks or "releasegroupid" in ks:
                ids["release_group_id"] = val
            elif "album id" in ks or "albumid" in ks and "artist" not in ks:
                ids["release_id"] = val
    return {"artist": first("artist"), "title": first("title"), "album": first("album"),
            "album_artist": first("albumartist"), "year": first("date")[:4], **ids,
            "seconds": round(float(raw.info.length), 1) if raw is not None else ""}


def readings(name: str) -> list[tuple[str, str]]:
    parts = harvest.split_name(name)["parts"]
    out = []
    if len(parts) >= 2:
        out += [(parts[0], " - ".join(parts[1:])), (parts[-1], " - ".join(parts[:-1]))]
        for i in range(len(parts) - 1):
            out += [(parts[i], parts[i + 1]), (parts[i + 1], parts[i])]
    return out


def main() -> None:
    names = harvest.load_songs()

    # Every filed song, with the keys it is matched on.
    filed = []
    for root in filed_roots():
        for p in sorted(set(root.rglob("*"))):
            if p.is_file() and movie_prep.file_kind(p) == "audio":
                t = tags_of(p)
                credited = {m._artist_key(t["artist"]), m._artist_key(t["album_artist"])} - {""}
                filed.append({"path": p, "tags": t, "artists": credited,
                              "title": m._title_key(t["title"]), "loose": m._loose_title(t["title"])})
    in_inbox = {}
    for box in inboxes():
        for p in set(box.rglob("*")):
            if p.is_file():
                in_inbox.setdefault(p.name, p)

    rows, used = [], {}

    def link(row, f, how):
        t = f["tags"]
        row.update(found="filed", how=how, artist=t["artist"], title=t["title"], album=t["album"],
                   album_artist=t["album_artist"], year=t["year"],
                   release_group_id=t.get("release_group_id", ""), release_id=t.get("release_id", ""),
                   file=str(f["path"]), seconds=t["seconds"])
        used.setdefault(str(f["path"]), []).append(row["name"])

    # First pass, for every name: a filed song with the same artist and title.
    for name in names:
        row = {k: "" for k in FIELDS}
        row["name"] = name
        for a, t in readings(name):
            tk, tl, ak = m._title_key(t), m._loose_title(t), m._artist_key(a)
            hit = next((f for f in filed
                        if (m._alike(tk, f["title"]) or (tl and m._alike(tl, f["loose"])))
                        and any(m._alike(ak, c) for c in f["artists"])), None)
            if hit:
                link(row, hit, "artist+title")
                break
        rows.append(row)

    # Second pass, only among files no name has claimed: the very same title,
    # whoever it is by — the name's "artist" may be a genre or a show
    # ("Balli di gruppo"), or simply wrong ("ACDC - Smoke on the water").
    for row in rows:
        if row["found"]:
            continue
        for a, t in readings(row["name"])[:1]:
            hits = [f for f in filed if str(f["path"]) not in used and m._title_key(t) == f["title"]]
            if len(hits) == 1:
                link(row, hits[0], "title only")

    for row in rows:
        if row["found"]:
            continue
        name = row["name"]
        if name in in_inbox:
            row.update(found="inbox", file=str(in_inbox[name]))
            try:
                row["seconds"] = round(float(mutagen.File(in_inbox[name]).info.length), 1)
            except Exception:
                pass
        else:
            row["found"] = "—"

    # Last pass: a name nothing matched, and a filed file no name claimed,
    # by the same artist — most likely the same song under another title
    # ("Remy Zero - Smallville" is "Save Me"). Marked for checking.
    free = [f for f in filed if str(f["path"]) not in used]
    for row in rows:
        if row["found"] != "—":
            continue
        for a, t in readings(row["name"])[:2]:
            ak = m._artist_key(a)
            same = [f for f in free if any(m._alike(ak, c) for c in f["artists"])]
            if not same:
                continue
            from difflib import SequenceMatcher
            f = max(same, key=lambda f: SequenceMatcher(None, m._title_key(t), f["title"]).ratio())
            tg = f["tags"]
            row.update(found="filed", how="artist only", artist=tg["artist"], title=tg["title"],
                       album=tg["album"], album_artist=tg["album_artist"], year=tg["year"],
                       release_group_id=tg.get("release_group_id", ""),
                       release_id=tg.get("release_id", ""), file=str(f["path"]), seconds=tg["seconds"])
            used.setdefault(str(f["path"]), []).append(row["name"])
            free.remove(f)
            break

    # One filed file claimed by two names: say so, for the person checking.
    for path, who in used.items():
        if len(who) > 1:
            for r in rows:
                if r["file"] == path:
                    r["notes"] = f"same file as {len(who) - 1} other name(s)"

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        key = r["found"] + (f" ({r['how']})" if r["how"] else "")
        counts[key] = counts.get(key, 0) + 1
    print(f"{len(rows)} songs -> {OUT}")
    for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  {k}")
    print(f"  {len(filed)} filed files, {sum(1 for f in filed if str(f['path']) not in used)} not matched to any name")


if __name__ == "__main__":
    main()
