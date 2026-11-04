"""Chefkoch (chefkoch.de): everything that depends on how its pages are built.

A recipe site of recipe_sites.py: see RECIPE_SITES.md for what a site has to
expose. It only reads HTML; fetching is the caller's (`fetch`, a URL -> page
text function that refuses non-public addresses -- food.py's _public_get).

* **search** -- www.chefkoch.de/rs/s<N>/<query>/Rezepte.html, N the page
  less one, 42 results a page. Each result is a
  <div class="ds-recipe-card bi-recipe-item" data-vars-...>: its title,
  rating and votes in the data-vars, then its link, image, time ("15 Min.")
  and difficulty ("simpel"). A Chefkoch Plus card
  (data-vars-payed-content-type="plus_recipe") is paid: left out.
* **difficulty** -- a recipe page's "Schwierigkeit", missing from its
  schema.org data. The rest -- ingredients, steps, times -- is schema.org,
  read by food.py; the steps have no photos.
"""
import html
import re
from typing import Callable
from urllib.parse import quote

NAME = "Chefkoch"
LANGUAGE = "de"
HOSTS = ("chefkoch.de",)

SEARCH_URL = "https://www.chefkoch.de/rs/s{start}/{query}/Rezepte.html"
_PAGE_SIZE = 42

_CARD_SPLIT = '<div class="ds-recipe-card bi-recipe-item"'
_DATA_RE = re.compile(r'\bdata-vars-([a-z-]+)="([^"]*)"')
_LINK_RE = re.compile(r'href="(https://www\.chefkoch\.de/rezepte/\d+/[^"#?]+\.html)"')
_IMG_RE = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"')
_INFO_RE = re.compile(r'<span class="ds-recipe-info__text">([^<]*)</span>')
_DESCRIPTION_RE = re.compile(r'<div class="ds-recipe-card__description[^"]*">(.*?)</div>', re.S)

# Its three levels, on cards and recipe pages alike.
_DIFFICULTIES = {"simpel": "easy", "normal": "medium", "pfiffig": "hard"}


def _clean(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def search(query: str, page: int, fetch: Callable[[str], str]) -> dict:
    """One page of results for `query`, as giallozafferano.search gives
    them: url, title, image, description, rating ("4.4"), votes, time
    ("15 Min."), difficulty (food.DIFFICULTIES); `next_page`, None when
    this one wasn't full."""
    text = fetch(SEARCH_URL.format(start=page - 1, query=quote(query.strip())))
    results, seen = [], set()
    for card in text.split(_CARD_SPLIT)[1:]:
        head = card[:card.find(">")]
        data = dict(_DATA_RE.findall(head))
        link = _LINK_RE.search(card)
        if not link or link[1] in seen or data.get("payed-content-type"):
            continue
        seen.add(link[1])
        img, desc = _IMG_RE.search(card), _DESCRIPTION_RE.search(card)
        infos = [_clean(i) for i in _INFO_RE.findall(card)]
        results.append({
            "url": link[1],
            "title": html.unescape(data.get("recipe-title", "")),
            "image": img[1] if img else "",
            "category": "",
            "description": _clean(desc[1]) if desc else "",
            "rating": data.get("rating", "") if data.get("num-votes", "0") != "0" else "",
            "votes": data.get("num-votes", "") if data.get("num-votes", "0") != "0" else "",
            "comments": "",
            "difficulty": next((_DIFFICULTIES[i.lower()] for i in infos if i.lower() in _DIFFICULTIES), ""),
            "time": next((i for i in infos if "min" in i.lower()), ""),
            "kcal": "",
        })
    full = text.count(_CARD_SPLIT) >= _PAGE_SIZE
    return {"results": results, "next_page": page + 1 if full else None}


# <i ...>difficulty_level</i> <div ...__labels><div ...__value>Simpel</div>
# <div ...__title>Schwierigkeit</div>
_DIFFICULTY_RE = re.compile(
    r">difficulty_level</i>.*?recipe-meta-property-group__value[^>]*>(?:<!--\[-->)?\s*([^<]+?)\s*<", re.S)


def difficulty(page_html: str) -> str:
    """A recipe page's difficulty (food.DIFFICULTIES), "" when it shows none."""
    m = _DIFFICULTY_RE.search(page_html)
    return _DIFFICULTIES.get(m[1].lower(), "") if m else ""
