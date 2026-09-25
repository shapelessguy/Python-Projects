"""Music staging — recognising songs and filing them the way Plex expects.

The music counterpart of movie_prep's identify-and-remux: a music pair
(an entry of secrets.json's `staging` with "type": "music") is an inbox of songs named any old way and
an output they are filed into as

    Album Artist/Album/NN - Title.ext      (D-NN - Title.ext on multi-disc)

with their tags filled in, and the album's front cover saved beside them as
cover.jpg, which Plex reads as the album's art.

Recognition is by artist and title — from the file's tags when it has them,
otherwise from an "Artist - Title" file name — looked up in MusicBrainz.
Knowing the song is the easy part; the same recording sits on the studio
album, the single, a dozen compilations and a live bootleg, and Plex files
by album. So every release it is on comes back as an option, ranked:

    studio album  <  single / EP  <  compilation, live, soundtrack …

by the song's own artist before "Various Artists", earliest first. The first
is the proposal; the panel lists the rest to switch to before filing.

MusicBrainz allows one request a second per client and asks each to say who
it is (the User-Agent). Its answers are kept (SEARCHES), so no search is ever
sent twice — not even after the rules below change.
"""
import json
import re
import shutil
import threading
import time
from pathlib import Path

import mutagen
import requests

from api.config import API_DATA_DIR, MUSICBRAINZ_CONTACT
from api.services import movie_prep, music_match, plex
from api.services.movie_prep import PrepError

MB_URL = "https://musicbrainz.org/ws/2/recording"
COVER_URL = "https://coverartarchive.org/release-group/{}/front-500"
USER_AGENT = "CyanHouse/1.0 ( {} )".format(
    MUSICBRAINZ_CONTACT or "https://github.com/shapelessguy/Python-Projects")
CACHE_DIR = API_DATA_DIR / "music"
# v3: options carry the recording's length and credited artists (which the
# automatic filing checks), and "not found" is only cached after the fuzzy
# search has had its go too.
# v4: "track" is the position on the disc, not the printed number (see
# _options).
# v5: one option per (album, recording), not per album — see _options.
# MusicBrainz's answers, as it gave them, by the exact search sent: what
# the rules make of them is worked out again every time, so changing the
# rules never costs a second question.
SEARCHES = CACHE_DIR / "searches.sqlite"
COVERS = CACHE_DIR / "covers"
# How many albums the panel is offered for one song…
MAX_OPTIONS = 20
# …and how many (album, recording) pairs are kept for deciding.
MAX_CANDIDATES = 80

_mb_lock = threading.Lock()
_mb_last = 0.0
_db_lock = threading.Lock()
_db = None


# ── what the song says it is ─────────────────────────────────────────────
_TRACKNO = re.compile(r"^\s*(?:\d{1,3}|[A-D]\d{1,2})\s*[-._)]\s*")


def read_song(path: Path) -> dict:
    """Artist and title for a file: its tags when it has both, otherwise
    its name — "Artist - Title", with any leading track number dropped."""
    artist = title = album = ""
    try:
        tags = mutagen.File(path, easy=True)
        if tags is not None and tags.tags is not None:
            first = lambda k: (tags.get(k) or [""])[0].strip()  # noqa: E731
            artist, title, album = first("artist"), first("title"), first("album")
    except Exception:
        pass
    if artist and title:
        return {"artist": artist, "title": title, "album": album, "from": "tags"}
    stem = path.stem
    if " - " in _TRACKNO.sub("", stem):   # a track number, not the artist ("883 - …")
        stem = _TRACKNO.sub("", stem)
    if " - " in stem:
        a, t = stem.split(" - ", 1)
        return {"artist": a.strip(), "title": t.strip(), "album": album, "from": "name"}
    return {"artist": artist, "title": title or stem.strip(), "album": album, "from": "name"}


def song_variants(path: Path) -> list[dict]:
    """Every reading of what the song is: its name ("Artist - Title") first,
    then its tags when they say something else. Names are usually the
    cleaner of the two — tags from a download say "Greenday", or stop
    mid-word ("… (Radio Ed") — but either may be the one that is right, so
    both are searched and either may make the match."""
    tagged = read_song(path)
    readings = name_readings(path.stem)
    out: list[dict] = readings[:1]
    if tagged["from"] == "tags" or not out:
        out.append(tagged)
    out += readings[1:]
    seen, unique = set(), []
    for v in out:
        key = (_artist_key(v["artist"]), _title_key(v["title"]))
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


MAX_READINGS = 6


def name_readings(stem: str) -> list[dict]:
    """The ways a file name can be read as artist and title, likeliest
    first. "Artist - Title" is the usual shape, but downloads also come as
    "Title - Artist", or with extra parts: "Cartoni animati - Walt Disney -
    Gli aristogatti - Sigla italiana". So: first part as the artist, then
    the last part, then every two neighbouring parts either way round."""
    # A dash with a space on at least one side: "Nickelback- Photograph" and
    # "Eros Ramazzotti -Ti sposerò" are separators, "Jay-Z" is not.
    split = lambda s: [p.strip() for p in re.split(r"\s+[-–—]\s*|\s*[-–—]\s+", s) if p.strip()]  # noqa: E731
    stem = stem.replace("_", " ").strip()
    parts = split(stem)
    # A leading number is a track number ("03 - Nirvana - Breed") only if an
    # "Artist - Title" is still left after it; otherwise it is the artist
    # ("883 - Come mai").
    bare = _TRACKNO.sub("", stem).strip()
    if bare != stem and len(split(bare)) >= 2:
        parts = split(bare)
    if len(parts) < 2:
        return []
    pairs = [(parts[0], " - ".join(parts[1:])), (parts[-1], " - ".join(parts[:-1]))]
    if len(parts) > 2:
        pairs.append((parts[0], parts[-1]))
        for i in range(len(parts) - 1):
            pairs += [(parts[i], parts[i + 1]), (parts[i + 1], parts[i])]
    out, seen = [], set()
    for artist, title in pairs:
        if (artist, title) not in seen:
            seen.add((artist, title))
            out.append({"artist": artist, "title": title, "album": "", "from": "name"})
    return out[:MAX_READINGS]


def albums_only(options: list[dict]) -> list[dict]:
    """One option per album, the best-ranked recording of each — the list
    a person picks from."""
    out, seen = [], set()
    for o in options:
        key = o.get("release_group_id") or o.get("release_id")
        if key not in seen:
            seen.add(key)
            out.append(o)
    return out[:MAX_OPTIONS]


def lookup_all(variants: list[dict]) -> list[dict]:
    """The options for every reading of a song, the first reading's first."""
    out, seen = [], set()
    for v in variants:
        if not v.get("title"):
            continue
        for o in lookup(v["artist"], v["title"]):
            key = (o.get("release_group_id") or o.get("release_id"), o.get("recording_id"))
            if key not in seen:
                seen.add(key)
                out.append(o)
    return out


# ── MusicBrainz ──────────────────────────────────────────────────────────
def _lucene(s: str) -> str:
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", s)


def _searches():
    global _db
    if _db is None:
        import sqlite3
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(SEARCHES, check_same_thread=False)
        _db.execute("CREATE TABLE IF NOT EXISTS search (query TEXT PRIMARY KEY, answer TEXT, at REAL)")
    return _db


def _mb_search(query: str, limit: int = 100) -> list[dict]:
    """A recording search, answered from the cache when it has been sent
    before; otherwise asked (_mb_ask) and kept. The same search asked for a
    different number of results is a different search."""
    key = query if limit == 100 else f"{limit}|{query}"
    with _db_lock:
        row = _searches().execute("SELECT answer FROM search WHERE query = ?", (key,)).fetchone()
    if row:
        return json.loads(row[0])
    answer = _mb_ask(query, limit)
    with _db_lock:
        _searches().execute("INSERT OR REPLACE INTO search VALUES (?, ?, ?)",
                            (key, json.dumps(answer, ensure_ascii=False), time.time()))
        _searches().commit()
    return answer


def _mb_ask(query: str, limit: int = 100) -> list[dict]:
    """One recording search, spaced a second from the last one.

    MusicBrainz counts its limit per IP address, and this machine's traffic
    leaves through NordVPN's shared exit — other people's requests count
    against it too. So a 503 ("slow down") is retried, waiting longer each
    time, before it is given up on."""
    global _mb_last
    for attempt in range(5):
        with _mb_lock:
            wait = 1.1 - (time.time() - _mb_last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = requests.get(MB_URL, params={"query": query, "fmt": "json", "limit": limit},
                                 headers={"User-Agent": USER_AGENT}, timeout=20)
            finally:
                _mb_last = time.time()
            if r.status_code != 503:
                break
            time.sleep(2 * (attempt + 1))
    if r.status_code == 503:
        raise PrepError("MusicBrainz is busy — try again in a moment", 503)
    r.raise_for_status()
    return r.json().get("recordings") or []


def mb_get(path: str, params: dict) -> dict:
    """Any MusicBrainz web-service call (`path` under /ws/2/, e.g. "release"
    or "release/<id>"), cached like the searches — keyed by the call itself
    — and spaced like them. None-free answers only: a 404 is kept as {}."""
    key = "get|" + path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    with _db_lock:
        row = _searches().execute("SELECT answer FROM search WHERE query = ?", (key,)).fetchone()
    if row:
        return json.loads(row[0])
    global _mb_last
    answer: dict = {}
    for attempt in range(5):
        with _mb_lock:
            wait = 1.1 - (time.time() - _mb_last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = requests.get(f"https://musicbrainz.org/ws/2/{path}", params={**params, "fmt": "json"},
                                 headers={"User-Agent": USER_AGENT}, timeout=20)
            finally:
                _mb_last = time.time()
        if r.status_code == 503:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            answer = r.json()
        elif r.status_code != 404:
            r.raise_for_status()
        break
    else:
        raise PrepError("MusicBrainz is busy — try again in a moment", 503)
    with _db_lock:
        _searches().execute("INSERT OR REPLACE INTO search VALUES (?, ?, ?)",
                            (key, json.dumps(answer, ensure_ascii=False), time.time()))
        _searches().commit()
    return answer


def _credit(credits: list | None) -> str:
    return "".join(c.get("name", "") + c.get("joinphrase", "") for c in credits or []).strip()


def _options(recordings: list[dict], artist: str) -> list[dict]:
    """Every release of these recordings as a filing option, best first:
    one per album *and recording* (the album's earliest release of it). Per
    recording because a single often carries two — the album version and
    the radio edit — and only the one the file's length matches is right.
    The panel shows one line per album (see albums_only)."""
    want = artist.casefold()
    by_group: dict[str, dict] = {}
    for rec in recordings:
        if rec.get("video"):
            continue
        rec_artist = _credit(rec.get("artist-credit"))
        rec_artists = [c.get("name", "") for c in rec.get("artist-credit") or []]
        length = round((rec.get("length") or 0) / 1000, 1)
        live = "live" in (rec.get("disambiguation") or "").lower()
        for rel in rec.get("releases") or []:
            group = rel.get("release-group") or {}
            primary = group.get("primary-type") or ""
            secondary = group.get("secondary-types") or []
            media = rel.get("media") or []
            medium = media[0] if media else {}
            track = (medium.get("track") or [{}])[0]
            album_artist = _credit(rel.get("artist-credit")) or rec_artist
            date = rel.get("date") or ""
            kind = (0 if primary == "Album" and not secondary
                    else 1 if primary in ("Single", "EP") and not secondary
                    else 2)
            rank = (
                rel.get("status") != "Official",
                kind,
                live or "Live" in secondary,
                album_artist.casefold() != want,
                date or "9999",
            )
            opt = {
                "recording_id": rec.get("id"),
                "release_id": rel.get("id"),
                "release_group_id": group.get("id"),
                "artist": rec_artist,
                "title": rec.get("title") or "",
                "album": rel.get("title") or group.get("title") or "",
                "album_artist": album_artist,
                "date": date,
                "year": date[:4],
                # The position on the disc, counted: a vinyl release prints
                # "B1" for the first song of side B, which as a file number
                # would be 01. The printed one is kept for showing.
                "track": (str(medium["track-offset"] + 1) if medium.get("track-offset") is not None
                          else re.sub(r"\D", "", str(track.get("number") or ""))),
                "track_label": str(track.get("number") or ""),
                "tracks": medium.get("track-count") or 0,
                "disc": medium.get("position") or 1,
                # A search only returns the disc the song is on; that there
                # are others shows in the release having more tracks than
                # it, or in the song being on a disc after the first.
                "discs": rel.get("medium-count") or (
                    2 if (medium.get("position") or 1) > 1
                    or (rel.get("track-count") or 0) > (medium.get("track-count") or 0) else 1),
                "type": " + ".join([primary or "Other", *secondary]),
                "status": rel.get("status") or "",
                "country": rel.get("country") or "",
                "live": live,
                "length": length,
                "artists": rec_artists,
                "_rank": rank,
            }
            key = (group.get("id") or rel.get("id"), rec.get("id"))
            if key not in by_group or rank < by_group[key]["_rank"]:
                by_group[key] = opt
    out = sorted(by_group.values(), key=lambda o: o["_rank"])[:MAX_CANDIDATES]
    for o in out:
        o.pop("_rank")
    return out


def lookup(artist: str, title: str) -> list[dict]:
    """The albums this song can be filed under, best first."""
    artist, title = artist.strip(), title.strip()
    if not title:
        raise PrepError("no title to look up", 400)
    # The main artist only: "Beyoncé & Jay-Z" is credited as Beyoncé feat.
    # JAY-Z, and a quoted "Beyoncé & Jay-Z" matches neither spelling.
    main = _FEAT.sub("", artist).strip() or artist
    base = f'recording:"{_lucene(title)}"' + (f' AND artist:"{_lucene(main)}"' if main else "")
    # One question per reading — MusicBrainz answers one a second, so every
    # extra one is a second per song. Official releases only, which keeps a
    # famous song's hundreds of live bootlegs out; a hundred results (the
    # most it gives) is every recording of all but the most covered songs.
    options = _options(_mb_search(base + " AND status:official"), main)
    # Still nothing: the quoted names must match exactly, and a download's
    # spelling often does not ("Bob Sinclair" for Bob Sinclar, "andar" for
    # "andare"). The same search word by word, each allowed a typo.
    by_artist = any(_alike(_artist_key(main), _artist_key(a))
                    for o in options for a in o.get("artists") or [o.get("artist", "")])
    if not by_artist and main:
        fuzzy = " AND ".join(
            f"{field}:({' '.join(w + '~' if len(w) > 3 else w for w in re.findall(r'[^\W_]+', text))})"
            for field, text in (("recording", title), ("artist", main)) if re.search(r"\w", text))
        options = _options(_mb_search(fuzzy + " AND status:official"), main) + options
    return options


def cover(release_group_id: str) -> bytes | None:
    """An album's front cover from the Cover Art Archive, cached; None when
    it has none."""
    if not re.fullmatch(r"[0-9a-f-]{36}", release_group_id or ""):
        raise PrepError("bad release group id", 400)
    COVERS.mkdir(parents=True, exist_ok=True)
    hit = COVERS / f"{release_group_id}.jpg"
    miss = COVERS / f"{release_group_id}.none"
    if hit.exists():
        return hit.read_bytes()
    if miss.exists() and time.time() - miss.stat().st_mtime < 7 * 86400:
        return None
    r = requests.get(COVER_URL.format(release_group_id), timeout=20,
                     headers={"User-Agent": USER_AGENT})
    if r.status_code == 404:
        miss.touch()
        return None
    r.raise_for_status()
    hit.write_bytes(r.content)
    return r.content


# ── in the inbox ─────────────────────────────────────────────────────────
def _music_inbox(area_name: str) -> tuple[Path, Path]:
    cfg = movie_prep.areas().get(area_name)
    if not cfg or cfg.get("type") != "music" or not cfg.get("inbox"):
        raise PrepError(f"{area_name!r} is not a music inbox", 400)
    return movie_prep.area(area_name)


def identify(area_name: str, rel: str, artist: str | None = None,
             title: str | None = None) -> dict:
    """What a song in the inbox is and where it would go. `artist`/`title`
    replace what was read from the file, to search again by hand."""
    inbox, output = _music_inbox(area_name)
    path = movie_prep.resolve_in_area(area_name, rel)
    if movie_prep.file_kind(path) != "audio":
        raise PrepError("not a song", 400)
    if artist is not None or title is not None:
        variants = [{"artist": (artist or "").strip(), "title": (title or "").strip(),
                     "album": "", "from": "you"}]
    else:
        variants = song_variants(path)
    song = variants[0]
    # Copies: the target depends on this file's extension, and the cached
    # lookup is shared by every file of the same song.
    # The first few readings only: a person is waiting on this one.
    options = [dict(o) for o in albums_only(lookup_all(variants[:3]))]
    for o in options:
        o["target"] = str(_target_in(output, path, o).relative_to(output)) if o.get("album") else ""
    review = auto_status(area_name).get("review", {}).get(rel)
    return {"path": rel, "song": song, "variants": variants, "options": options, "review": review}


_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _safe(name: str) -> str:
    """A name that is valid on this NTFS drive and on Windows."""
    name = _UNSAFE.sub("_", name).strip().rstrip(". ")
    return name[:180] or "_"


def _target_in(output: Path, path: Path, opt: dict) -> Path:
    number = re.sub(r"\D", "", str(opt.get("track") or ""))
    lead = f"{int(number):02d}" if number else ""
    if lead and int(opt.get("discs") or 1) > 1:
        lead = f"{opt.get('disc') or 1}-{lead}"
    name = f"{lead} - {opt['title']}" if lead else opt["title"]
    return (output / _safe(opt.get("album_artist") or opt.get("artist") or "Unknown Artist")
            / _safe(opt.get("album") or "Unknown Album")
            / (_safe(name) + path.suffix.lower()))


def _write_tags(path: Path, opt: dict) -> bool:
    """Fill the file's tags in place. False for a format that has none (a
    .wav), which is filed all the same."""
    audio = mutagen.File(path, easy=True)
    if audio is None:
        return False
    if audio.tags is None:
        try:
            audio.add_tags()
        except Exception:
            return False
    values = {
        "artist": opt.get("artist"),
        "title": opt.get("title"),
        "album": opt.get("album"),
        "albumartist": opt.get("album_artist"),
        "date": opt.get("date") or opt.get("year"),
        "tracknumber": (f"{opt['track']}/{opt['tracks']}" if opt.get("track") and opt.get("tracks")
                        else opt.get("track")),
        "discnumber": (f"{opt.get('disc') or 1}/{opt['discs']}" if opt.get("discs") else None),
        "musicbrainz_trackid": opt.get("recording_id"),
        "musicbrainz_albumid": opt.get("release_id"),
        "musicbrainz_releasegroupid": opt.get("release_group_id"),
    }
    for key, value in values.items():
        if not value:
            continue
        try:
            audio[key] = str(value)
        except (KeyError, ValueError, TypeError):
            pass  # a key this format's tag set has no room for
    audio.save()
    return True


def file_song(area_name: str, rel: str, opt: dict) -> dict:
    """Tag a song from the inbox with `opt` (one of identify's options) and
    move it into the output as Album Artist/Album/NN - Title.ext."""
    inbox, output = _music_inbox(area_name)
    path = movie_prep.resolve_in_area(area_name, rel)
    if movie_prep.file_kind(path) != "audio":
        raise PrepError("not a song", 400)
    for field in ("title", "album"):
        if not str(opt.get(field) or "").strip():
            raise PrepError(f"the choice has no {field}", 400)
    dest = _target_in(output, path, opt)
    if dest.exists():
        raise PrepError(f"{dest.relative_to(output)} is already in the library", 409)
    tagged = _write_tags(path, opt)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dest))

    # The album's cover, once per album folder. Never fatal: a song filed
    # without a cover is still filed.
    art = dest.parent / "cover.jpg"
    if not art.exists() and opt.get("release_group_id"):
        try:
            data = cover(opt["release_group_id"])
            if data:
                art.write_bytes(data)
        except Exception as e:
            print(f"music_prep: no cover for {opt.get('album')!r} ({e})")

    # Folders the song leaves empty behind it in the inbox go too.
    folder = path.parent
    root = inbox.resolve()
    while folder.resolve() != root and root in folder.resolve().parents:
        try:
            folder.rmdir()
        except OSError:
            break
        folder = folder.parent

    movie_prep._bump()
    plex.notify(dest)
    return {"path": rel, "new_path": str(dest.relative_to(output)), "tagged": tagged,
            "cover": art.exists()}


# ── filing by itself ─────────────────────────────────────────────────────
# A worker goes through every music inbox and files each song it is sure of
# — so a thousand songs are not a thousand clicks. What "sure" means is
# music_match's decide(): the rules measured against a hand-checked list of
# songs (scripts/music_match), tuned to file none wrongly.
#
# Everything else stays in the inbox, with the reason it was not filed, for
# the panel to show. A song is looked at once; it is looked at again only if
# the file changes (size or time) or the rules do (RULES_VERSION) — and
# MusicBrainz is not asked again either (SEARCHES).
AUTO_STATE = CACHE_DIR / "auto.json"
# Raised whenever music_match's rules or searches change: a verdict reached
# under older rules is judged again rather than kept as long as the file is.
RULES_VERSION = 12   # 11: whole albums first (music_albums); 12: all releases, and a fuzzy second try
AUTO_PASS_SECONDS = 30
# A file changed this recently may still be arriving (a copy over the
# network rather than an upload, which only appears once it is whole).
AUTO_SETTLE_SECONDS = 20
# How alike two names must be (difflib ratio, once tidied) to count as the
# same, for the panel's own lookup (lookup, song_variants).
NAME_ALIKE = 0.85

_auto_lock = threading.Lock()
_auto: dict = {"current": None, "pending": {}, "filed": {}, "started": False}
_auto_state: dict | None = None

_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*\b(feat|ft|featuring|remaster(ed)?|official|video|audio|lyrics?|"
    r"hd|hq|explicit|clean|mono|stereo|bonus|album version|single version)\b[^\)\]]*[\)\]]",
    re.I)
_TAIL = re.compile(r"\s+-\s+.*\b(remaster(ed)?|version|edit|mono|stereo)\b.*$", re.I)
_FEAT = re.compile(r"\s+(feat\.?|ft\.?|featuring|&|and|x|with|,)\s+.*$", re.I)


def _plain(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = s.replace("&", " and ")
    return re.sub(r"[^0-9a-z]+", "", s)


def _title_key(s: str) -> str:
    return _plain(_TAIL.sub("", _NOISE.sub("", s or "")))


def _artist_key(s: str) -> str:
    """The main artist: what comes before any "feat.", "&", "," …, without
    a leading "The" ("Beatles" is The Beatles)."""
    return _plain(re.sub(r"^\s*the\s+", "", _FEAT.sub("", s or ""), flags=re.I))


def _alike(a: str, b: str) -> bool:
    from difflib import SequenceMatcher
    return a == b or (bool(a) and bool(b) and SequenceMatcher(None, a, b).ratio() >= NAME_ALIKE)


def _duration(path: Path) -> float:
    try:
        info = mutagen.File(path)
        return float(info.info.length) if info is not None else 0.0
    except Exception:
        return 0.0


def auto_match(path: Path) -> tuple[dict | None, str]:
    """Recognise a song from its file name and length (music_match): send
    the searches its rules use, and file what decide() is sure of. Returns
    the option to file under, or None and why not."""
    name = music_match.split_name(path.name)
    cands: list = []
    for key in music_match.PARAMS.strategies:
        query = music_match.STRATEGIES[key](name)
        if query:
            # As many results as the rules were measured on (RESULTS).
            cands += music_match.cands_from_answer(key, _mb_search(query, music_match.RESULTS))
    chosen, why = music_match.decide(name["parts"], _duration(path), cands, lookup=_mb_lookup)
    return (_option(chosen) if chosen else None), why


def _mb_lookup(recording_id: str) -> dict:
    """A recording's full entry — every release it is on — cached like the
    searches (as "lookup|<id>"), so it too is asked only once."""
    key = f"lookup|{recording_id}"
    with _db_lock:
        row = _searches().execute("SELECT answer FROM search WHERE query = ?", (key,)).fetchone()
    if row:
        return json.loads(row[0])
    global _mb_last
    answer: dict = {}
    for attempt in range(5):
        with _mb_lock:
            wait = 1.1 - (time.time() - _mb_last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = requests.get(f"https://musicbrainz.org/ws/2/recording/{recording_id}",
                                 params={"inc": "releases+release-groups+media+artist-credits", "fmt": "json"},
                                 headers={"User-Agent": USER_AGENT}, timeout=20)
            finally:
                _mb_last = time.time()
        if r.status_code == 503:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            answer = r.json()
        break
    else:
        raise PrepError("MusicBrainz is busy — try again in a moment", 503)
    with _db_lock:
        _searches().execute("INSERT OR REPLACE INTO search VALUES (?, ?, ?)",
                            (key, json.dumps(answer, ensure_ascii=False), time.time()))
        _searches().commit()
    return answer


def _option(c) -> dict:
    """A music_match candidate as the option file_song() files under."""
    number = str(c.track_position or re.sub(r"\D", "", c.track_number or ""))
    multi = (c.medium_position or 1) > 1 or (c.release_tracks or 0) > (c.medium_tracks or 0)
    return {
        "recording_id": c.recording_id, "release_id": c.release_id,
        "release_group_id": c.release_group_id, "artist": c.artist, "title": c.title,
        "album": c.release, "album_artist": c.album_artist, "date": c.date, "year": c.date[:4],
        "track": number, "track_label": c.track_number, "tracks": c.medium_tracks or 0,
        "disc": c.medium_position or 1, "discs": 2 if multi else 1,
        "type": " + ".join([c.primary or "Other", *c.secondary]), "status": c.status,
        "country": c.country, "live": False, "length": c.length or 0, "artists": c.artists,
    }


def _load_auto_state() -> dict:
    global _auto_state
    if _auto_state is None:
        try:
            _auto_state = json.loads(AUTO_STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _auto_state = {}
    return _auto_state


def _save_auto_state() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = AUTO_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_auto_state or {}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(AUTO_STATE)


def auto_status(area_name: str) -> dict:
    """What the worker is doing in one inbox: the song it is on, how many
    are waiting, and the ones left for a person, with the reason."""
    with _auto_lock:
        reviews = (_load_auto_state().get(area_name) or {})
        current = _auto["current"]
        return {
            "enabled": _auto_enabled(area_name),
            "current": current[1] if current and current[0] == area_name else None,
            "pending": _auto["pending"].get(area_name, 0),
            "filed": _auto["filed"].get(area_name, 0),
            "review": {rel: v["reason"] for rel, v in reviews.items()},
        }


def _auto_enabled(area_name: str) -> bool:
    from api.config import MUSIC_STAGING
    cfg = (MUSIC_STAGING or {}).get(area_name) or {}
    return cfg.get("auto", True) is not False


def _songs(inbox: Path) -> list[Path]:
    # A set: the ntfs3 driver repeats names in a folder being written to
    # (UNIQUE_NAMES in movie_prep.py).
    out = []
    for p in set(inbox.rglob("*")):
        rel = p.relative_to(inbox)
        if any(part.startswith(".") for part in rel.parts) or movie_prep.TRASH_DIR in rel.parts:
            continue
        if p.is_file() and movie_prep.file_kind(p) == "audio":
            out.append(p)
    return sorted(out)


def _album_pass(name: str, inbox: Path, todo: list) -> set[str]:
    """Recognise and file the albums among `todo` (the songs due a look):
    the rel paths of the songs filed. An album is looked at once, and again
    only when one of its songs or the rules change."""
    from api.services import music_albums
    by_rel = {rel: (p, sig) for p, rel, sig in todo}
    groups = music_albums.albums(inbox, [p for p, _, _ in todo])
    with _auto_lock:
        seen = _load_auto_state().setdefault(f"{name}|albums", {})
    filed: set[str] = set()
    for album_rel, files in groups.items():
        rels = [str(p.relative_to(inbox)) for p, _ in files]
        sig = "|".join(sorted(f"{r}:{by_rel[r][1]}" for r in rels))
        if (seen.get(album_rel) or {}).get("sig") == sig and seen[album_rel].get("rules") == RULES_VERSION:
            continue
        with _auto_lock:
            _auto["current"] = (name, album_rel + "/")
        release, pairs, why = music_albums.match(music_albums.hints(album_rel, files))
        with _auto_lock:
            seen[album_rel] = {"sig": sig, "rules": RULES_VERSION, "reason": why, "at": time.time()}
            _save_auto_state()
        if not release:
            continue
        _, output = _music_inbox(name)
        for song, track in pairs:
            rel = str(song["path"].relative_to(inbox))
            opt = music_albums.option(release, track)
            opt["target"] = str(_target_in(output, song["path"], opt).relative_to(output))
            try:
                file_song(name, rel, opt)
                filed.add(rel)
                with _auto_lock:
                    _auto["filed"][name] = _auto["filed"].get(name, 0) + 1
                print(f"music_prep: filed {rel} -> {opt['target']} (album)")
            except PrepError as e:
                with _auto_lock:
                    _load_auto_state().setdefault(name, {})[rel] = {
                        "sig": by_rel[rel][1], "reason": str(e), "at": time.time(), "rules": RULES_VERSION}
                filed.add(rel)   # judged: not for the song-by-song pass either
    return filed


def _auto_pass() -> None:
    for name, cfg in movie_prep.areas().items():
        if cfg.get("type") != "music" or not cfg.get("ready") or not _auto_enabled(name):
            continue
        inbox = Path(cfg["inbox"])
        now = time.time()
        with _auto_lock:
            known = _load_auto_state().setdefault(name, {})
        todo = []
        present = set()
        for p in _songs(inbox):
            rel = str(p.relative_to(inbox))
            present.add(rel)
            try:
                st = p.stat()
            except OSError:
                continue
            if now - st.st_mtime < AUTO_SETTLE_SECONDS:
                continue
            sig = f"{st.st_size}:{int(st.st_mtime)}"
            seen = known.get(rel) or {}
            if seen.get("sig") == sig and seen.get("rules") == RULES_VERSION:
                continue
            # Songs never judged come first; a verdict to be redone under
            # newer rules (cheap: MusicBrainz's answers are kept) waits.
            todo.append((1 if seen else 0, p, rel, sig))
        todo = [t[1:] for t in sorted(todo, key=lambda t: t[0])]
        # Whole albums first (music_albums): a folder of songs is recognised
        # as the release it is, and filed together; what it could not place
        # goes on to the song-by-song matching below.
        try:
            done = _album_pass(name, inbox, todo)
            todo = [t for t in todo if t[1] not in done]
        except Exception as e:
            print(f"music_prep: album pass: {e.__class__.__name__}: {e}")
        with _auto_lock:
            # Verdicts on songs no longer here (filed by hand, moved, deleted).
            for rel in [r for r in known if r not in present]:
                known.pop(rel)
            _auto["pending"][name] = len(todo)
            _save_auto_state()
        for i, (p, rel, sig) in enumerate(todo):
            with _auto_lock:
                _auto["current"] = (name, rel)
                _auto["pending"][name] = len(todo) - i
            try:
                if not p.exists():
                    continue
                chosen, why = auto_match(p)
                if chosen:
                    inbox_root, output = _music_inbox(name)
                    chosen = {**chosen, "target": str(_target_in(output, p, chosen).relative_to(output))}
                    file_song(name, rel, chosen)
                    with _auto_lock:
                        known.pop(rel, None)
                        _auto["filed"][name] = _auto["filed"].get(name, 0) + 1
                    print(f"music_prep: filed {rel} -> {chosen['target']}")
                else:
                    with _auto_lock:
                        known[rel] = {"sig": sig, "reason": why, "at": time.time(),
                                      "rules": RULES_VERSION}
            except PrepError as e:
                # Busy MusicBrainz: leave it unjudged, for the next pass.
                if e.status_code != 503:
                    with _auto_lock:
                        known[rel] = {"sig": sig, "reason": str(e), "at": time.time(),
                                      "rules": RULES_VERSION}
            except Exception as e:
                print(f"music_prep: {rel}: {e.__class__.__name__}: {e}")
            finally:
                with _auto_lock:
                    _save_auto_state()
        with _auto_lock:
            _auto["current"] = None
            _auto["pending"][name] = 0
        # New verdicts are news to the panel even when nothing moved (a
        # filed song has already said so itself).
        if todo:
            movie_prep._bump()


def _auto_loop() -> None:
    while True:
        try:
            _auto_pass()
        except Exception as e:
            print(f"music_prep: auto pass failed: {e.__class__.__name__}: {e}")
        time.sleep(AUTO_PASS_SECONDS)


def start_auto() -> None:
    with _auto_lock:
        if _auto["started"]:
            return
        _auto["started"] = True
    threading.Thread(target=_auto_loop, name="music-auto", daemon=True).start()
