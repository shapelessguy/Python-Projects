"""BBC Good Food (bbcgoodfood.com): everything that depends on how its pages
are built.

A recipe site of recipe_sites.py: see RECIPE_SITES.md for what a site has to
expose. It only reads HTML; fetching is the caller's (`fetch`, a URL -> page
text function that refuses non-public addresses -- food.py's _public_get).

The site is a Next.js app: each page's data is the JSON in its
<script id="__NEXT_DATA__">, and that is what is read.

* **search** -- www.bbcgoodfood.com/search?q=<query>: the first 30
  results, props.pageProps.searchResults.items -- title, url, image,
  rating, and "terms" with the time ("35 mins") and skill level ("Easy").
  No further pages (?page=2 comes back empty). A /premium/ recipe is paid:
  left out, as is anything not a recipe.
* **difficulty** -- a recipe page's skill level, missing from its schema.org
  data. The rest -- ingredients, steps, times -- is schema.org, read by
  food.py; the steps have no photos.
"""
import json
import re
from typing import Callable
from urllib.parse import quote

NAME = "BBC Good Food"
LANGUAGE = "en"
HOSTS = ("bbcgoodfood.com",)

SEARCH_URL = "https://www.bbcgoodfood.com/search?q={query}"
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

_DIFFICULTIES = {"easy": "easy", "more effort": "medium", "a challenge": "hard"}


def _next_data(page_html: str) -> dict:
    m = _NEXT_DATA_RE.search(page_html)
    try:
        return json.loads(m[1]) if m else {}
    except ValueError:
        return {}


def _term(item: dict, slug: str) -> str:
    return next((str(t.get("display") or "") for t in item.get("terms") or []
                 if isinstance(t, dict) and t.get("slug") == slug), "")


def search(query: str, page: int, fetch: Callable[[str], str]) -> dict:
    """The results for `query`, as giallozafferano.search gives them: url,
    title, image, rating ("4.6"), votes, time ("35 mins"), difficulty
    (food.DIFFICULTIES). One page only: a later one is empty."""
    if page > 1:
        return {"results": [], "next_page": None}
    data = _next_data(fetch(SEARCH_URL.format(query=quote(query.strip()))))
    items = (((data.get("props") or {}).get("pageProps") or {}).get("searchResults") or {}).get("items") or []
    results, seen = [], set()
    for it in items:
        url = str(it.get("url") or "")
        if it.get("postType") != "recipe" or "/recipes/" not in url or it.get("isPremium") or url in seen:
            continue
        seen.add(url)
        rating = it.get("rating") or {}
        votes = rating.get("ratingCount") or 0
        results.append({
            "url": url,
            "title": str(it.get("title") or "").removesuffix(" recipe"),
            "image": str((it.get("image") or {}).get("url") or ""),
            "category": "",
            "description": "",
            "rating": str(rating.get("ratingValue") or "") if votes else "",
            "votes": str(votes) if votes else "",
            "comments": "",
            "difficulty": _DIFFICULTIES.get(_term(it, "skillLevel").lower(), ""),
            "time": _term(it, "time"),
            "kcal": "",
        })
    return {"results": results, "next_page": None}


_SKILL_RE = re.compile(r'"skillLevel":"([^"]+)"')


def difficulty(page_html: str) -> str:
    """A recipe page's difficulty (food.DIFFICULTIES), "" when it shows none."""
    m = _SKILL_RE.search(page_html)
    return _DIFFICULTIES.get(m[1].lower(), "") if m else ""
