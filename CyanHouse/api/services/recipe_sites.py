"""The recipe sites searched together, and their results merged.

A site is a module (giallozafferano.py, chefkoch.py, bbcgoodfood.py) with:

  NAME       how it is shown ("Chefkoch")
  LANGUAGE   the language its search is asked in (food.LANGUAGES)
  HOSTS      its domains, a recipe URL's site told by them
  search(query, page, fetch) -> {"results": [hit, ...], "next_page": n | None}
             a hit: url, title, image, category, description, rating,
             votes, comments, difficulty (food.DIFFICULTIES), time, kcal
             ("" for what its results don't show)

and optionally, for its recipe pages (food.fetch_recipe_page):

  preparation(url, page_html, mark) -> steps   its steps with their photos,
                                               when schema.org's lack them
  difficulty(page_html) -> food.DIFFICULTIES   when its page shows one

What a site has to expose to be one, and how to check: RECIPE_SITES.md.

A search asks every site at once, each in its own language, for up to
PER_SITE results, and ranks them all by how well their title fits the query
(as that site was asked it) -- the site's own order breaking ties.
"""
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from typing import Callable
from urllib.parse import urlsplit

from api.services import bbcgoodfood, chefkoch, giallozafferano

SITES = (giallozafferano, chefkoch, bbcgoodfood)
PER_SITE = 20
_MAX_PAGES = 3  # a site's pages read for its PER_SITE


def site_for(url: str):
    """The site module a URL is on, None for another."""
    host = (urlsplit(url).hostname or "").lower()
    return next((s for s in SITES if any(host == h or host.endswith("." + h) for h in s.HOSTS)), None)


def languages() -> set[str]:
    return {s.LANGUAGE for s in SITES}


_HOURS_RE = re.compile(r"(\d+)\s*(?:h|hr|hrs|hour|hours|std|stunden?|or[ae])\b", re.I)
_MINUTES_RE = re.compile(r"(\d+)\s*(?:m|min|mins|minut[eio]n?|minutes)\b", re.I)


def _time(text: str) -> str:
    """A result's time the same way whatever its site's: "1 h 10 min" --
    as it was when it can't be read."""
    h, m = _HOURS_RE.search(text), _MINUTES_RE.search(text)
    if not h and not m:
        return text
    total = (int(h[1]) * 60 if h else 0) + (int(m[1]) if m else 0)
    return " ".join(p for p in (f"{total // 60} h" if total >= 60 else "", f"{total % 60} min" if total % 60 else "") if p)


def _site_results(site, query: str, fetch: Callable[[str], str]) -> list[dict]:
    hits: list[dict] = []
    seen: set[str] = set()
    page: int | None = 1
    for _ in range(_MAX_PAGES):
        r = site.search(query, page, fetch)
        for h in r["results"]:
            if h["url"] not in seen:
                seen.add(h["url"])
                hits.append(h)
        page = r["next_page"]
        if len(hits) >= PER_SITE or page is None:
            break
    return hits[:PER_SITE]


# Words that join a dish's name, not name it: no weight in the fit.
_JOINERS = set("""
a al alla alle allo ai agli all con di del della delle dei degli e ed in il la le lo i gli per da
mit und an auf aus im in der die das den dem des vom zum zur nach art
with and the of in on a an style
""".split())


def _words(text: str) -> list[str]:
    s = unicodedata.normalize("NFKD", text.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return [w for w in re.sub(r"[^a-z0-9]+", " ", s).split() if w not in _JOINERS]


def _like(a: str, b: str) -> float:
    """How alike two words are; a word inside a German compound counts
    ("curry" in "huhncurry")."""
    if a == b:
        return 1.0
    if len(a) >= 4 and (a in b or b in a):
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def fit(query: str, title: str) -> float:
    """How well a title fits a query, 0..1: mostly how much of the query it
    has, a little how much of it is the query (no long titles of extras)."""
    q, t = _words(query), _words(title)
    if not q or not t:
        return 0.0
    has = sum(max(_like(w, x) for x in t) for w in q) / len(q)
    only = sum(1 for x in t if max(_like(w, x) for w in q) >= 0.8) / len(t)
    return 0.75 * has + 0.25 * only


def search(queries: dict[str, str], fetch: Callable[[str], str]) -> dict:
    """Every site searched at once, each with queries[its LANGUAGE]: their
    results ranked by fit (each with "site", its NAME), and the sites that
    failed (NAME -> why) -- one failing is no reason to fail the search."""
    with ThreadPoolExecutor(max_workers=len(SITES)) as pool:
        futures = {s: pool.submit(_site_results, s, queries[s.LANGUAGE], fetch) for s in SITES}
    ranked, failed = [], {}
    for site, f in futures.items():
        try:
            hits = f.result()
        except Exception as e:
            print(f"[food search] {site.NAME}: {e}")
            failed[site.NAME] = str(e) or type(e).__name__
            continue
        for pos, h in enumerate(hits):
            ranked.append((round(fit(queries[site.LANGUAGE], h["title"]), 2), pos,
                           {**h, "time": _time(h["time"]), "site": site.NAME}))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    return {"results": [h for _score, _pos, h in ranked], "failed": failed}
