# Food: the old recipe-URL pipeline (archived 2026-11-03)

Taken out of `api/services/food.py` to be rebuilt as one pipeline that runs
from the dish's Save button. `pipeline.py` is the code as it was, verbatim and
not imported anywhere. Git history has it too (the commits before this one).

## What it did

Three background stages, each a daemon thread that polled the DB for work:

1. **Page fetch**: `_spawn_text_fetch` → `_apply_text_fetch` → `fetch_page_text`.
   On create, or on a URL change, it fetched the page through `_public_get`
   (public addresses only, redirects checked, 15 MB cap) and reduced the HTML
   to visible text (`_TextExtractor`). It stored that in `food_dishes.page_text`,
   but only if the URL was still the same.
2. **Instructions**: `_process_pending_instructions`. For each dish with
   `page_text` and no instructions, it made one LLM call
   (`_INSTRUCTIONS_SYSTEM_PROMPT`, page text cut to 12 000 chars) asking for
   Markdown steps in English.
3. **Ingredients**: `_process_pending_ingredients`. For each dish with
   `page_text` and no ingredient rows, it made up to 3 LLM attempts
   (`_INGREDIENTS_SYSTEM_PROMPT`). It sent the known ingredient list, checked
   the answer with `_validate_generated`, and on failure fed back every error
   and asked again.

The triggers were scattered: `init_db`, `create_dish`, the end of the page
fetch, and the URL branch of `update_dish`. A URL change also blanked
`page_text`, the instructions and the ingredients.

## Why it went

- **Nothing tells the user what is happening:** work happens at some point
  after the save, from three places. The only signal was a red/green dot
  ("recipe text fetched") on the card.
- **A failed dish is skipped until the next trigger** (another dish added, a
  restart), with no error anywhere.
- **The stages hand off through DB columns** (`page_text != ''`,
  `instructions = ''`, "no ingredient rows"), so clearing a field by hand
  re-arms a stage.
- **The parts are tangled:** the URL edit, the fetch and the two LLM stages
  live in the CRUD functions.

## Worth keeping for the rebuild

- **`_public_get` / `_check_public`**: still in `food.py`, used for images.
  It's the SSRF guard (the LAN has ESP32 boards, qBittorrent and the router)
  and must stay in front of any fetch of a user-given URL.
- **The ingredients prompt's naming rules:** English, singular, the plain
  name it is bought under, the product rather than a part of it. Also the
  idea of validating the answer and feeding back every error at once.
- **The data:** `food_dishes.page_text` is still in the live DB with the
  pages fetched so far. The code no longer reads or writes it.

## Web client bits removed

- **`has_text` on `Dish`** and the `dish-status-dot` on the card: red until
  the page text was fetched, hidden once instructions or ingredients existed.
  Its CSS and the strings "Recipe text saved" / "Recipe text not fetched yet"
  went too.
