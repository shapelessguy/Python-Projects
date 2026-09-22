"""Film identification against TMDb.

preparePlex calls this "check_on_imdb" but the API is themoviedb.org; the
naming is kept only where it touches existing config. The job is to turn a
release name into the canonical `Title (Year)` the library is organised by —
which is worth doing for more than tidiness: a scene name is lossy in ways
that matter. `Angels.Egg.1985.PC.1080p...` has silently dropped an apostrophe,
and only a lookup puts it back.

The auto-accept rule is preparePlex's and is kept: if exactly one result
matches the parsed title exactly (ignoring punctuation and case) and the year
agrees, take it. Anything else is a question for a human, because a wrong
match here renames the file and there is nothing downstream to catch it.
"""
import re
import unicodedata

import requests

from api.config import TMDB_API_KEY

SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
DETAILS_URL = "https://api.themoviedb.org/3/movie/{id}"
_TIMEOUT = 15


class TmdbError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def configured() -> bool:
    return bool(TMDB_API_KEY)


def _normalise(s: str) -> str:
    """Compare titles the way a human would: accents, punctuation and case are
    all noise. `Angels Egg` and `Angel's Egg` must come out equal, or the
    apostrophe this exists to restore would stop it matching."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def library_name(title: str, year: str) -> str:
    """The library's own convention. A colon becomes ' -' — see the existing
    folders (`Alita - Battle Angel (2019)`, `2001 - A Space Odyssey (1968)`) —
    and everything a filesystem objects to is dropped."""
    name = (title or "").replace(":", " -")
    name = re.sub(r'[\\/*?"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return f"{name} ({year})" if year else name


def search(title: str, year: str = "", limit: int = 15) -> list[dict]:
    if not configured():
        raise TmdbError("TMDB_API_KEY is not set in secrets.json", 503)
    params = {"api_key": TMDB_API_KEY, "query": title, "include_adult": "false"}
    if year:
        # Narrowing server-side beats paging through everything and filtering
        # afterwards, which is what preparePlex does.
        params["primary_release_year"] = year
    try:
        r = requests.get(SEARCH_URL, params=params, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise TmdbError(f"TMDb unreachable: {e}")
    if r.status_code == 401:
        raise TmdbError("TMDb rejected the API key", 502)
    if not r.ok:
        raise TmdbError(f"TMDb returned {r.status_code}")
    results = r.json().get("results", [])
    if not results and year:
        # The year in a release name is often the re-release or the rip's
        # year rather than the film's; retry without it before giving up.
        return search(title, "", limit)
    return [_candidate(m) for m in results[:limit]]


def _candidate(m: dict) -> dict:
    year = (m.get("release_date") or "")[:4]
    title = m.get("title") or m.get("original_title") or ""
    return {
        "id": m.get("id"),
        "title": title,
        "original_title": m.get("original_title") or "",
        "year": year,
        "name": library_name(title, year),
        "overview": (m.get("overview") or "")[:400],
        "poster": f"https://image.tmdb.org/t/p/w185{m['poster_path']}" if m.get("poster_path") else None,
        "votes": m.get("vote_count", 0),
    }


def details(movie_id: int) -> dict:
    if not configured():
        raise TmdbError("TMDB_API_KEY is not set in secrets.json", 503)
    try:
        r = requests.get(DETAILS_URL.format(id=movie_id),
                         params={"api_key": TMDB_API_KEY}, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise TmdbError(f"TMDb unreachable: {e}")
    if not r.ok:
        raise TmdbError(f"TMDb returned {r.status_code}")
    d = r.json()
    year = (d.get("release_date") or "")[:4]
    return {
        "id": d.get("id"),
        "title": d.get("title", ""),
        "original_title": d.get("original_title", ""),
        "year": year,
        "name": library_name(d.get("title", ""), year),
        "genres": [g["name"] for g in d.get("genres", [])],
        "runtime": d.get("runtime"),
        "original_language": d.get("original_language"),
        "overview": d.get("overview", ""),
        "poster": f"https://image.tmdb.org/t/p/w342{d['poster_path']}" if d.get("poster_path") else None,
    }


def identify(title: str, year: str = "") -> dict:
    """Search, and say whether the answer is safe to take without asking.

    `confident` is only true for a single exact title match with an agreeing
    year. Everything else comes back as candidates — renaming on a guess is
    how a film ends up in the library under the wrong name with nothing to
    notice it."""
    candidates = search(title, year)
    want = _normalise(title)
    exact = [
        c for c in candidates
        if want in (_normalise(c["title"]), _normalise(c["original_title"]))
        and (not year or not c["year"] or c["year"] == year)
    ]
    best = exact[0] if len(exact) == 1 else None
    return {
        "query": {"title": title, "year": year},
        "confident": bool(best),
        "match": best,
        "candidates": candidates,
    }
