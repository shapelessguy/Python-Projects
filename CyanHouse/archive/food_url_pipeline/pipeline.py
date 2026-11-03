"""ARCHIVED -- not imported anywhere. The recipe-URL pipeline as it was in
api/services/food.py before it was taken out (2026-11-03), kept verbatim to
look at while building its replacement. See README.md next to this file.

It relied on these, which are still in food.py: connect, _bump_all,
_public_get (the public-addresses-only fetch), _openrouter, OPENROUTER_KEY,
_validate_ingredients_json, _set_dish_ingredients, _spawn_translations_processing.
_openrouter_chat was:

    def _openrouter_chat(messages: list[dict]) -> str:
        return (_openrouter(messages)["content"] or "").strip()
"""
# flake8: noqa

_MAX_INGREDIENT_ATTEMPTS = 3


# ── recipe page (shared, fetched in the background) ─────────────────────
# Only the visible text is kept -- not the raw markup -- since the eventual
# consumer is an LLM chunker, not a renderer. This also happens to be the
# simplest way to drop embedded images: pages routinely inline them as base64
# data: URIs (lazy-load placeholders especially), and stripping to text
# removes those along with all the <script>/<style>/<svg> noise in one pass.
class _TextExtractor(HTMLParser):
    _SKIP_TAGS = {"script", "style", "svg", "noscript", "template", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text)


def _extract_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    return "\n".join(parser.parts)


def fetch_page_text(url: str) -> str:
    """Fetch a dish's recipe-url page and reduce it to plain text. A failure
    here must not fail the dish save -- it just means the url/text status dot
    stays red -- so errors are swallowed."""
    try:
        resp = _public_get(url, timeout=15)
        resp.raise_for_status()
        return _extract_text(resp.text)
    except Exception:
        return ""


def _apply_text_fetch(dish_id: int, url: str) -> None:
    """Runs on a background thread, off the request/response cycle: fetch the
    page, then store it -- but only if this dish's url is still the one we
    were asked to fetch. Without that guard, a slow fetch for an old url
    could land after a newer edit and clobber it with stale content."""
    text = fetch_page_text(url)
    with connect() as conn:
        row = conn.execute("SELECT url FROM food_dishes WHERE id = ?", (dish_id,)).fetchone()
        if row is None or row["url"] != url:
            return
        conn.execute("UPDATE food_dishes SET page_text = ? WHERE id = ?", (text, dish_id))
        _bump_all(conn)  # lets clients' version poll pick up the finished fetch
    if text:
        # This is the actual moment a dish becomes eligible for instructions/
        # ingredients processing (create_dish/init_db also trigger a scan,
        # but the text for a brand-new dish almost never exists yet when
        # those run -- this is what makes the pipelines actually fire in
        # the common case).
        _spawn_instructions_processing()
        _spawn_ingredients_processing()


def _spawn_text_fetch(dish_id: int, url: str) -> None:
    threading.Thread(target=_apply_text_fetch, args=(dish_id, url), daemon=True).start()


# Recipe pages are long and repetitive (nav/ads/comments alongside the actual
# procedure); cap what's sent so a single dish can't blow the model's context.
_MAX_LLM_INPUT_CHARS = 12000


def _openrouter_chat(messages: list[dict]) -> str:
    """The reply's text."""
    return (_openrouter(messages)["content"] or "").strip()


# ── instructions (LLM, background, one dish at a time) ───────────────────
_INSTRUCTIONS_SYSTEM_PROMPT = (
    "You turn messy text scraped from a recipe webpage into clear cooking "
    "instructions. Rewrite the procedure in plain English, formatted as "
    "Markdown (e.g. a numbered list of steps), regardless of what language "
    "the source page is written in -- always translate to English, never "
    "leave any of it in the original language. Output ONLY the step-by-step "
    "procedure -- no title/heading, no ingredients list, no preamble, no "
    "code fences, no commentary about the source or the task."
)

_PROCESS_LOCK = threading.Lock()


def _call_llm_instructions(dish_name: str, page_text: str) -> str:
    """Returns "" on any failure (no key configured, network error, bad
    response) so the caller can treat it like "not ready yet" rather than
    crash the background worker."""
    if not OPENROUTER_KEY:
        return ""
    try:
        return _openrouter_chat([
            {"role": "system", "content": _INSTRUCTIONS_SYSTEM_PROMPT},
            {"role": "user", "content": f"Dish: {dish_name}\n\n{page_text[:_MAX_LLM_INPUT_CHARS]}"},
        ])
    except Exception:
        return ""


def _process_pending_instructions() -> None:
    """Repeatedly claims the oldest dish that has page_text but no
    instructions yet, and fills it in -- one dish, one LLM call, at a time
    (deliberately sequential, not parallel). If a worker is already running,
    this call is a no-op: the running one re-queries every iteration, so it
    will still pick up anything that becomes eligible while it works."""
    if not _PROCESS_LOCK.acquire(blocking=False):
        return
    # Dishes whose LLM call failed *this run* -- skipped so one stuck/broken
    # entry can't block every dish behind it forever; the next trigger (next
    # dish added, next restart) will give it another try from scratch.
    failed_ids: set[int] = set()
    try:
        while True:
            with connect() as conn:
                exclude = f"AND id NOT IN ({','.join('?' * len(failed_ids))}) " if failed_ids else ""
                row = conn.execute(
                    "SELECT id, name, page_text FROM food_dishes "
                    f"WHERE page_text != '' AND instructions = '' {exclude}"
                    "ORDER BY id LIMIT 1",
                    tuple(failed_ids),
                ).fetchone()
            if row is None:
                return
            instructions = _call_llm_instructions(row["name"], row["page_text"])
            if not instructions:
                failed_ids.add(row["id"])
                continue
            with connect() as conn:
                conn.execute(
                    "UPDATE food_dishes SET instructions = ? WHERE id = ?",
                    (instructions, row["id"]),
                )
                _bump_all(conn)
            _spawn_translations_processing()
    finally:
        _PROCESS_LOCK.release()


def _spawn_instructions_processing() -> None:
    threading.Thread(target=_process_pending_instructions, daemon=True).start()


def _validate_generated(text: str, known: set[str]) -> tuple[dict | None, list[str]]:
    """The model's answer (_INGREDIENTS_SYSTEM_PROMPT) against the ingredient
    list `known`: (recipe, []) when every ingredient is in the list or
    declared new, else (None, [reason, ...])."""
    try:
        data = json.loads(text)
    except Exception as e:
        return None, [f"not valid JSON ({e})"]
    if not isinstance(data, dict) or "new_ingredients" not in data:
        return None, ['top-level value must be a JSON object with the keys "new_ingredients", '
                      '"quantity", "unit", "ingredients"']
    new = data.pop("new_ingredients")
    recipe, errors = _validate_ingredients_json(json.dumps(data))
    if not isinstance(new, list) or not all(isinstance(n, str) for n in new):
        return None, errors + ['"new_ingredients" must be a JSON array of names ([] when there are none)']
    for name in new:
        if name in known:
            errors.append(f'"{name}" is already in the ingredient list -- use it; do not add it to "new_ingredients"')
    if recipe is None:
        return None, errors
    for name in recipe["ingredients"]:
        if name not in known and name not in new:
            errors.append(f'ingredient "{name}" is not in the ingredient list -- use the list\'s name for '
                          'it, or, if it is genuinely different to buy, add it to "new_ingredients"')
    for name in new:
        if name not in known and name not in recipe["ingredients"]:
            errors.append(f'new ingredient "{name}" is not used in "ingredients" -- drop it or use it')
    if errors:
        return None, errors
    return recipe, []


# ── ingredients (LLM, background, one dish at a time, strictly validated) ─
_INGREDIENTS_SYSTEM_PROMPT = (
    "You extract the ingredients of a recipe from messy text scraped from "
    "its webpage, for a shopping list. You are given the INGREDIENT LIST: "
    "every ingredient already known.\n\n"
    "Each of the recipe's ingredients that is the same thing to buy as an "
    "ingredient of the list IS that ingredient: use the list's name. Only one "
    "that is genuinely different to buy is new: give it a name and list it in "
    '"new_ingredients".\n\n'
    "Write each amount in the unit the recipe uses, one of these:\n"
    '  - weight: "mg", "g", "hg", "kg"\n'
    '  - volume: "ml", "cl", "l", "tsp", "tbsp", "cup", "glass", "coffee cup"\n'
    '  - "" for a number of whole pieces, as they are bought: 2 eggs, 1 lemon, '
    "1 onion, 1 bread roll.\n"
    "Never convert between weight, volume and pieces: \"2 tbsp sugar\" stays "
    "2 tbsp, \"1 onion\" stays 1 piece. Convert only units that are not in "
    "the lists above, into one of the same kind: pounds and ounces to g, "
    "fluid ounces and pints to ml, dl to cl. A count of a part of what is "
    "bought is a weight: 1 garlic clove = 5 g of garlic, 1 celery stalk = "
    "40 g of celery, 1 sprig of rosemary = 2 g. Round sensibly (150 g, not "
    "147.87 g).\n\n"
    "Output ONLY a single JSON object (no markdown fences, no commentary) "
    "with exactly this shape, the keys in this order:\n\n"
    '{"new_ingredients": ["<name>", ...], '
    '"quantity": "<number>", "unit": "<recipe yield unit, e.g. persons, '
    'servings -- lowercase>", "ingredients": {"<name>": '
    '{"quantity": "<number or empty string>", "unit": "<one of the units '
    'above>"}, ...}}\n\n'
    "Rules, all mandatory:\n"
    '- "new_ingredients" holds only names that are not in the list, each '
    "used in the recipe; [] when there are none.\n"
    "- Every name is in English whatever the page's language (\"onion\" not "
    '"cipolla"), lowercase and singular ("egg" not "eggs"), and the plain '
    "name it is bought under: no quality, brand or preparation words "
    '("olive oil" not "extra virgin olive oil", "tomato" not "chopped '
    'tomato", "parmesan" not "grated parmesan cheese"). Keep a word only '
    'when it names a different thing to buy ("cherry tomato", "red onion").\n'
    "- Name the product, not a part of it: \"celery\" not \"celery stalk\", "
    '"garlic" not "garlic clove", "parsley" not "parsley leaf". And '
    'not a whole category: the cheese, bean or pasta it actually is ("provola", '
    '"cannellini bean"), never just "cheese".\n'
    '- An ingredient\'s "quantity" is a plain number, or "" when the '
    'recipe gives no amount ("salt to taste"). Never a range, a fraction '
    "or text.\n"
    '- With no amount, both are "": {"quantity": "", "unit": ""}.\n'
    "- Do not include any text outside the JSON object."
)


def known_names(conn) -> set[str]:
    return {r["name"] for r in conn.execute("SELECT name FROM food_ingredients")}


def _generate_ingredients(dish_name: str, page_text: str, known: set[str]) -> dict | None:
    """Up to _MAX_INGREDIENT_ATTEMPTS attempts: each time the model's output
    fails validation, the invalid output and the specific reason are fed
    back so it can correct itself. A network/API failure is a different
    failure mode -- not worth retrying against, so it aborts immediately
    instead of spending the remaining attempts. Returns the recipe (the JSON
    shape above), or None if it never validated."""
    if not OPENROUTER_KEY:
        return None
    listing = "\n".join(sorted(known)) or "(empty -- every ingredient is new)"
    messages = [
        {"role": "system", "content": _INGREDIENTS_SYSTEM_PROMPT},
        {"role": "user", "content": f"INGREDIENT LIST:\n{listing}\n\n"
                                    f"Dish: {dish_name}\n\n{page_text[:_MAX_LLM_INPUT_CHARS]}"},
    ]
    for _attempt in range(_MAX_INGREDIENT_ATTEMPTS):
        try:
            raw = _openrouter_chat(messages)
        except Exception:
            return None
        recipe, errors = _validate_generated(raw, known)
        if recipe is not None:
            return recipe
        messages.append({"role": "assistant", "content": raw})
        bullets = "\n".join(f"- {e}" for e in errors)
        messages.append({
            "role": "user",
            "content": (
                "Your previous output was invalid for these reasons:\n"
                f"{bullets}\n\n"
                "Fix ALL of the problems listed above and output ONLY the corrected "
                "JSON object, following the exact structure and rules given. Recheck "
                "every ingredient, not just the ones named above -- a fix to one must "
                "not reintroduce a problem in another."
            ),
        })
    return None


_INGREDIENTS_LOCK = threading.Lock()
_NO_INGREDIENTS = "NOT EXISTS (SELECT 1 FROM food_dish_ingredients di WHERE di.dish_id = food_dishes.id)"


def _process_pending_ingredients() -> None:
    """Same shape as _process_pending_instructions -- one dish, one
    (possibly multi-attempt) generation, at a time; a worker already running
    makes this a no-op since it re-queries every iteration."""
    if not _INGREDIENTS_LOCK.acquire(blocking=False):
        return
    failed_ids: set[int] = set()
    try:
        while True:
            with connect() as conn:
                exclude = f"AND id NOT IN ({','.join('?' * len(failed_ids))}) " if failed_ids else ""
                row = conn.execute(
                    "SELECT id, name, page_text FROM food_dishes "
                    f"WHERE page_text != '' AND {_NO_INGREDIENTS} {exclude}"
                    "ORDER BY id LIMIT 1",
                    tuple(failed_ids),
                ).fetchone()
                # Read again for every dish: the one just done may have
                # added to it.
                known = known_names(conn)
            if row is None:
                return
            recipe = _generate_ingredients(row["name"], row["page_text"], known)
            if recipe is None:
                failed_ids.add(row["id"])
                continue
            with connect() as conn:
                # Its new ingredients join the list with it.
                _set_dish_ingredients(conn, row["id"], recipe)
                _bump_all(conn)
    finally:
        _INGREDIENTS_LOCK.release()


def _spawn_ingredients_processing() -> None:
    threading.Thread(target=_process_pending_ingredients, daemon=True).start()
