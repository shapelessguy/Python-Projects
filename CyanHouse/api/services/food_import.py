"""The recipe import: a dish's linked recipe page turned into its
ingredients, instructions (with their photos) and facts. It runs when a dish
is created with a recipe, when its recipe changes (food.py, _start_import),
and on Import / Retry.

One job a dish, on its own thread, its stage in food_dishes.import_state for
the clients to show:

  fetching     the page fetched again, and kept (food.fetch_recipe_page)
  reading      at once: the preparation cleaned of what isn't preparation
               (LLM, save_preparation), and the ingredient lines turned into
               ingredients of the list (LLM, save_ingredients)
  translating  at once: the instructions translated (food._translate), and
               their photos downloaded into the image store
  done / failed

What succeeds is saved even when another part fails -- "failed" lists what
did -- and Retry runs it all again.
"""
import json
import re
import secrets
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

from api.services import food

_CANDIDATES = 10  # the list's closest ingredients given with each line
_RUNNING: set[int] = set()
_RUNNING_LOCK = threading.Lock()


class ImportProblem(Exception):
    pass


# ── the job ──────────────────────────────────────────────────────────────
def start_after_commit(dish_id: int) -> None:
    """Run the import of a dish whose import_state the caller has just set to
    queued, once that is committed."""
    threading.Thread(target=_run, args=(dish_id,), daemon=True).start()


def _state(dish_id: int, state: dict) -> None:
    with food.connect() as conn:
        conn.execute("UPDATE food_dishes SET import_state = ? WHERE id = ?", (json.dumps(state), dish_id))
        food._bump_all(conn)


def _run(dish_id: int) -> None:
    with _RUNNING_LOCK:
        if dish_id in _RUNNING:
            return
        _RUNNING.add(dish_id)
    try:
        # Wait for the caller's transaction to commit the queued state -- a
        # dish just created isn't there at all until then.
        for _ in range(100):
            with food.connect() as conn:
                row = conn.execute("SELECT name, url, import_state FROM food_dishes WHERE id = ?",
                                   (dish_id,)).fetchone()
            if row is not None and json.loads(row["import_state"] or "{}").get("stage") == "queued":
                break
            time.sleep(0.1)
        else:
            return  # deleted, or it never came
        try:
            _import(dish_id, row["url"], row["name"])
        except Exception as e:  # nothing of it saved
            _state(dish_id, {"state": "failed", "errors": [str(e) or type(e).__name__]})
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(dish_id)


def _import(dish_id: int, url: str, name: str) -> None:
    errors: list[str] = []
    _state(dish_id, {"state": "running", "stage": "fetching"})
    food.fetch_recipe_page(url)
    with food.connect() as conn:
        page = conn.execute("SELECT preparation, json_ld, site_facts FROM food_recipe_pages WHERE url = ?",
                            (url,)).fetchone()
        known = _known(conn)
    recipe = food._recipe(json.loads(page["json_ld"]))
    steps = _mark_unmarked(json.loads(page["preparation"]))
    facts = _facts(url, recipe, json.loads(page["site_facts"] or "{}"))

    _state(dish_id, {"state": "running", "stage": "reading"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_steps = pool.submit(_clean_preparation, steps)
        f_ingredients = pool.submit(_ingredients, recipe, name, known)
    kept = f_steps.result()  # never fails: the steps as they were, at worst
    try:
        ingredients = f_ingredients.result()
    except (ImportProblem, food.TranslationError) as e:
        ingredients = None
        errors.append(f"ingredients: {e}")

    instructions, photos = None, None
    if kept:
        _state(dish_id, {"state": "running", "stage": "translating"})
        md, lang = _markdown(kept), _language(recipe)
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_tr = pool.submit(food._translate, "instructions", lang, "", md, {})
            f_photos = pool.submit(_download_photos, kept, name)
        photos, photo_errors = f_photos.result()
        errors += photo_errors
        try:
            instructions = {lang: md, **f_tr.result()}
        except food.TranslationError as e:
            errors.append(f"instructions: {e}")
            for f in set(photos.values()):
                food._forget_image(f)
            photos = None
    _save(dish_id, url, facts, ingredients, instructions, photos, errors)


def _save(dish_id: int, url: str, facts: dict, ingredients: dict | None,
          instructions: dict | None, photos: dict | None, errors: list[str]) -> None:
    with food.connect() as conn:
        row = conn.execute("SELECT url, photos FROM food_dishes WHERE id = ?", (dish_id,)).fetchone()
        if row is None or row["url"] != url:
            # Deleted, or given another recipe meanwhile (its own import runs).
            for f in set((photos or {}).values()):
                food._forget_image(f)
            return
        cols = {**facts, "import_url": url,
                "import_state": json.dumps({"state": "failed" if errors else "done", "errors": errors})}
        if instructions is not None:
            cols["instructions"] = instructions.get("en", "")
            cols["photos"] = json.dumps(photos or {})
        conn.execute(f"UPDATE food_dishes SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?",
                     (*cols.values(), dish_id))
        if instructions is not None:
            food._set_translations(conn, dish_id, "instructions", instructions)
            for f in set(json.loads(row["photos"] or "{}").values()) - set((photos or {}).values()):
                food._forget_image(f)
        if ingredients is not None:
            food._set_dish_ingredients(conn, dish_id, ingredients["data"])
            for ing_name, names in ingredients["new_names"].items():
                food.name_ingredient(conn, food._ingredient_id(conn, ing_name), names)
            conn.executemany(
                "INSERT OR REPLACE INTO food_ingredient_aliases (alias, ingredient_id) VALUES (?, ?)",
                [(alias, food._ingredient_id(conn, ing_name)) for alias, ing_name in ingredients["aliases"].items()
                 if alias])
        food._bump_all(conn)


# ── facts ────────────────────────────────────────────────────────────────
def _minutes(iso: str) -> int | None:
    """An ISO 8601 duration ("PT1H30M") in minutes; None for anything else."""
    m = re.match(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", iso or "")
    if not m or not any(m.groups()):
        return None
    d, h, mins = (int(x or 0) for x in m.groups())
    return d * 1440 + h * 60 + mins


def _facts(url: str, recipe: dict, site_facts: dict) -> dict:
    """The dish's facts (food._FACT_COLUMNS) and the site's rating and
    comments, off the page's schema.org Recipe and site_facts."""
    s = food._recipe_summary(url, recipe)
    return {
        "prep_min": _minutes(s["prep_time"]), "cook_min": _minutes(s["cook_time"]),
        "total_min": _minutes(s["total_time"]),
        "difficulty": site_facts.get("difficulty", "") if site_facts.get("difficulty") in food.DIFFICULTIES else "",
        "source_rating": s["rating"], "source_rating_count": s["rating_count"], "source_comments": s["comments"],
    }


def _language(recipe: dict) -> str:
    """The language the page is written in, one of food.LANGUAGES; Italian
    when it doesn't say (GialloZafferano is Italian)."""
    lang = food._ld_text(recipe.get("inLanguage"))[:2].lower()
    return lang if lang in food.LANGUAGES else "it"


# ── the preparation ──────────────────────────────────────────────────────
def _mark_unmarked(steps: list[dict]) -> list[dict]:
    """A photo the text doesn't point at (a blog's one photo a step) gets a
    number and a marker at its step's start, so it stays in its place."""
    used = [int(n) for st in steps for n in food.PHOTO_MARK_RE.findall(st["text"])]
    used += [n for st in steps for img in st["images"] for n in img["steps"]]
    n = max(used, default=0)
    for st in steps:
        marks = []
        for img in st["images"]:
            if not img["steps"]:
                n += 1
                img["steps"] = [n]
                marks.append(food.photo_mark(n))
        if marks:
            st["text"] = " ".join(marks) + " " + st["text"]
    return steps


_PREPARATION_SYSTEM_PROMPT = (
    "You are given the preparation steps of a recipe, as scraped from its "
    "web page. Some sentences in them are not preparation: an introduction to "
    "the dish, invitations to read other recipes, links, sign-offs, ads. Call "
    "save_preparation with the steps, keeping only the preparation.\n\n"
    "Copy every sentence you keep exactly as it is, word for word, with every "
    "marker like {{photo:3}} in it -- never reword, translate, reorder, merge "
    "or add anything. Leave out a step whose sentences are none of them "
    "preparation. Advice on making the dish (another pasta shape, how to keep "
    "it) is preparation: keep it."
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def _norm(text: str) -> str:
    return " ".join(text.split())


def _check_preparation(args: dict, steps: list[dict]) -> tuple[list[dict] | None, list[str]]:
    """The kept steps -- each its original's images that its text still
    points at -- or the reasons the answer won't do."""
    errors, kept, last = [], [], 0
    for item in args.get("steps") or []:
        try:
            n, text = int(item["step"]), str(item["text"]).strip()
        except (KeyError, TypeError, ValueError):
            errors.append("every kept step is {\"step\": its number, \"text\": its text}")
            continue
        if not 1 <= n <= len(steps) or n <= last:
            errors.append(f"step {n}: steps are the given numbers, once each, in order")
            continue
        last = n
        source = _norm(steps[n - 1]["text"])
        for sentence in _SENTENCE_SPLIT.split(_norm(text)):
            if sentence and sentence not in source:
                errors.append(f'step {n}: "{sentence[:80]}" is not word for word in the step -- copy, do not reword')
        marks = set(food.PHOTO_MARK_RE.findall(text))
        if not marks <= set(food.PHOTO_MARK_RE.findall(source)):
            errors.append(f"step {n}: a photo marker that the step does not have")
        images = [img for img in steps[n - 1]["images"] if {str(s) for s in img["steps"]} & marks]
        kept.append({"text": text, "images": images})
    if not kept and not errors:
        errors.append("keep at least the steps of the preparation")
    return (None, errors) if errors else (kept, [])


def _clean_preparation(steps: list[dict]) -> list[dict]:
    """The steps without what isn't preparation (the LLM, checked to have
    only left sentences out). The steps as they were when it can't."""
    if not steps or not food.OPENROUTER_KEY:
        return steps
    listing = "\n\n".join(f"STEP {i}:\n{st['text']}" for i, st in enumerate(steps, 1))
    tool = {"type": "function", "function": {
        "name": "save_preparation",
        "description": "Save the steps that are preparation.",
        "parameters": {"type": "object", "properties": {"steps": {"type": "array", "items": {
            "type": "object",
            "properties": {"step": {"type": "integer", "description": "its number as given"},
                           "text": {"type": "string", "description": "its sentences that are preparation, word for word"}},
            "required": ["step", "text"], "additionalProperties": False}}},
            "required": ["steps"], "additionalProperties": False},
    }}
    messages = [{"role": "system", "content": _PREPARATION_SYSTEM_PROMPT}, {"role": "user", "content": listing}]
    for _attempt in range(2):
        try:
            args = _call_tool(messages, tool)
        except ImportProblem:
            return steps
        kept, errors = _check_preparation(args, steps)
        if kept is not None:
            return kept
        messages += [{"role": "assistant", "content": json.dumps(args, ensure_ascii=False)},
                     {"role": "user", "content": _fix_these(errors)}]
    return steps


def _markdown(steps: list[dict]) -> str:
    """The steps as a numbered Markdown list, a step's paragraphs in its item."""
    items = []
    for i, st in enumerate(steps, 1):
        paras = [p.strip() for p in st["text"].split("\n\n") if p.strip()]
        items.append(f"{i}. " + "\n\n   ".join(paras))
    return "\n\n".join(items)


def _download_photos(steps: list[dict], name: str) -> tuple[dict[str, str], list[str]]:
    """The kept steps' photos into the image store, at once: ({"N": file}
    for every number a photo shows, [what couldn't be downloaded])."""
    numbers: dict[str, list[int]] = {}
    for st in steps:
        for img in st["images"]:
            numbers.setdefault(img["url"], []).extend(img["steps"])

    def get(url: str) -> str:
        resp = food._public_get(url, timeout=20)
        resp.raise_for_status()
        fname = f"{food._slug(name)}-step-{secrets.token_hex(4)}{food._ext_for(resp.headers.get('content-type', ''), url)}"
        (food.FOOD_IMAGES_DIR / fname).write_bytes(resp.content)
        return fname

    photos, errors = {}, []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {url: pool.submit(get, url) for url in numbers}
    for url, f in futures.items():
        try:
            fname = f.result()
        except Exception as e:
            errors.append(f"photo {', '.join(map(str, numbers[url]))}: {e}")
            continue
        for n in numbers[url]:
            photos[str(n)] = fname
    return photos, errors


# ── the ingredients ──────────────────────────────────────────────────────
# Words of an ingredient line that say how much or how, not what: left out
# when it is compared with the ingredient list's names (_core).
_NOISE = set("""
g gr kg hg mg ml cl dl l lt q b qb oz lb tsp tbsp cup cups grams gram teaspoon teaspoons tablespoon tablespoons
di del della dello dei degli delle d da al alla allo alle agli ai e ed con per in the of and a an to taste
fino grosso grossa dop igp fresco fresca freschi fresche extravergine circa
cucchiaio cucchiai cucchiaino cucchiaini ciuffo ciuffi foglia foglie spicchio spicchi rametto rametti
pizzico bicchiere bicchieri tazza tazze tazzina tazzine pezzo pezzi fetta fette mazzetto costa coste
""".split())


def _core(text: str) -> str:
    """An ingredient line or name as compared: lowercase, no accents, no
    parentheses, amounts or _NOISE -- "Cipolle dorate 1,5 kg" -> "cipolle dorate"."""
    s = unicodedata.normalize("NFKD", text.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z]+", " ", s)
    return " ".join(w for w in s.split() if w not in _NOISE and len(w) > 1)


def _score(a: str, b: str) -> float:
    """How alike two _core'd names are, by their letters: as a whole, or by
    their closest pair of words ("cipolle dorate" ~ "cipolla")."""
    if not a or not b:
        return 0.0
    whole = SequenceMatcher(None, a, b).ratio()
    words = max(SequenceMatcher(None, x, y).ratio() for x in a.split() for y in b.split())
    return max(whole, 0.9 * words)


def _known(conn) -> dict:
    """The ingredient list as the import compares lines with it: id -> its
    English name and other languages' names, and the aliases."""
    known = {r["id"]: {"name": r["name"], "names": {}} for r in conn.execute("SELECT id, name FROM food_ingredients")}
    for r in conn.execute("SELECT ingredient_id, lang, name FROM food_ingredient_names"):
        if r["ingredient_id"] in known:
            known[r["ingredient_id"]]["names"][r["lang"]] = r["name"]
    aliases = {r["alias"]: r["ingredient_id"] for r in conn.execute("SELECT alias, ingredient_id FROM food_ingredient_aliases")}
    return {"ingredients": known, "aliases": aliases}


def _candidates(line: str, known: dict) -> tuple[list[int], int | None]:
    """The list's _CANDIDATES ingredients closest to a line, best first, and
    the one an alias says it is (None for none)."""
    core = _core(line)
    alias = known["aliases"].get(core)
    best: dict[int, float] = {}
    for iid, ing in known["ingredients"].items():
        variants = [ing["name"], *ing["names"].values()]
        best[iid] = max(_score(core, _core(v)) for v in variants)
    for a, iid in known["aliases"].items():
        if iid in best:
            best[iid] = max(best[iid], _score(core, a))
    if alias in best:
        best[alias] = 2.0
    ranked = sorted(best, key=lambda i: -best[i])[:_CANDIDATES]
    return ranked, alias if alias in best else None


def _label(ing: dict) -> str:
    others = [ing["names"][lang] for lang in food.LANGUAGES if lang != "en" and lang in ing["names"]]
    return ing["name"] + (f" ({' / '.join(others)})" if others else "")


_INGREDIENTS_REASONING = {"effort": "low"}

_INGREDIENTS_SYSTEM_PROMPT = (
    "You turn the ingredient lines of a recipe page into the ingredients of a "
    "shopping list. You get the INGREDIENT LIST -- every ingredient already "
    "known, by its English name with its names in other languages -- and the "
    "recipe's lines, each with the list's closest ingredients. Call "
    "save_ingredients.\n\n"
    "For every line that is an ingredient (leave out headings like \"Per la salsa:\"):\n"
    "- name: when it is the same thing to buy as an ingredient of the list, that "
    "ingredient's English name exactly, new false -- look first at the closest "
    "ones given with the line; one marked \"matched before\" is what that line "
    "turned out to be last time. Only an ingredient genuinely different to buy "
    "is new: new true, its English name, and its name in each other language "
    "({other_names}).\n"
    "- Every name: English, lowercase, singular, the plain name it is bought "
    "under -- no quality, brand or preparation words (\"olive oil\" not \"extra "
    "virgin olive oil\", \"tomato\" not \"chopped tomato\", \"parmesan\" not "
    "\"grated parmesan\"); keep a word only when it names a different thing to "
    "buy (\"cherry tomato\", \"red onion\"). The product, not a part of it "
    "(\"garlic\" not \"garlic clove\", \"celery\" not \"celery stalk\"), and not a "
    "whole category (\"provola\", never just \"cheese\").\n"
    "- quantity: a plain number with a dot for decimals (\"1.5\"), or \"\" when "
    "the line gives no amount (\"q.b.\", \"to taste\").\n"
    "- unit: the line's own unit when it is one of the allowed ones. A unit "
    "that isn't becomes one of the same kind: pounds and ounces g, fluid ounces "
    "and pints ml, dl cl. A number of whole things as they are bought is pieces, "
    "unit \"\" (2 eggs, 1 lemon). A number of a part of what is bought is its "
    "weight in g, estimated: 1 garlic clove 5 g, 1 celery stalk 40 g, 1 sprig of "
    "rosemary 2 g, 1 bunch of parsley 10 g, 1 bay leaf 0.5 g. Never convert "
    "between weight and volume (\"150 g vino bianco\" stays 150 g). With no "
    "amount, unit \"\" too.\n"
    "- line: the line's number.\n"
    "yield_quantity: how much the recipe makes, a plain number; yield_unit: "
    "what that counts, English, lowercase (\"persons\", \"servings\", \"pieces\") "
    "-- \"persons\" when the page gives just a number."
)


def _ingredients(recipe: dict, dish_name: str, known: dict) -> dict:
    """The recipe's ingredient lines as the dish's ingredients (LLM, checked,
    one retry with every error): {"data": the JSON shape of
    food._validate_ingredients_json, "new_names": new ingredient -> lang ->
    name, "aliases": _core(line) -> ingredient name}. Raises ImportProblem."""
    lines = [food._clean(str(i)) for i in recipe.get("recipeIngredient") or [] if str(i).strip()]
    if not lines:
        raise ImportProblem("the recipe page lists no ingredients")
    others = [lang for lang in food.LANGUAGES if lang != "en"]
    ings = known["ingredients"]
    parts = [f"DISH: {dish_name}", f"RECIPE YIELD: {food._ld_text(recipe.get('recipeYield')) or '(not given)'}",
             "INGREDIENT LIST:\n" + ("\n".join(_label(i) for i in sorted(ings.values(), key=lambda i: i["name"]))
                                     or "(empty -- every ingredient is new)")]
    listing = []
    for n, line in enumerate(lines, 1):
        ranked, alias = _candidates(line, known)
        closest = ", ".join(_label(ings[i]) + (" -- matched before" if i == alias else "") for i in ranked)
        listing.append(f"{n}. {line}\n   closest: {closest or '(none)'}")
    parts.append("LINES:\n" + "\n".join(listing))
    item = {"line": {"type": "integer"}, "name": {"type": "string"}, "quantity": {"type": "string"},
            "unit": {"type": "string", "enum": list(food.UNITS)}, "new": {"type": "boolean"},
            **{f"name_{lang}": {"type": "string", "description": f"a new one's name in {food.LANGUAGES[lang]}"}
               for lang in others}}
    tool = {"type": "function", "function": {
        "name": "save_ingredients",
        "description": "Save the recipe's ingredients.",
        "parameters": {"type": "object", "properties": {
            "yield_quantity": {"type": "string"}, "yield_unit": {"type": "string"},
            "ingredients": {"type": "array", "items": {"type": "object", "properties": item,
                                                       "required": ["line", "name", "quantity", "unit", "new"],
                                                       "additionalProperties": False}}},
            "required": ["yield_quantity", "yield_unit", "ingredients"], "additionalProperties": False},
    }}
    prompt = _INGREDIENTS_SYSTEM_PROMPT.replace("{other_names}", ", ".join(f"name_{lang}" for lang in others))
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": "\n\n".join(parts)}]
    names = {i["name"] for i in ings.values()}
    errors: list[str] = []
    for _attempt in range(2):
        # A little reasoning: telling what a line is to buy, and a part's
        # weight, is where a model would otherwise make things up.
        args = _call_tool(messages, tool, _INGREDIENTS_REASONING)
        result, errors = _check_ingredients(args, lines, names, others)
        if result is not None:
            return result
        messages += [{"role": "assistant", "content": json.dumps(args, ensure_ascii=False)},
                     {"role": "user", "content": _fix_these(errors)}]
    raise ImportProblem("; ".join(errors[:5]))


def _check_ingredients(args: dict, lines: list[str], names: set[str], others: list[str]):
    """save_ingredients' answer as the import's result, or (None, every reason
    it won't do). Two lines of one ingredient are added up."""
    errors: list[str] = []
    yq, yu = str(args.get("yield_quantity", "")).strip().replace(",", "."), str(args.get("yield_unit", "")).strip().lower()
    if not food._PLAIN_NUMBER_RE.match(yq):
        errors.append('"yield_quantity" is a plain number, e.g. "4"')
    if not food._LOWER_WORD_RE.match(yu):
        errors.append('"yield_unit" is lowercase English word(s), e.g. "persons"')
    out: dict[str, dict] = {}
    new_names: dict[str, dict] = {}
    aliases: dict[str, str] = {}
    seen: set[int] = set()
    for it in args.get("ingredients") or []:
        try:
            n, name = int(it["line"]), str(it["name"]).strip().lower()
            qty, unit, new = str(it["quantity"]).strip().replace(",", "."), str(it["unit"]), bool(it["new"])
        except (KeyError, TypeError, ValueError):
            errors.append("every ingredient has line, name, quantity, unit and new")
            continue
        where = f'line {n} ("{lines[n - 1]}")' if 1 <= n <= len(lines) else f"line {n}"
        if not 1 <= n <= len(lines) or n in seen:
            errors.append(f"{where}: lines are the given numbers, once each")
            continue
        seen.add(n)
        if not food._LOWER_WORD_RE.match(name):
            errors.append(f'{where}: the name "{name}" is lowercase English word(s)')
            continue
        if qty and not food._PLAIN_NUMBER_RE.match(qty):
            errors.append(f'{where}: the quantity "{qty}" is a plain number, or ""')
            continue
        if unit not in food.UNITS:
            errors.append(f'{where}: the unit "{unit}" is not one of the allowed ones')
            continue
        if unit and not qty:
            errors.append(f'{where}: a unit but no quantity -- with no amount, both are ""')
            continue
        if new and name in names:
            errors.append(f'{where}: "{name}" is in the ingredient list -- new is false')
            continue
        if not new and name not in names:
            errors.append(f'{where}: "{name}" is not in the ingredient list -- use its name there, '
                          'or, if it is genuinely different to buy, new true with its other names')
            continue
        if new:
            # Names it left out are filled in by the translation worker.
            new_names[name] = {lang: str(it.get(f"name_{lang}", "")).strip() for lang in others}
        aliases[_core(lines[n - 1])] = name
        have = out.get(name)
        if have is None or not have["quantity"]:
            out[name] = {"quantity": qty, "unit": unit if qty else ""}
        elif qty:
            (m1, f1), (m2, f2) = food.UNITS[have["unit"]], food.UNITS[unit]
            if m1 != m2:
                errors.append(f'{where}: "{name}" is on another line too, in a unit of another kind -- give both one')
                continue
            have["quantity"] = food._fmt_qty(float(have["quantity"]) + float(qty) * f2 / f1)
    if not out and not errors:
        errors.append("the recipe has ingredients: save them")
    if errors:
        return None, errors
    return {"data": {"quantity": yq, "unit": yu, "ingredients": out}, "new_names": new_names, "aliases": aliases}, []


# ── a hand edit's ingredient names ───────────────────────────────────────
_RESOLVE_SYSTEM_PROMPT = (
    "Someone typed ingredient names into a recipe by hand. You check them "
    "against the INGREDIENT LIST -- every ingredient known, by its English "
    "name with its names in other languages; each typed name comes with the "
    "list's closest ingredients. Call resolve_ingredients with every typed "
    "name.\n\n"
    "- match: when the typed name means the same thing to buy as an "
    "ingredient of the list -- a typo, a plural, another language, a synonym "
    "-- that ingredient's English name exactly. Only the same product: a "
    "different one is never matched, however close (\"red onion\" is not "
    "\"onion\", \"guanciale\" is not \"bacon\", \"cherry tomato\" is not "
    "\"tomato\").\n"
    "- Otherwise match \"\", and name: the plain English name it is bought "
    "under -- lowercase, singular, no quality or preparation words -- with "
    "its name in each other language ({other_names})."
)


def resolve_names(typed: list[str]) -> dict[str, dict]:
    """Names typed into a dish's ingredients that aren't in the list, as
    what they turn out to be: typed -> {"name": the list's ingredient, or a
    new one's English name, "new_names": a new one's other languages' names
    (None for one of the list), "alias": _core(typed)}. An alias or another
    language's name of the list settles one in Python; the rest are asked
    of the model (a little reasoning). Left as typed when it can't say."""
    with food.connect() as conn:
        known = _known(conn)
    ings = known["ingredients"]
    out: dict[str, dict] = {}
    ask = []
    for t in typed:
        core = _core(t)
        iid = known["aliases"].get(core) or next(
            (i for i, ing in ings.items() if core and core in {_core(v) for v in ing["names"].values()}), None)
        if iid in ings:
            out[t] = {"name": ings[iid]["name"], "new_names": None}
        else:
            ask.append(t)
    if ask:
        try:
            out.update(_resolve_by_model(ask, known))
        except ImportProblem:
            pass
    for t in typed:
        out.setdefault(t, {"name": t, "new_names": None})
        out[t]["alias"] = _core(t)
    return out


def _resolve_by_model(typed: list[str], known: dict) -> dict[str, dict]:
    ings = known["ingredients"]
    names = {i["name"] for i in ings.values()}
    others = [lang for lang in food.LANGUAGES if lang != "en"]
    listing = []
    for t in typed:
        ranked, _alias = _candidates(t, known)
        listing.append(f'"{t}" -- closest: {", ".join(_label(ings[i]) for i in ranked) or "(none)"}')
    parts = ["INGREDIENT LIST:\n" + ("\n".join(_label(i) for i in sorted(ings.values(), key=lambda i: i["name"]))
                                    or "(empty)"),
             "TYPED NAMES:\n" + "\n".join(listing)]
    item = {"typed": {"type": "string"}, "match": {"type": "string"}, "name": {"type": "string"},
            **{f"name_{lang}": {"type": "string"} for lang in others}}
    tool = {"type": "function", "function": {
        "name": "resolve_ingredients",
        "description": "What each typed name is.",
        "parameters": {"type": "object", "properties": {"ingredients": {"type": "array", "items": {
            "type": "object", "properties": item, "required": ["typed", "match"], "additionalProperties": False}}},
            "required": ["ingredients"], "additionalProperties": False},
    }}
    prompt = _RESOLVE_SYSTEM_PROMPT.replace("{other_names}", ", ".join(f"name_{lang}" for lang in others))
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": "\n\n".join(parts)}]
    errors: list[str] = []
    for _attempt in range(2):
        args = _call_tool(messages, tool, _INGREDIENTS_REASONING)
        out, errors = {}, []
        for it in args.get("ingredients") or []:
            t = str(it.get("typed", ""))
            if t not in typed or t in out:
                errors.append(f'"{t}": answer each typed name once, exactly as given')
                continue
            match = str(it.get("match", "")).strip().lower()
            name = match or str(it.get("name", "")).strip().lower()
            if match and match not in names:
                errors.append(f'"{t}": match "{match}" is not in the ingredient list -- its exact name, or ""')
            elif not food._LOWER_WORD_RE.match(name):
                errors.append(f'"{t}": a new one has its English name, lowercase word(s)')
            elif name in names:
                out[t] = {"name": name, "new_names": None}
            else:
                out[t] = {"name": name, "new_names": {lang: str(it.get(f"name_{lang}", "")).strip() for lang in others}}
        errors += [f'"{t}": not answered' for t in typed if t not in out]
        if not errors:
            return out
        messages += [{"role": "assistant", "content": json.dumps(args, ensure_ascii=False)},
                     {"role": "user", "content": _fix_these(errors)}]
    raise ImportProblem("; ".join(errors[:5]))


# ── the model ────────────────────────────────────────────────────────────
def _call_tool(messages: list[dict], tool: dict, reasoning: dict | None = None) -> dict:
    """The arguments of the model's call of `tool`, forced; `reasoning` as
    OpenRouter takes it, none by default. Raises ImportProblem when it can't
    be had."""
    if not food.OPENROUTER_KEY:
        raise ImportProblem("no LLM key configured")
    try:
        msg = food._openrouter(messages, tools=[tool], reasoning=reasoning or {"enabled": False},
                               tool_choice={"type": "function", "function": {"name": tool["function"]["name"]}})
        return json.loads(msg["tool_calls"][0]["function"]["arguments"])
    except Exception as e:
        raise ImportProblem(f"the model's answer couldn't be had: {e}")


def _fix_these(errors: list[str]) -> str:
    return ("Your answer has these problems:\n" + "\n".join(f"- {e}" for e in errors) +
            "\n\nFix all of them and call the tool again with the whole corrected answer -- recheck "
            "everything, not just what is named above.")
