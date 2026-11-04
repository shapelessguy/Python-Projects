"""GialloZafferano: everything that depends on how its pages are built.

A recipe site of recipe_sites.py (see RECIPE_SITES.md), and the one that
has it all. When GialloZafferano changes its HTML, this is the file to fix. It only
reads HTML; fetching is the caller's (`fetch`, a URL -> page text function
that refuses non-public addresses -- food.py's _public_get).

Two things are read off its pages:

* **search** -- www.giallozafferano.it/ricerca-ricette/[pageN/]<query>/.
  Every <article class="gz-card ..."> linking to a recipe page
  (ricette.giallozafferano.it/<Name>.html) is a result, whatever its layout:
  a plain search lists them one under the other ("gz-card-search", 15 a
  page); a popular one ("carbonara") gets a landing page of carousels
  repeating them, whose cards show less, and whose page 2 is the plain
  list; "SPECIALE" cards link to collections, not recipes.
* **preparation** -- a recipe page's steps with their photos, the one thing
  the page's schema.org data (read by food.py, a web standard) lacks. Where
  the text points at a photo is marked the caller's way (`mark`).
* **difficulty** -- also missing from the schema.org data.
"""
import html
import re
from typing import Callable
from urllib.parse import quote, urljoin

NAME = "GialloZafferano"
LANGUAGE = "it"
HOSTS = ("giallozafferano.it",)

SEARCH_URL = "https://www.giallozafferano.it/ricerca-ricette/{page}{query}/"

_CARD_RE = re.compile(r'<article class="gz-card[^"]*".*?</article>', re.S)
_LINK_RE = re.compile(r'href="(https://ricette\.giallozafferano\.it/[^"#?]+\.html)"')
_TITLE_RE = re.compile(r'<h[1-6] class="gz-title[^"]*">(.*?)</h[1-6]>', re.S)
_IMG_RE = re.compile(r'<img\b[^>]*?\b(?:data-src|src)="([^"]+)"')
_CATEGORY_RE = re.compile(r'<div class="gz-category">\s*<a[^>]*>(.*?)</a>', re.S)
_DESCRIPTION_RE = re.compile(r'<div class="gz-description">(.*?)</div>', re.S)
# A card's facts, each a <li class="gz-single-data-recipe"> told apart by its
# icon ("#voto-orange", "#tempo-grey"...): the name before the colour.
_FACT_RE = re.compile(r'<li class="gz-single-data-recipe[^"]*">(.*?)</li>', re.S)
_FACT_ICON_RE = re.compile(r'#([a-z]+)-[a-z]+"')
_FACTS = {"voto": "rating", "commento": "comments", "difficolta": "difficulty", "tempo": "time", "kcal": "kcal"}
_PLAIN_CARD = "gz-card-search"  # a card of the plain list
_PAGE_SIZE = 15  # the plain list's results a page

# The preparation: a <div class="gz-content-recipe-step"> per step -- its
# photos, then its paragraph(s), which point at them with
# <span class="num-step">N</span> -- up to the next section's heading
# (Conservazione, Consiglio...). A photo is a <picture data-step="N"> each,
# or, in older recipes, one <picture class="...-img-full"> strip of them all
# (its file "..._strip_1-3.jpg"), with no data-step.
_STEP_SPLIT = '<div class="gz-content-recipe-step">'
_SECTION_HEADING = 'class="gz-title-section'
_PICTURE_RE = re.compile(r"<picture\b([^>]*)>(.*?)</picture>", re.S)
_DATA_STEP_RE = re.compile(r'\bdata-step="(\d+)"')
_PARAGRAPH_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S)
_NUM_STEP_RE = re.compile(r'<span class="num-step">\s*(\d+)\s*</span>')


def _clean(fragment: str) -> str:
    """An HTML fragment's text: tags out, entities decoded, spaces collapsed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _cards(page_html: str) -> list[dict]:
    """The recipe cards of a search page, once each."""
    results, seen = [], set()
    for card in _CARD_RE.findall(page_html):
        link, title = _LINK_RE.search(card), _TITLE_RE.search(card)
        if not link or not title or link[1] in seen:
            continue
        seen.add(link[1])
        img, cat, desc = _IMG_RE.search(card), _CATEGORY_RE.search(card), _DESCRIPTION_RE.search(card)
        hit = {"url": link[1], "title": _clean(title[1]), "image": img[1] if img else "",
               "category": _clean(cat[1]) if cat else "", "description": _clean(desc[1]) if desc else "",
               "votes": "", **{k: "" for k in _FACTS.values()}}
        for fact in _FACT_RE.findall(card):
            icon = _FACT_ICON_RE.search(fact)
            if icon and icon[1] in _FACTS:
                hit[_FACTS[icon[1]]] = re.sub(r"(?i)^kcal\s*", "", _clean(fact))
        hit["difficulty"] = _DIFFICULTIES.get(hit["difficulty"].lower(), "")
        results.append(hit)
    return results


def search(query: str, page: int, fetch: Callable[[str], str]) -> dict:
    """One page of results for `query`: each with its recipe URL, title,
    image, category, description, and the facts its card shows -- rating
    ("4,3"), votes (never: its cards don't say), comments, difficulty
    (food.DIFFICULTIES), time ("4 h 40 min"), kcal ("" where it shows none); `next_page`, None for the last as far as
    can be told (one past it just comes back empty).

    A landing page's cards show only rating and comments, so its page 2 --
    the plain list -- is read too and the two merged: details from page 2,
    order from page 1."""
    def page_html(n: int) -> str:
        return fetch(SEARCH_URL.format(page=f"page{n}/" if n > 1 else "", query=quote(query.strip())))

    text = page_html(page)
    results = _cards(text)
    nxt = page + 1
    if page == 1 and _PLAIN_CARD not in text and "/ricerca-ricette/page2/" in text:
        text = page_html(2)
        listed = {h["url"]: h for h in _cards(text)}
        results = [{**h, **{k: v for k, v in listed.pop(h["url"], {}).items() if v}} for h in results]
        results += listed.values()
        nxt = 3
    # A landing query's page 2 doesn't link on, though page 3 is there: a
    # full page of the plain list says there may be more, too.
    more = f"/ricerca-ricette/page{nxt}/" in text or text.count(_PLAIN_CARD) >= _PAGE_SIZE
    return {"results": results, "next_page": nxt if more else None}


def preparation(url: str, page_html: str, mark: Callable[[int], str]) -> list[dict]:
    """A recipe page's steps, [] when it has no GialloZafferano preparation
    section: each step's text -- photo N it points at written mark(N) -- and
    its photos, [{"steps": [N, ...], "url"}] (absolute): the photo numbers
    each shows, one, or all of the step's for a strip."""
    start = page_html.find(_STEP_SPLIT)
    if start < 0:
        return []
    end = page_html.find(_SECTION_HEADING, start)
    steps = []
    for chunk in page_html[start:end if end > 0 else None].split(_STEP_SPLIT)[1:]:
        # The number's own spaces go: GialloZafferano writes "tagliere <span>1</span> ."
        paragraphs = (_clean(_NUM_STEP_RE.sub(lambda m: f" {mark(int(m[1]))}", p)) for p in _PARAGRAPH_RE.findall(chunk))
        text = re.sub(r" +([.,;:!?)])", r"\1", "\n\n".join(p for p in paragraphs if p))
        pointed = [int(n) for n in _NUM_STEP_RE.findall(chunk)]
        images = []
        for attrs, inner in _PICTURE_RE.findall(chunk):
            src, step = _IMG_RE.search(inner), _DATA_STEP_RE.search(attrs)
            if src:
                images.append({"steps": [int(step[1])] if step else pointed, "url": urljoin(url, src[1])})
        if text or images:
            steps.append({"text": text, "images": images})
    return steps


# "Difficoltà: <strong>Media</strong>" among a recipe page's featured data.
_DIFFICULTY_RE = re.compile(r"Difficolt(?:à|&agrave;):\s*<strong>\s*([^<]+?)\s*</strong>")
_DIFFICULTIES = {"molto facile": "very_easy", "facile": "easy", "media": "medium",
                 "difficile": "hard", "molto difficile": "very_hard"}


def difficulty(page_html: str) -> str:
    """A recipe page's difficulty: very_easy, easy, medium, hard, very_hard,
    or "" when it shows none."""
    m = _DIFFICULTY_RE.search(page_html)
    return _DIFFICULTIES.get(m[1].lower(), "") if m else ""
