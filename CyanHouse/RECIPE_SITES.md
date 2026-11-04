# Recipe sites

The Food panel's recipe search asks several recipe sites at once and merges
their results; a picked recipe's page is then imported (ingredients,
instructions with photos, times, difficulty). This is what a site has to
expose to be one of them, how to check it, and how to add it.

Code: `api/services/recipe_sites.py` (the registry, the merged search),
one module per site (`giallozafferano.py`, `chefkoch.py`, `bbcgoodfood.py`),
the page reading in `food.py` (`fetch_recipe_page`) and the import in
`food_import.py`.

## How a search works

1. What was typed is turned by the LLM into the query in each site's
   language (`food._search_queries`, one call, cached): "pollo al curry" →
   it "pollo al curry", de "Hähnchen Curry", en "chicken curry". A site
   searched in the wrong language finds nothing (Chefkoch has no
   "pollo al curry").
2. Every site is searched at once, up to 20 results each (`PER_SITE`, as
   many pages as that takes, 3 at most).
3. All of them are ranked by how well their title fits the query as that
   site was asked it (`recipe_sites.fit`), the site's own order breaking
   ties. The picker shows the best 20, "More results" the rest.
4. A site that fails is left out and named; the others still answer.

## Requirements

### Search (S) -- to be searched

| # | Requirement | |
|---|---|---|
| **S1** | A search URL built from the query (and a page) whose results are **in the HTML the server sends** -- or a JSON API. Not added later by JavaScript; no bot challenge (Cloudflare "Just a moment…", `cf-mitigated: challenge`), no login. A Next.js / Nuxt page whose `__NEXT_DATA__` / `__NUXT_DATA__` JSON holds them is fine. | must |
| **S2** | Each result has a **title** (what is ranked) and a **link to one recipe page**, and recipes can be told apart from collections, articles, videos and **paid** recipes (all left out). | must |
| **S3** | **20 results reachable**: a page of 20+, or a page parameter / "next" link. | must |
| **S4** | **Stable markup**: a card per result (or JSON) a small module can read. A redesign breaks it: the module is the one file to fix. | must |
| **S5** | Per result: image, rating and votes, time, difficulty -- shown on the picker's cards. | nice |
| **S6** | A **language**: the one its search is asked in. Any language works -- the instructions are rewritten in every app language anyway. | must |

### Recipe page (P) -- to be imported

| # | Requirement | |
|---|---|---|
| **P1** | Reachable with a plain server-side GET: no bot challenge, no paywall. | must |
| **P2** | **Ingredients as one group, a line each** (amount, unit and name in the line, any order or language). Best: schema.org `recipeIngredient`. Section headings ("Per la salsa:") are fine. | must |
| **P3** | **The preparation as separate steps**, apart from the rest of the page. Best: schema.org `recipeInstructions` as `HowToStep`s; else one block per step in the HTML (a site module's `preparation`). Some chatter inside steps is fine (the LLM drops what isn't preparation); steps scattered through an article are not. | must |
| **P4** | **Photos with their step**: `HowToStep.image`, or an image inside the step's block. | nice |
| **P5** | **Photos numbered and mentioned in the text** (GialloZafferano's `<span class="num-step">`, our `{{ref:N}}`). Rare: only GialloZafferano so far. | nice |
| **P6** | **Prep, cook and total time**, best schema.org ISO 8601 (`PT15M`). Text like "20 minutes" isn't read (Epicurious, Bon Appétit). | nice |
| **P7** | **Difficulty**: not in schema.org, so always the site's own HTML (a site module's `difficulty`), mapped to very_easy … very_hard. | nice |

Everything else on the page (description, nutrition, author…) doesn't
matter. The page's language doesn't either: no need for `inLanguage`.

## Checking a site

```bash
python3 scripts/check_recipe_site.py <recipe url> [<recipe url> ...]
```

runs the import's own reading on a recipe page -- no LLM, nothing saved --
and grades P1–P7. For the search (S1–S4): fetch the search URL with
`food._public_get` and see whether the results are in what comes back.

## Adding a site

A module in `api/services/` (copy `chefkoch.py`), added to
`recipe_sites.SITES`, with:

- `NAME`, `LANGUAGE` (one of `food.LANGUAGES` -- for another language,
  add it there first), `HOSTS` (its domains)
- `search(query, page, fetch)` → `{"results": [...], "next_page": n | None}`,
  each result `url, title, image, category, description, rating, votes,
  comments, difficulty, time, kcal` (`""` for what it doesn't show;
  difficulty one of `food.DIFFICULTIES`)
- optionally `difficulty(page_html)` and `preparation(url, page_html, mark)`
  for its recipe pages, when schema.org lacks them

and its domain in `SITE_NAMES` of `react_ui/src/panels/FoodPanel.tsx`.

## Sites

Searched now:

| Site | Lang | Search | Page | Notes |
|---|---|---|---|---|
| GialloZafferano | it | HTML cards, 15 a page | P1–P7 | the only one with numbered step photos |
| Chefkoch | de | HTML cards + JSON-LD ItemList, 42 a page | P1–P3, P6, P7 | Plus recipes (paid) left out |
| BBC Good Food | en | `__NEXT_DATA__`, 30 results, one page | P1–P3, P6, P7 | /premium/ recipes (paid) left out |

Pages that import (P1–P3, checked 2026-11), search not yet checked:
Marmiton (fr), 750g (fr), Misya, Cookaround, Ricette della Nonna,
Sale&Pepe, La Cucina Italiana (it), RecipeTin Eats, Budget Bytes,
Minimalist Baker, Cookie and Kate, The Woks of Life, Hebbars Kitchen,
King Arthur Baking, Delish, Tasty, Ottolenghi (en), Epicurious, Bon Appétit
(en, times as text), Just One Cookbook (en, with step photos: P4).

Blocked (bot challenge or 403 to a server): Fatto in casa da Benedetta,
Cucchiaio d'Argento, Allrecipes, Serious Eats, Simply Recipes, The Kitchn,
Maangchi, NYT Cooking (also paid).
