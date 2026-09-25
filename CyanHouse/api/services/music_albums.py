"""Recognising a whole album at once, in a music inbox.

Song by song, a file is found by its name — "Artist - Title" — and a
download of a discography rarely names its files that way: "01. Stressed
Out.flac", in a folder "(2015) Blurryface", in a folder "Twenty One Pilots -
Studio Discography". What such a download does carry is its folders and,
often, its tags; and above all, what the files *are* as a set: how many,
in which order, and how long each one is. That is what this matches on.

  1. Albums. Every folder that holds songs itself is an album — a folder
     inside the inbox, at any depth; songs loose at the top of the inbox
     are left to the song-by-song matching. A folder that is only a disc of
     one ("CD2", "Disc 1", "Album (disc 1 of 2)") joins the album it is a
     disc of.
  2. Hints, from the tags when they have them (album artist, album, year,
     track and disc numbers, titles) and otherwise from the names: each
     folder name on the way is read for an artist, a year and an album
     ("2003 - Album", "(2011) Album", "Artist - Album (2016) [FLAC]"), with
     the usual noise dropped (years, formats, "Discography", catalogue
     numbers). They may be wrong; they only choose what to ask.
  3. MusicBrainz is asked for releases by those names, and each likely one
     is checked against the folder, track by track: the song at each
     position against the release's — its title, and its length. A release
     is taken only when (nearly) every song of the folder lines up with
     one of its tracks; lengths within seconds of each other are what make
     that sure, and what tell a deluxe edition from the plain one.
  4. The songs that lined up are filed as that release; anything that did
     not stays for the song-by-song matching.
"""
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import mutagen

# A song's length may differ from the release's by this much and still be
# that track (different masterings and encoders differ by a second or two).
LENGTH_CLOSE = 4.0
# …and by this much when its title also clearly agrees.
LENGTH_LOOSE = 12.0
# How many of the folder's songs must line up for the release to be taken.
SHARE_NEEDED = 0.8
MIN_SONGS = 2
# How many releases found are looked at track by track (one request each).
CHECK_AT_MOST = 6

# "CD2", "Disc 1", "Disk 03", "Part 2" — as a whole folder name, or at the
# end of one ("… (disc 1 of 2)", "… CD1", "… [Disc 2]").
_DISC_ONLY = re.compile(r"^\s*(?:cd|disc|disk|part)\s*0*(\d{1,2})\s*$", re.I)
_DISC_TAIL = re.compile(r"\s*[\(\[]?\s*(?:cd|disc|disk)\s*0*(\d{1,2})(?:\s*of\s*\d{1,2})?\s*[\)\]]?\s*$", re.I)
_YEAR = re.compile(r"(?<!\d)(19[0-9]{2}|20[0-9]{2})(?!\d)")
# Words that describe the download, not the music.
_NOISE_WORDS = re.compile(
    r"\b(discography|studio|albums?|complete|collection|flac|mp3|aac|alac|ogg|wav|web|cd|vinyl|lp|"
    r"\d{2,4}\s*k(?:bps)?|kbps|24\s*bit|16\s*bit|hi-?res|lossless|remaster(?:ed)?|deluxe|edition|"
    r"expanded|anniversary|bonus|tracks?|version|rip|scene)\b", re.I)
_TRACK_LEAD = re.compile(r"^\s*(?:(\d{1,2})[-.](?=\d))?(\d{1,3})\s*(?:[-._)]\s*|\s+)")


def _tags(path: Path) -> dict:
    try:
        f = mutagen.File(path, easy=True)
        length = float(f.info.length) if f is not None and f.info else 0.0
        if f is None or f.tags is None:
            return {"length": length}
        first = lambda k: (f.tags.get(k) or [""])[0].strip()  # noqa: E731
        return {"length": length, "title": first("title"), "album": first("album"),
                "albumartist": first("albumartist"), "artist": first("artist"),
                "date": first("date"), "tracknumber": first("tracknumber"), "discnumber": first("discnumber")}
    except Exception:
        return {"length": 0.0}


def _number(s: str) -> int | None:
    m = re.match(r"\s*0*(\d{1,3})", s or "")
    return int(m.group(1)) if m else None


def _without_brackets(s: str, keep_plain: bool = True) -> str:
    """Drop the bracketed parts that say nothing about the music: a year,
    a format or edition, a catalogue number ("EMI CDP 7 46435 2"). One that
    is part of the title ("(Vol 1)") stays, unless keep_plain is False."""
    def drop(m: re.Match) -> str:
        inner = m.group(0)[1:-1]
        if not keep_plain:
            return " "
        if _YEAR.fullmatch(inner.strip()) or _NOISE_WORDS.search(inner) or len(re.findall(r"\d", inner)) >= 4:
            return " "
        return m.group(0)
    return re.sub(r"\s+", " ", re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", drop, s)).strip(" -_.")


def _read_name(name: str) -> dict:
    """What a folder name says: {"artist", "album", "year"}, any of them "".
    "2003 - Album", "(2011) Album", "Artist - Album (2016) [WEB FLAC]",
    "Album", "Artist - Discography 2003-2013"."""
    year = ""
    m = _YEAR.search(name)
    if m:
        year = m.group(1)
    s = _DISC_TAIL.sub("", name)
    s = re.sub(r"^\s*[\(\[]?(?:19|20)\d{2}[\)\]]?\s*[-._]?\s*", "", s)          # a leading year
    s = re.sub(r"\s*[\(\[]?(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}[\)\]]?", "", s)  # a span of years
    s = _without_brackets(s)
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", s) if p.strip()]
    artist, album = "", s
    if len(parts) >= 2:
        artist, album = parts[0], " - ".join(parts[1:])
    album = _NOISE_WORDS.sub("", album)
    album = re.sub(r"\s+", " ", album).strip(" -_.")
    return {"artist": artist.strip(), "album": album, "year": year}


def _clean_title(stem: str, artists: list[str]) -> str:
    s = _TRACK_LEAD.sub("", stem.replace("_", " "), count=1).strip()
    for a in artists:
        if a and s.casefold().startswith(a.casefold() + " - "):
            s = s[len(a) + 3:]
    return s.strip(" -.")


# ── 1. albums ─────────────────────────────────────────────────────────────
def albums(inbox: Path, songs: list[Path]) -> dict[str, list[tuple[Path, int]]]:
    """The inbox's songs grouped into albums, by the album folder's path
    (relative to the inbox): each song with the disc it is on, when its
    folder says (0 when not)."""
    out: dict[str, list[tuple[Path, int]]] = {}
    for p in songs:
        folder = p.parent
        if folder == inbox:
            continue
        rel = folder.relative_to(inbox)
        disc = 0
        m = _DISC_ONLY.match(folder.name)
        if m and folder.parent != inbox:
            disc, rel = int(m.group(1)), rel.parent
        else:
            m = _DISC_TAIL.search(folder.name)
            if m and _DISC_TAIL.sub("", folder.name).strip():
                disc = int(m.group(1))
                rel = rel.parent / _DISC_TAIL.sub("", folder.name).strip()
        out.setdefault(str(rel), []).append((p, disc))
    return out


# ── 2. hints ─────────────────────────────────────────────────────────────
def hints(album_rel: str, files: list[tuple[Path, int]]) -> dict:
    """Who and what the album probably is, and its songs as the folder has
    them: [{"path", "disc", "number", "title", "length"}]."""
    tags = [_tags(p) for p, _ in files]
    common = lambda k: Counter(t.get(k) for t in tags if t.get(k)).most_common(1)  # noqa: E731
    names = [_read_name(part) for part in Path(album_rel).parts]
    here = names[-1]
    artists: list[str] = []
    for c in (common("albumartist"), common("artist")):
        if c:
            artists.append(c[0][0])
    artists += [here["artist"]] + [n["artist"] for n in reversed(names[:-1])]
    # A parent folder with no " - " in it may be the artist's own name
    # ("Jacob Collier/…") — or not ("Original Masters/…"): asked, not trusted.
    artists += [n["album"] for n in reversed(names[:-1]) if not n["artist"]]
    album_names = []
    if common("album"):
        # "B'Day Disc 1": the album's name, not the disc's.
        album_names.append(_without_brackets(_DISC_TAIL.sub("", common("album")[0][0])))
    album_names.append(here["album"])
    year = (common("date")[0][0][:4] if common("date") else "") or here["year"]
    songs = []
    for (p, disc), t in zip(files, tags):
        songs.append({
            "path": p,
            "disc": disc or _number(t.get("discnumber", "")) or 0,
            "number": _number(t.get("tracknumber", "")) or _number(_TRACK_LEAD.match(p.stem).group(2)
                                                                 if _TRACK_LEAD.match(p.stem) else ""),
            "title": t.get("title") or _clean_title(p.stem, artists),
            "length": t.get("length") or 0.0,
        })
    uniq = lambda xs: list(dict.fromkeys(x for x in xs if x and x.strip()))  # noqa: E731
    return {"artists": uniq(artists), "albums": uniq(album_names), "year": year, "songs": songs}


# ── 3. which release ─────────────────────────────────────────────────────
def _similar(a: str, b: str) -> float:
    from api.services.music_prep import _title_key
    a, b = _title_key(a), _title_key(b)
    if not a or not b:
        return 0.0
    return 1.0 if a == b else SequenceMatcher(None, a, b).ratio()


def _release_tracks(release: dict) -> list[dict]:
    out = []
    discs = release.get("media") or []
    for medium in discs:
        for i, t in enumerate(medium.get("tracks") or []):
            rec = t.get("recording") or {}
            out.append({
                "disc": medium.get("position") or 1, "position": i + 1,
                "number": t.get("number") or str(i + 1),
                "title": t.get("title") or rec.get("title") or "",
                "length": ((t.get("length") or rec.get("length") or 0) / 1000),
                "recording_id": rec.get("id"),
                "artist_credit": t.get("artist-credit") or rec.get("artist-credit"),
                "medium_tracks": medium.get("track-count") or len(medium.get("tracks") or []),
            })
    return out


def _line_up(songs: list[dict], tracks: list[dict]) -> list[tuple[dict, dict]]:
    """Each song paired with the release track it is, where one fits: at its
    own disc and number first, then anywhere by title — and in either case
    only when the length agrees (or, when the title clearly does, is near)."""
    multi = len({t["disc"] for t in tracks}) > 1
    used: set[int] = set()
    pairs = []

    def fits(s: dict, t: dict) -> bool:
        gap = abs(s["length"] - t["length"]) if s["length"] and t["length"] else None
        title = _similar(s["title"], t["title"])
        if gap is not None and gap <= LENGTH_CLOSE and title >= 0.5:
            return True
        if gap is not None and gap <= 1.5:        # same length to the second: the track, whatever it is called
            return True
        return title >= 0.9 and (gap is None or gap <= LENGTH_LOOSE)

    for s in songs:
        pick = None
        if s["number"]:
            disc = s["disc"] or (1 if not multi else None)
            for i, t in enumerate(tracks):
                if i not in used and t["position"] == s["number"] and (disc is None or t["disc"] == disc) and fits(s, t):
                    pick = i
                    break
        if pick is None:
            best = max(((i, _similar(s["title"], t["title"])) for i, t in enumerate(tracks) if i not in used),
                       key=lambda x: x[1], default=(None, 0))
            if best[0] is not None and fits(s, tracks[best[0]]):
                pick = best[0]
        if pick is not None:
            used.add(pick)
            pairs.append((s, tracks[pick]))
    return pairs


def match(h: dict) -> tuple[dict | None, list[tuple[dict, dict]], str]:
    """The release this album is, the songs paired with its tracks, and
    why not when there is none."""
    from api.services.music_prep import _credit, _lucene, mb_get
    songs = h["songs"]
    if len(songs) < MIN_SONGS:
        return None, [], "too few songs in the folder to recognise it as an album"
    queries = []
    for album in h["albums"][:2]:
        for artist in h["artists"][:3]:
            queries.append(f'release:"{_lucene(album)}" AND artist:"{_lucene(artist)}"')
        queries.append(f'release:"{_lucene(album)}"')
    # The same, word by word and each word allowed a typo: a download's
    # spelling is often a little off ("8 Day of Christmas").
    words = lambda t: " ".join(w + "~" if len(w) > 3 else w for w in re.findall(r"[^\W_]+", t))  # noqa: E731
    fuzzy = [f"release:({words(album)})" + (f" AND artist:({words(h['artists'][0])})" if h["artists"] else "")
             for album in h["albums"][:1] if re.search(r"\w", album)]
    n = len(songs)
    best: tuple[dict | None, list] = (None, [])
    for batch in (queries, fuzzy):
        # A popular album has dozens of releases (editions, countries): all
        # of them, a hundred per question.
        found: dict[str, dict] = {}
        for q in dict.fromkeys(batch):
            for r in (mb_get("release", {"query": q, "limit": 100}).get("releases") or []):
                found.setdefault(r["id"], r)
        best = _best_release(found, songs, h, best)
        if best[0] is not None and len(best[1]) >= max(MIN_SONGS, SHARE_NEEDED * n):
            break
    release, pairs = best
    if release is None and not pairs:
        return None, [], "no album of that name in MusicBrainz lines up with the folder"
    if release is None or len(pairs) < max(MIN_SONGS, SHARE_NEEDED * n):
        return None, [], f"no release lines up with the folder's songs (best: {len(pairs)} of {n})"
    return release, pairs, ""


def _best_release(found: dict[str, dict], songs: list[dict], h: dict,
                  best: tuple[dict | None, list]) -> tuple[dict | None, list]:
    """Of the releases found, the one the most songs line up with — the
    likeliest few looked at track by track."""
    from api.services.music_prep import mb_get
    n = len(songs)
    # Likeliest first: as many tracks as there are songs (or a few more — a
    # folder may miss a song), official, dated like the folder.
    def likely(r: dict) -> tuple:
        count = r.get("track-count") or 0
        return (count < n, abs(count - n), r.get("status") != "Official",
                bool(h["year"]) and not (r.get("date") or "").startswith(h["year"]), r.get("date") or "9999")
    for r in sorted(found.values(), key=likely)[:CHECK_AT_MOST]:
        full = mb_get(f"release/{r['id']}", {"inc": "recordings+artist-credits+release-groups"})
        if not full:
            continue
        pairs = _line_up(songs, _release_tracks(full))
        # More songs placed wins; then the release that is least bigger than
        # the folder (the plain album over the deluxe one, for a plain folder).
        if len(pairs) > len(best[1]) or (
                best[0] is not None and len(pairs) == len(best[1])
                and abs(len(_release_tracks(full)) - n) < abs(len(_release_tracks(best[0])) - n)):
            best = (full, pairs)
    return best


# ── 4. as filing options ─────────────────────────────────────────────────
def option(release: dict, track: dict) -> dict:
    """A paired track as the option music_prep.file_song() files under."""
    from api.services.music_prep import _credit
    group = release.get("release-group") or {}
    date = release.get("date") or group.get("first-release-date") or ""
    artists = [c.get("name", "") for c in track.get("artist_credit") or []]
    discs = len(release.get("media") or []) or 1
    return {
        "recording_id": track.get("recording_id"), "release_id": release.get("id"),
        "release_group_id": group.get("id"),
        "artist": _credit(track.get("artist_credit")) or _credit(release.get("artist-credit")),
        "title": track["title"], "album": release.get("title") or "",
        "album_artist": _credit(release.get("artist-credit")), "date": date, "year": date[:4],
        "track": str(track["position"]), "track_label": track["number"], "tracks": track["medium_tracks"],
        "disc": track["disc"], "discs": discs,
        "type": " + ".join([group.get("primary-type") or "Other", *(group.get("secondary-types") or [])]),
        "status": release.get("status") or "", "country": release.get("country") or "", "live": False,
        "length": round(track["length"], 1), "artists": artists,
    }
