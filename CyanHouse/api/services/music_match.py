"""Recognising a song from its file name — the rules, and only the rules.

One place for them, used by both sides:

  - the music inbox's automatic filing (music_prep.auto_match), which asks
    MusicBrainz the searches below and files what decide() is sure of;
  - scripts/music_match/, which measures them offline against a hand-checked
    list of songs (evaluate.py) using every answer MusicBrainz ever gave to
    these searches (harvest.py).

A change here is a change to both, so what the evaluation says is what the
inbox does. The rules, and why, are measured in scripts/music_match — see
PARAMS for the current choice.

How a song is recognised:

  1. The name is split on " - " (split_name) and read every sensible way
     (readings): "Artist - Title", "Title - Artist", neighbouring parts.
  2. A few searches are sent (STRATEGIES, the ones PARAMS names), each a
     different way of turning the name into a MusicBrainz query.
  3. Every recording they return, on every release it is on, is a candidate
     (Cand). decide() keeps the ones whose title and artist fit one reading
     of the name and whose length fits the file's, drops other takes
     (remixes, live, karaoke…) the name does not ask for, and — if any are
     left — picks the plainest title on the artist's own album.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# ── tidying names ────────────────────────────────────────────────────────
_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*\b(feat|ft|featuring|remaster(ed)?|official|video|audio|lyrics?|"
    r"hd|hq|explicit|clean|mono|stereo|bonus|album version|single version)\b[^\)\]]*[\)\]]", re.I)
_TAIL = re.compile(r"\s+-\s+.*\b(remaster(ed)?|version|edit|mono|stereo)\b.*$", re.I)
_SPLIT_ARTISTS = re.compile(r"\s+(?:feat\.?|ft\.?|featuring|&|and|x|with|vs\.?|con|e)\s+|\s*,\s*|\s*&\s*", re.I)
# Takes the remix fallback may use: the same performance, remixed or edited…
_MIXES = {"remix", "mix", "rmx", "dub", "extended", "club", "edit", "vip", "bootleg", "mashup"}
# …and takes that are another performance, used only when the name asks.
_OTHER_TAKE = {"remix", "mix", "rmx", "dub", "instrumental", "karaoke", "acoustic", "live",
               "unplugged", "demo", "cover", "extended", "club", "bootleg", "mashup", "vip",
               "reprise", "orchestral", "piano", "a cappella", "cappella"}
_PART = re.compile(r"\b(?:part|pt|pts)\.?\s*([0-9]+|[ivx]+)\b", re.I)


def plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold().replace("&", " and ")
    return re.sub(r"[^0-9a-z]+", "", s)


def title_key(s: str) -> str:
    return plain(_TAIL.sub("", _NOISE.sub("", s or "")))


def loose_title(s: str) -> str:
    """The title with anything in brackets gone, even a bracket cut off."""
    return plain(_TAIL.sub("", re.sub(r"\s*[\(\[][^\)\]]*([\)\]]|$)", "", s or "")))


def artist_keys(s: str) -> set[str]:
    """Every artist a credit names, each tidied, "The" dropped."""
    out = set()
    for a in _SPLIT_ARTISTS.split(s or ""):
        k = plain(re.sub(r"^\s*the\s+", "", a, flags=re.I))
        if k:
            out.add(k)
    return out


def alike(a: str, b: str, ratio: float) -> bool:
    return a == b or (bool(a) and bool(b) and SequenceMatcher(None, a, b).ratio() >= ratio)


def part_of(title: str) -> str:
    """The "Part 2" / "Pt. II" a title names, or "" — another half of the
    piece, whatever else the title shares."""
    m = _PART.search(title or "")
    return m.group(1).lower() if m else ""


def version_words(title: str) -> set[str]:
    """What a title says about which version it is: the words in its
    brackets and after a " - "."""
    bits = re.findall(r"[\(\[]([^\)\]]*)(?:[\)\]]|$)", title or "")
    parts = re.split(r"\s+-\s+", title or "", maxsplit=1)
    if len(parts) > 1:
        bits.append(parts[1])
    text = unicodedata.normalize("NFKD", " ".join(bits)).casefold()
    return set(re.findall(r"[a-z]+", text))


# ── reading a name ───────────────────────────────────────────────────────
def _parts(stem: str) -> list[str]:
    # A dash with a space on at least one side: "Nickelback- Photograph" and
    # "Eros Ramazzotti -Ti sposerò" are separators, "Jay-Z" is not.
    return [p.strip() for p in re.split(r"\s+[-–—]\s*|\s*[-–—]\s+", stem) if p.strip()]


def split_name(name: str) -> dict:
    """A file name as {"stem", "parts"}."""
    stem = re.sub(r"\.(mp3|flac|m4a|aac|ogg|oga|opus|wav)$", "", name, flags=re.I).strip()
    stem = stem.replace("_", " ")
    parts = _parts(stem)
    # A leading number is a track number ("03 - Nirvana - Breed") only if an
    # "Artist - Title" is still left after it; otherwise it is the artist
    # ("883 - Come mai").
    bare = re.sub(r"^\s*\d{1,3}\s*[-._)]\s*", "", stem)
    if bare != stem and len(_parts(bare)) >= 2:
        stem, parts = bare, _parts(bare)
    return {"stem": stem, "parts": parts}


def readings(parts: list) -> list[tuple[str, str]]:
    """(artist, title) readings of a name's parts, likeliest first."""
    if len(parts) < 2:
        return [("", parts[0])] if parts else []
    out = [(parts[0], " - ".join(parts[1:])), (parts[-1], " - ".join(parts[:-1]))]
    if len(parts) > 2:
        out.append((parts[0], parts[-1]))
        for i in range(len(parts) - 1):
            out += [(parts[i], parts[i + 1]), (parts[i + 1], parts[i])]
    return out


# ── the searches ─────────────────────────────────────────────────────────
def lucene(s: str) -> str:
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", s)


def clean_title(t: str) -> str:
    """Brackets, "feat. …" and a " - …" tail gone."""
    t = re.sub(r"\s*[\(\[][^\)\]]*([\)\]]|$)", "", t)
    t = re.sub(r"\s+(feat\.?|ft\.?|featuring)\s+.*$", "", t, flags=re.I)
    return t.split(" - ")[0].strip() or t


def main_artist(a: str) -> str:
    """Before any "feat.", "&", ",", "vs", "and", "x", "with"."""
    return re.sub(r"\s+(feat\.?|ft\.?|featuring|&|and|x|with|vs\.?|,)\s+.*$", "", a, flags=re.I) \
        .split(",")[0].split("&")[0].strip() or a


def _words(s: str) -> list[str]:
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", s))


def _q_words(field_: str, s: str, fuzzy: bool = False) -> str | None:
    w = _words(s)
    if not w:
        return None
    return f"{field_}:(" + " ".join(x + ("~" if fuzzy and len(x) > 3 else "") for x in w) + ")"


def _at(s):
    p = s["parts"]
    return (p[0], " - ".join(p[1:])) if len(p) >= 2 else (None, None)


def _join(*bits):
    bits = [b for b in bits if b]
    return " AND ".join(bits) if len(bits) >= 2 else None


def _quoted(s, extra=""):
    a, t = _at(s)
    return f'recording:"{lucene(t)}" AND artist:"{lucene(a)}"{extra}' if a else None


# Name (split_name's result) -> MusicBrainz search, or None when it does
# not apply. The names are what harvest.sqlite and PARAMS refer to.
STRATEGIES = {
    "artist_title":            lambda s: _quoted(s),
    "artist_title_official":   lambda s: _quoted(s, " AND status:official"),
    "artist_title_album":      lambda s: _quoted(s, " AND status:official AND primarytype:album"),
    "main_artist_title":       lambda s: (lambda a, t: a and f'recording:"{lucene(t)}" AND artist:"{lucene(main_artist(a))}"')(*_at(s)),
    "main_artist_clean_title": lambda s: (lambda a, t: a and f'recording:"{lucene(clean_title(t))}" AND artist:"{lucene(main_artist(a))}"')(*_at(s)),
    "title_only":              lambda s: (lambda a, t: a and f'recording:"{lucene(t)}"')(*_at(s)),
    "clean_title_only":        lambda s: (lambda a, t: a and f'recording:"{lucene(clean_title(t))}"')(*_at(s)),
    "title_only_official":     lambda s: (lambda a, t: a and f'recording:"{lucene(t)}" AND status:official')(*_at(s)),
    "words":                   lambda s: (lambda a, t: a and _join(_q_words("recording", t), _q_words("artist", a)))(*_at(s)),
    "words_fuzzy":             lambda s: (lambda a, t: a and _join(_q_words("recording", t, True), _q_words("artist", a, True)))(*_at(s)),
    "swapped":                 lambda s: len(s["parts"]) >= 2 and f'recording:"{lucene(" - ".join(s["parts"][:-1]))}" AND artist:"{lucene(s["parts"][-1])}"' or None,
    "first_last":              lambda s: len(s["parts"]) >= 3 and f'recording:"{lucene(s["parts"][-1])}" AND artist:"{lucene(s["parts"][0])}"' or None,
    "last_part_only":          lambda s: len(s["parts"]) >= 3 and f'recording:"{lucene(s["parts"][-1])}"' or None,
    "free_text":               lambda s: (lambda w: w and "(" + " ".join(w) + ")")([lucene(x) for x in _words(s["stem"])]),
    "whole_as_title":          lambda s: len(s["parts"]) == 1 and f'recording:"{lucene(s["stem"])}"' or None,
}


# ── candidates ───────────────────────────────────────────────────────────
@dataclass
class Cand:
    """One recording on one release, as a search returned it."""
    strategy: str
    title: str
    artist: str
    artists: list
    length: float | None
    disambiguation: str = ""
    release: str = ""
    album_artist: str = ""
    status: str = ""
    date: str = ""
    primary: str = ""
    secondary: list = field(default_factory=list)
    country: str = ""
    recording_id: str = ""
    release_id: str = ""
    release_group_id: str = ""
    track_number: str = ""
    track_position: int | None = None
    medium_position: int | None = None
    medium_tracks: int | None = None
    release_tracks: int | None = None


def _credit(c) -> str:
    return "".join(x.get("name", "") + x.get("joinphrase", "") for x in c or []).strip()


# Recordings asked for per search, and releases looked at per recording —
# what the rules were measured on (scripts/music_match/harvest.py uses the
# same), so the inbox sees what the evaluation saw.
RESULTS = 50
KEEP_RELEASES = 15


def cands_from_answer(strategy: str, recordings: list[dict], keep: int | None = KEEP_RELEASES) -> list[Cand]:
    """A MusicBrainz recording search's answer (or recording entries) as
    candidates, `keep` releases per recording (None: all of them)."""
    out = []
    for r in recordings or []:
        base = dict(strategy=strategy, title=r.get("title") or "", artist=_credit(r.get("artist-credit")),
                    artists=[c.get("name") for c in r.get("artist-credit") or []],
                    length=(r.get("length") or 0) / 1000 or None,
                    disambiguation=r.get("disambiguation") or "", recording_id=r.get("id") or "")
        rels = (r.get("releases") or [])[:keep]
        if not rels:
            out.append(Cand(**base))
        for rel in rels:
            g = rel.get("release-group") or {}
            m = (rel.get("media") or [{}])[0]
            t = (m.get("track") or [{}])[0]
            out.append(Cand(
                **base, release=rel.get("title") or "",
                album_artist=_credit(rel.get("artist-credit")) or base["artist"],
                status=rel.get("status") or "", date=rel.get("date") or "",
                primary=g.get("primary-type") or "", secondary=g.get("secondary-types") or [],
                country=rel.get("country") or "", release_id=rel.get("id") or "",
                release_group_id=g.get("id") or "", track_number=str(t.get("number") or ""),
                track_position=(m["track-offset"] + 1) if m.get("track-offset") is not None else None,
                medium_position=m.get("position"), medium_tracks=m.get("track-count"),
                release_tracks=rel.get("track-count")))
    return out


# ── deciding ─────────────────────────────────────────────────────────────
@dataclass
class Params:
    # Which searches to send, and use. Measured (scripts/music_match): these
    # five do what all fifteen do — 654 of 690 checked songs right, none
    # wrong — at a third of the searches, and MusicBrainz answers one a second.
    strategies: tuple = ("main_artist_title", "artist_title_official", "title_only_official",
                         "words_fuzzy", "free_text")
    # How alike titles / artists must be (difflib ratio after tidying).
    title_ratio: float = 0.85
    artist_ratio: float = 0.85
    # Compare titles with brackets removed too.
    loose_titles: bool = True
    # Seconds either way, or this fraction of the length, is the same recording.
    slack: float = 8.0
    slack_frac: float = 0.04
    # Release types a song may be recognised on (it is filed on the artist's
    # own one when there is one — see decide's last step).
    types: tuple = ("Album", "Single", "EP", "Album + Compilation", "Single + Compilation",
                    "EP + Compilation", "Album + Soundtrack")
    official_only: bool = True
    # Artist and title may not *both* be merely alike: one must be exact.
    one_exact: bool = True
    # No plain version fits: a remix / mix / edit fitting within this many
    # seconds will do (0 = never). Never karaoke, instrumental, live, cover…
    take_slack: float = 3.0
    # A song found only on other people's compilations is trusted (True) or
    # left for review (False): compilations are where misattributions live —
    # "Bob Marley - Don't Worry Be Happy" (it is Bobby McFerrin's) exists
    # under Bob Marley only on a German party compilation.
    compilation_only: bool = False
    # Nothing official fits: a bootleg of the artist's own (never Various
    # Artists) will do when title and artist are exact and the length fits
    # within this many seconds (0 = never) — a band's unreleased demos exist
    # only on bootlegs (Evanescence's "Bleed", "Anything for You").
    bootleg_slack: float = 0.0


PARAMS = Params()


def decide(parts: list, seconds: float | None, cands: list[Cand],
           p: Params = PARAMS, lookup=None) -> tuple[Cand | None, str]:
    """The candidate to file under, or None and why not.

    `lookup(recording_id)` — MusicBrainz's full entry for a recording, with
    every release it is on (a search shows only a few) — is used, when
    given, for a song otherwise found only on compilations: the very
    recording that fits may also be on the artist's own single or album."""
    reads = readings(parts)
    want_t = [(title_key(t), loose_title(t), version_words(t)) for _, t in reads]
    want_a = [artist_keys(x) for x, _ in reads]
    asked = set().union(*(w for _, _, w in want_t)) if want_t else set()
    fits, takes, bootlegs, reason = [], [], [], ""
    for c in cands:
        if c.strategy not in p.strategies:
            continue
        bootleg = p.official_only and bool(c.status) and c.status != "Official"
        if bootleg and not (p.bootleg_slack and c.status == "Bootleg"):
            continue
        if " + ".join([c.primary or "Other", *c.secondary]) not in p.types:
            continue
        if "live" in c.disambiguation.lower():
            continue
        tk, tl, vw = title_key(c.title), loose_title(c.title), version_words(c.title)
        # Which readings of the name the title fits: the artist must then
        # fit one of the *same* readings — "DJ Tiesto - Ayla" is not "Ayla"
        # by Ayla just because the name also reads as "Ayla - DJ Tiesto".
        fit_reads = [i for i, (t, l, _) in enumerate(want_t)
                     if alike(tk, t, p.title_ratio) or (p.loose_titles and l and alike(tl, l, p.title_ratio))]
        if not fit_reads:
            continue
        title_exact = any(want_t[i][0] == tk or (tl and want_t[i][1] == tl) for i in fit_reads)
        # "I Want Your Sex, Pt. 2" is not "I Want Your Sex".
        if part_of(c.title) and part_of(c.title) not in {part_of(t) for _, t in reads}:
            continue
        other = (vw & (_OTHER_TAKE | _MIXES)) - asked
        if other and (not p.take_slack or other - _MIXES):
            continue
        credited = set().union(*(artist_keys(x) for x in c.artists or [c.artist])) or artist_keys(c.artist)
        artist_ok = any(alike(k, ck, p.artist_ratio) for i in fit_reads for k in want_a[i] for ck in credited)
        if not artist_ok:
            continue
        # "Green Day - Letterbomb" is not "Green Hay - Glitterbomb".
        if p.one_exact and not title_exact \
                and not any(k == ck for i in fit_reads for k in want_a[i] for ck in credited):
            continue
        if not c.length or not seconds:
            reason = reason or "no length to compare"
            continue
        gap = abs(c.length - seconds)
        if bootleg:
            exact_artist = any(k == ck for i in fit_reads for k in want_a[i] for ck in credited)
            own_release = bool(artist_keys(c.album_artist) & credited)
            if not other and title_exact and exact_artist and own_release and gap <= p.bootleg_slack:
                bootlegs.append(c)
            continue
        if other:
            if gap <= p.take_slack:
                takes.append(c)
        elif gap <= max(p.slack, seconds * p.slack_frac):
            fits.append(c)
        else:
            reason = reason or f"the length differs ({_mmss(seconds)} here, {_mmss(c.length)} on MusicBrainz)"
    pool = fits or takes or bootlegs
    if not pool:
        return None, reason or "no recording of that artist has this title"

    def own(c):
        credited = set().union(*(artist_keys(x) for x in c.artists or [c.artist]))
        return bool(artist_keys(c.album_artist) & credited)
    if not p.compilation_only and not any(own(c) for c in pool):
        if lookup:
            found = _own_release_of(pool, lookup)
            if found:
                return found, ""
        return None, f"only found on compilations ({pool[0].release!r}), never on the artist's own release"

    # Which one to file under: the artist's own release — always, so nothing
    # is ever filed under "Various Artists" (the gate above makes sure there
    # is one) — then the plainest title on it (not the "(Spanish version)"),
    # album before single, earliest.
    rank = {"Album": 0, "Single": 1, "EP": 1}
    pool.sort(key=lambda c: (not own(c), len(version_words(c.title) - asked), rank.get(c.primary, 2),
                             bool(c.secondary), c.date or "9999"))
    return pool[0], ""


# Recordings looked up per song, best-fitting first.
LOOKUPS_PER_SONG = 6


def _own_release_of(pool: list[Cand], lookup) -> Cand | None:
    """One of these recordings on a release of the artist's own — official,
    an album, single or EP, not a compilation — from its full entry."""
    seen = []
    for c in pool:
        if c.recording_id and c.recording_id not in seen:
            seen.append(c.recording_id)
    rank = {"Album": 0, "Single": 1, "EP": 1}
    for rid in seen[:LOOKUPS_PER_SONG]:
        entry = lookup(rid) or {}
        found = [x for x in cands_from_answer(pool[0].strategy, [entry], keep=None)
                 if x.status == "Official" and not x.secondary and x.primary in rank
                 and artist_keys(x.album_artist) & set().union(*(artist_keys(a) for a in x.artists or [x.artist]))]
        if found:
            found.sort(key=lambda x: (rank[x.primary], x.date or "9999"))
            return found[0]
    return None


def _mmss(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"
