"""The recipe import: a dish's linked recipe page turned into its
ingredients, instructions (with their photos) and facts. It runs when a dish
is created with a recipe, when its recipe changes (food.py, _start_import),
and on Import / Retry.

One job a dish, on its own thread, its stage in food_dishes.import_state for
the clients to show:

  fetching     the page fetched again, and kept (food.fetch_recipe_page)
  splitting    the recipe looked at for sub-recipes (LLM, save_split): a
               cheesecake's topping, a lasagne's ragù. When it has some it
               waits ("choosing") for who imported it to pick which become
               dishes of their own (food.choose_split); each one picked is
               then read and translated like the rest, and the dish uses it
  reading      at once: the preparation cleaned of what isn't preparation
               (LLM, save_preparation), and the ingredient lines turned into
               ingredients of the list (LLM, save_ingredients)
  translating  at once: the instructions written in every language, in the
               house style (LLM, save_instructions -- the page's own
               language too, so whatever it was written in), and their
               photos downloaded into the image store
  done / failed

What succeeds is saved even when another part fails -- "failed" lists what
did -- and Retry runs it all again (the sub-recipes asked about again).
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
        st = json.loads(row["import_state"] or "{}")
        resume = {"plan": st["plan"], "keep": st["keep"]} if "plan" in st else None
        try:
            _import(dish_id, row["url"], row["name"], resume)
        except Exception as e:  # nothing of it saved
            _state(dish_id, {"state": "failed", "errors": [str(e) or type(e).__name__]})
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(dish_id)


def _import(dish_id: int, url: str, name: str, resume: dict | None = None) -> None:
    """The whole import -- or, `resume`d, from the sub-recipes picked on."""
    errors: list[str] = []
    started = time.monotonic()
    if resume is None:
        _state(dish_id, {"state": "running", "stage": "fetching"})
        food.fetch_recipe_page(url)
    with food.connect() as conn:
        page = conn.execute("SELECT preparation, json_ld, site_facts FROM food_recipe_pages WHERE url = ?",
                            (url,)).fetchone()
        known = _known(conn)
    if page is None:
        raise ImportProblem("the recipe page is gone -- import it again")
    recipe = food._recipe(json.loads(page["json_ld"]))
    steps = _number_unmarked(json.loads(page["preparation"]))
    facts = _facts(url, recipe, json.loads(page["site_facts"] or "{}"))

    if resume is None:
        _state(dish_id, {"state": "running", "stage": "splitting"})
        plan = _plan_split(dish_id, name, recipe, steps)
        if plan["parts"]:
            _state(dish_id, {"state": "choosing", "stage": "splitting", "plan": plan,
                             "parts": [{"name": p["name"]["en"], "name_tr": {k: v for k, v in p["name"].items() if k != "en"},
                                        "existing": p["existing"]} for p in plan["parts"]]})
            print(f"[food import] dish {dish_id} ({name}): {len(plan['parts'])} sub-recipe(s) proposed")
            return
        resume = {"plan": plan, "keep": []}
    main, subs, linked = _pieces(resume["plan"], resume["keep"], steps)
    # What the dish is now made with, apart: named in its instructions.
    uses = [p["name"] for p in subs]
    with food.connect() as conn:
        uses += [food._texts(conn, cid, "name") for cid in linked]

    # Every dish made out of the recipe, read and translated alike: this
    # one first, then the sub-recipes picked.
    pieces = [{"name": name, "lines": main["lines"], "steps": main["steps"]}] + [
        {"name": p["name"]["en"], "names": p["name"], "lines": p["lines"], "steps": p["steps"],
         "weight_g": p["weight_g"]} for p in subs]
    _state(dish_id, {"state": "running", "stage": "reading"})
    with ThreadPoolExecutor(max_workers=2 * len(pieces)) as pool:
        f_steps = [pool.submit(_clean_preparation, pc["steps"]) for pc in pieces]
        f_ings = [pool.submit(_ingredients, {**recipe, "recipeIngredient": pc["lines"]}, pc["name"], known)
                  for pc in pieces]
    for pc, fs, fi in zip(pieces, f_steps, f_ings):
        pc["kept"] = fs.result()  # never fails: the steps as they were, at worst
        pc["errors"] = []
        try:
            pc["ingredients"] = fi.result()
        except (ImportProblem, food.TranslationError) as e:
            pc["ingredients"] = None
            pc["errors"].append(f"ingredients: {e}")
        pc["instructions"], pc["photos"] = None, None

    todo = [pc for pc in pieces if pc["kept"]]
    if todo:
        _state(dish_id, {"state": "running", "stage": "translating"})
        with ThreadPoolExecutor(max_workers=2 * len(todo)) as pool:
            f_tr = [pool.submit(_write_instructions, pc["kept"], uses if pc is pieces[0] else None) for pc in todo]
            f_photos = [pool.submit(_download_photos, pc["kept"], pc["name"]) for pc in todo]
        for pc, ft, fp in zip(todo, f_tr, f_photos):
            pc["photos"], photo_errors = fp.result()
            pc["errors"] += photo_errors
            try:
                pc["instructions"] = ft.result()
            except ImportProblem as e:
                pc["errors"].append(f"instructions: {e}")
                for f in set(pc["photos"].values()):
                    food._forget_image(f)
                pc["photos"] = None
    errors = pieces[0]["errors"] + [f'{pc["name"]}: {e}' for pc in pieces[1:] for e in pc["errors"]]
    head = pieces[0]
    _save(dish_id, url, facts, head["ingredients"], head["instructions"], head["photos"], errors,
          {"subs": pieces[1:], "linked": linked, "matched": [p["existing"] for p in resume["plan"]["parts"]
                                                             if p["existing"]]})
    print(f"[food import] dish {dish_id} ({name}): done in {time.monotonic() - started:.1f}s"
          + (f", {len(pieces) - 1} sub-recipe(s)" if len(pieces) > 1 else "")
          + (f", {len(errors)} error(s)" if errors else ""))


def _save(dish_id: int, url: str, facts: dict, ingredients: dict | None,
          instructions: dict | None, photos: dict | None, errors: list[str], split: dict | None = None) -> None:
    """The import's dish saved, and with `split` ({"subs": the sub-recipes
    made into dishes, as _import has them; "linked": existing dish -> how
    many grams of it; "matched": the existing dishes the split named}) the new
    dishes too, the dish using them and the ones linked."""
    split = split or {"subs": [], "linked": {}, "matched": []}
    with food.connect() as conn:
        row = conn.execute("SELECT url, photos, category_id FROM food_dishes WHERE id = ?", (dish_id,)).fetchone()
        if row is None or row["url"] != url:
            # Deleted, or given another recipe meanwhile (its own import runs).
            for f in set((photos or {}).values()) | {f for sub in split["subs"] for f in (sub["photos"] or {}).values()}:
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
            # A yield unit new to the dish loses its translations: the
            # worker gives it new ones.
            food._set_dish_ingredients(conn, dish_id, ingredients["data"])
            _save_names(conn, ingredients)
        if split["subs"] or split["matched"]:
            # The dishes it uses: the ones it did, but those the split named
            # (they are linked again if picked), and the ones made now.
            comps = {r["component_id"]: r["quantity"] for r in conn.execute(
                "SELECT component_id, quantity FROM food_dish_components WHERE dish_id = ? ORDER BY position",
                (dish_id,)) if r["component_id"] not in split["matched"]}
            usable = food.usable_components(conn, dish_id)
            for cid, grams in split["linked"].items():
                if cid in usable:
                    comps[cid] = food._fmt_qty(grams)
            for sub in split["subs"]:
                # All of it, as its own lines weigh -- the estimate when
                # they can't tell.
                new_id = _new_dish(conn, sub, row["category_id"])
                comps[new_id] = food._fmt_qty(food.dish_grams(conn, new_id) or sub["weight_g"])
            food._set_components(conn, dish_id, comps)
        food._bump_all(conn)
    if ingredients is not None or split["subs"]:
        food._spawn_translations_processing()


def _save_names(conn, ingredients: dict) -> None:
    """The new ingredients' names and the lines' aliases an ingredients
    answer (_ingredients) came with."""
    for ing_name, names in ingredients["new_names"].items():
        food.name_ingredient(conn, food._ingredient_id(conn, ing_name), names)
    conn.executemany(
        "INSERT OR REPLACE INTO food_ingredient_aliases (alias, ingredient_id) VALUES (?, ?)",
        [(alias, food._ingredient_id(conn, ing_name)) for alias, ing_name in ingredients["aliases"].items()
         if alias])


def _new_dish(conn, sub: dict, category_id: int | None) -> int:
    """A sub-recipe made a dish of its own, in that category, with no picture
    and no recipe link of its own (what failed of it is in the import's
    errors); its id."""
    pos = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM food_dishes WHERE category_id IS ?",
                       (category_id,)).fetchone()[0]
    ins = sub["instructions"] or {}
    new_id = conn.execute(
        "INSERT INTO food_dishes (name, category_id, position, instructions, photos) VALUES (?, ?, ?, ?, ?)",
        (sub["names"]["en"], category_id, pos, ins.get("en", ""), json.dumps(sub["photos"] or {})),
    ).lastrowid
    food._set_translations(conn, new_id, "name", sub["names"])
    if ins:
        food._set_translations(conn, new_id, "instructions", ins)
    if sub["ingredients"]:
        food._set_dish_ingredients(conn, new_id, sub["ingredients"]["data"])
        _save_names(conn, sub["ingredients"])
    return new_id


# ── sub-recipes ──────────────────────────────────────────────────────────
_SPLIT_SYSTEM_PROMPT = (
    "You are given a recipe: its dish, its ingredient lines and its "
    "preparation, sentence by sentence, each numbered. Some recipes are made "
    "of sub-recipes -- preparations of their own, that could be made apart or "
    "swapped for another: a cheesecake's base and its topping, a lasagne's "
    "ragù and its béchamel, a tart's pastry and its filling, a sauce, a dough, "
    "a cream. Call save_split with those sub-recipes as its parts, leaving out "
    "the main one: the main one is the dish itself -- the sub-recipe that is "
    "most of it (the cheesecake's base) with the assembling, cooking and "
    "serving -- and it keeps every line and sentence not given to a part.\n\n"
    "Give no parts at all when the recipe is one preparation. An ingredient "
    "on its own (grated cheese on top), a garnish, a decoration or the "
    "assembling is never a part. For each part:\n"
    "- its name as a dish's, in English, Italian and German (\"Cheesecake "
    "topping\", \"Copertura per cheesecake\", \"Cheesecake-Topping\");\n"
    "- lines: the ingredient lines it uses; a line belongs to one part at "
    "most -- shared by two, to the one using more of it;\n"
    "- sentences: the sentences that make it, one part at most each; those "
    "putting the parts together stay with the main one;\n"
    "- existing: when it is the same preparation as one of the EXISTING "
    "DISHES (the same thing to make, however written), that dish's id -- "
    "else 0;\n"
    "- weight_g: what its lines make weighs in grams, as much as this recipe "
    "uses, estimated as a cook would (pieces and spoons included).\n"
    "The main one keeps at least one line."
)


def _units(steps: list[dict]) -> list[dict]:
    """The steps' sentences, in order: {"step": its index, "para": its
    paragraph's in the step, "text"}."""
    out = []
    for si, st in enumerate(steps):
        paras = [p for p in st["text"].split("\n\n") if p.strip()]
        for pi, para in enumerate(paras):
            out.extend({"step": si, "para": pi, "text": t} for t in _SENTENCE_SPLIT.split(_norm(para)) if t)
    return out


def _plan_split(dish_id: int, name: str, recipe: dict, steps: list[dict]) -> dict:
    """The recipe's sub-recipes (LLM, checked, one retry): {"lines": its
    ingredient lines, "units": its sentences (_units), "parts": [{"name":
    lang -> name, "existing": a dish's id or 0, "lines", "sentences": their
    indices, "weight_g"}]} -- no parts when it has none, or when they can't
    be had (the import goes on with the recipe whole)."""
    lines = [food._clean(str(i)) for i in recipe.get("recipeIngredient") or [] if str(i).strip()]
    units = _units(steps)
    plan = {"lines": lines, "units": units, "parts": []}
    if len(lines) < 2 or not units or not food.OPENROUTER_KEY:
        return plan
    with food.connect() as conn:
        usable = food.usable_components(conn, dish_id)
        others = []
        for r in conn.execute("SELECT id, name FROM food_dishes ORDER BY name").fetchall():
            if r["id"] in usable:
                ings = [x["name"] for x in conn.execute(
                    "SELECT i.name FROM food_dish_ingredients di JOIN food_ingredients i ON i.id = di.ingredient_id "
                    "WHERE di.dish_id = ? ORDER BY di.position", (r["id"],))]
                others.append(f"{r['id']}. {r['name']}" + (f": {', '.join(ings)}" if ings else ""))
    listing, last = [], None
    for n, u in enumerate(units, 1):
        if u["step"] != last:
            listing.append(f"STEP {u['step'] + 1}:")
            last = u["step"]
        listing.append(f"  [{n}] {u['text']}")
    parts = [f"DISH: {name}",
             "EXISTING DISHES:\n" + ("\n".join(others) or "(none)"),
             "INGREDIENT LINES:\n" + "\n".join(f"{n}. {line}" for n, line in enumerate(lines, 1)),
             "PREPARATION:\n" + "\n".join(listing)]
    item = {**{f"name_{lang}": {"type": "string"} for lang in food.LANGUAGES},
            "lines": {"type": "array", "items": {"type": "integer"}},
            "sentences": {"type": "array", "items": {"type": "integer"}},
            "existing": {"type": "integer"}, "weight_g": {"type": "number"}}
    tool = {"type": "function", "function": {
        "name": "save_split",
        "description": "Save the recipe's sub-recipes other than the main one (none for a recipe of one).",
        "parameters": {"type": "object", "properties": {"parts": {"type": "array", "items": {
            "type": "object", "properties": item, "required": list(item), "additionalProperties": False}}},
            "required": ["parts"], "additionalProperties": False},
    }}
    messages = [{"role": "system", "content": _SPLIT_SYSTEM_PROMPT}, {"role": "user", "content": "\n\n".join(parts)}]
    for _attempt in range(2):
        try:
            args = _call_tool(messages, tool)
        except ImportProblem as e:
            print(f"[food import] no sub-recipes looked for: {e}")
            return plan
        found, errors = _check_split(args, len(lines), len(units), usable)
        if found is not None:
            return {**plan, "parts": found}
        print(f"[food import] split answer rejected: {'; '.join(errors[:3])}")
        messages += [{"role": "assistant", "content": json.dumps(args, ensure_ascii=False)},
                     {"role": "user", "content": _fix_these(errors)}]
    return plan


def _check_split(args: dict, n_lines: int, n_units: int, usable: set[int]) -> tuple[list[dict] | None, list[str]]:
    """The parts of a save_split answer, or what is wrong with it."""
    errors, out = [], []
    seen_lines, seen_units, seen_dishes = set(), set(), set()
    for k, p in enumerate(args.get("parts") or [], 1):
        try:
            names = {lang: str(p[f"name_{lang}"]).strip() for lang in food.LANGUAGES}
            lines, units = [int(x) for x in p["lines"]], [int(x) for x in p["sentences"]]
            existing, weight = int(p["existing"]), float(p["weight_g"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"part {k}: give every field, of its type")
            continue
        if not all(names.values()):
            errors.append(f"part {k}: give its name in every language")
        if not lines:
            errors.append(f"part {k}: give it its ingredient lines")
        for n in lines:
            if not 1 <= n <= n_lines:
                errors.append(f"part {k}: there is no line {n}")
            elif n in seen_lines:
                errors.append(f"line {n} is in two parts -- give it to one")
            seen_lines.add(n)
        for n in units:
            if not 1 <= n <= n_units:
                errors.append(f"part {k}: there is no sentence {n}")
            elif n in seen_units:
                errors.append(f"sentence {n} is in two parts -- give it to one")
            seen_units.add(n)
        if existing and (existing not in usable or existing in seen_dishes):
            errors.append(f"part {k}: {existing} is none of the EXISTING DISHES' ids, or another part's -- "
                          "give one of them, or 0")
        seen_dishes.add(existing)
        if weight <= 0:
            errors.append(f"part {k}: weight_g is what it weighs, in grams, above 0")
        out.append({"name": names, "existing": existing, "lines": sorted(n - 1 for n in lines),
                    "sentences": sorted(n - 1 for n in units), "weight_g": weight})
    if out and len(seen_lines) >= n_lines:
        errors.append("the main one keeps at least one line -- the dish itself is no part")
    return (None, errors) if errors else (out, [])


def _pieces(plan: dict, keep: list[int], steps: list[dict]):
    """The recipe cut by the sub-recipes picked: (the dish's own {"lines",
    "steps"}, the new ones' -- each its plan part with "lines" and "steps"
    --, existing dish -> how many grams of it). What isn't picked stays
    with the dish; a picked existing dish's lines and sentences go, it
    being the dish's instead. A step's photos go with the sentences that
    mention them, one mentioned by none with the step's first sentence."""
    lines, units = plan["lines"], plan["units"]
    if not keep:
        return {"lines": lines, "steps": steps}, [], {}
    owner = [0] * len(units)  # 0 the dish, else 1 + its place in `new`
    line_owner = [0] * len(lines)
    new, linked, dropped = [], {}, -1
    for k in keep:
        p = plan["parts"][k]
        if p["existing"]:
            linked[p["existing"]] = p["weight_g"]
            tag = dropped
        else:
            new.append(p)
            tag = len(new)
        for n in p["sentences"]:
            owner[n] = tag
        for n in p["lines"]:
            line_owner[n] = tag

    def cut(tag: int) -> dict:
        out = []
        for si, st in enumerate(steps):
            mine = [(u, owner[i]) for i, u in enumerate(units) if u["step"] == si]
            if not mine:  # photos only: the dish's
                if tag == 0:
                    out.append(st)
                continue
            texts = {}
            for u, o in mine:
                if o == tag:
                    texts.setdefault(u["para"], []).append(u["text"])
            if not texts:
                continue
            text = "\n\n".join(" ".join(ts) for _, ts in sorted(texts.items()))
            marks = {m for _kind, m in food.PHOTO_MARK_RE.findall(text)}
            mentioned = {m for _kind, m in food.PHOTO_MARK_RE.findall(st["text"])}
            first = mine[0][1] == tag
            images = [img for img in st["images"]
                      if {str(n) for n in img["steps"]} & marks
                      or (first and not {str(n) for n in img["steps"]} & mentioned)]
            out.append({"text": text, "images": images})
        return {"lines": [ln for n, ln in enumerate(lines) if line_owner[n] == tag], "steps": out}

    for t, p in enumerate(new, 1):
        p.update(cut(t))
    return cut(0), new, linked


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


# ── the preparation ──────────────────────────────────────────────────────
def _number_unmarked(steps: list[dict]) -> list[dict]:
    """A photo the text doesn't mention (a blog's one photo a step) gets a
    number of its own, after the ones the text mentions."""
    used = [int(n) for st in steps for kind, n in food.PHOTO_MARK_RE.findall(st["text"]) if kind == "ref"]
    used += [n for st in steps for img in st["images"] for n in img["steps"]]
    n = max(used, default=0)
    for st in steps:
        for img in st["images"]:
            if not img["steps"]:
                n += 1
                img["steps"] = [n]
    return steps


_PREPARATION_SYSTEM_PROMPT = (
    "You are given the preparation steps of a recipe, as scraped from its "
    "web page. Some sentences in them are not preparation: an introduction to "
    "the dish, invitations to read other recipes, links, sign-offs, ads. Call "
    "save_preparation with the steps, keeping only the preparation.\n\n"
    "Copy every sentence you keep exactly as it is, word for word, with every "
    "marker like {{ref:3}} in it -- never reword, translate, reorder, merge "
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
        marks = {m for _kind, m in food.PHOTO_MARK_RE.findall(text)}
        mentioned = {m for _kind, m in food.PHOTO_MARK_RE.findall(source)}
        if not marks <= mentioned:
            errors.append(f"step {n}: a photo marker that the step does not have")
        # Its photos the kept text still mentions, and the ones it never did.
        images = [img for img in steps[n - 1]["images"]
                  if {str(s) for s in img["steps"]} & marks or not {str(s) for s in img["steps"]} & mentioned]
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
        except ImportProblem as e:
            print(f"[food import] preparation kept as it was: {e}")
            return steps
        kept, errors = _check_preparation(args, steps)
        if kept is not None:
            return kept
        print(f"[food import] preparation answer rejected: {'; '.join(errors[:3])}")
        messages += [{"role": "assistant", "content": json.dumps(args, ensure_ascii=False)},
                     {"role": "user", "content": _fix_these(errors)}]
    return steps


def _markdown(steps: list[dict]) -> str:
    """The steps as a numbered Markdown list, a step's paragraphs in its
    item -- the text's {{ref:N}} mentions where they are; no photos (see
    _with_photos)."""
    items = []
    for i, st in enumerate(steps, 1):
        paras = [p.strip() for p in st["text"].split("\n\n") if p.strip()]
        items.append(f"{i}. " + "\n\n   ".join(paras))
    return "\n\n".join(items)


_ITEM_RE = re.compile(r"^(\d+)\. ", re.M)


def _items(md: str) -> list[int]:
    return [int(n) for n in _ITEM_RE.findall(md)]


def _with_photos(md: str, steps: list[dict]) -> str:
    """_markdown's list (in any language) with each step's photos on a line
    of their own just above its item: a {{photo:N}} each (N its first
    number; a strip of several is one photo), shown there."""
    def above(m: re.Match) -> str:
        st = steps[int(m[1]) - 1]
        shown = " ".join(food.photo_mark(img["steps"][0]) for img in st["images"] if img["steps"])
        return f"{shown}\n{m[0]}" if shown else m[0]
    return _ITEM_RE.sub(above, md)


# How each language's instructions are written, whatever the page's style.
_INSTRUCTIONS_STYLE = {
    "en": 'the imperative ("Chop the onion and fry it in the oil.")',
    "it": 'the infinitive ("Tritare la cipolla e farla soffriggere nell\'olio.") -- never '
          '"tritate" or "trita"',
    "de": 'the infinitive at the end of the sentence ("Die Zwiebel hacken und im Öl anbraten.") -- '
          'never "Hacken Sie" or "hacke"',
}

_INSTRUCTIONS_SYSTEM_PROMPT = (
    "You are given a recipe's cooking instructions as scraped from its web "
    "page, in Markdown, in whatever language the page is written in. Call "
    "save_instructions with them written in each of these languages -- the "
    "page's own language too, rewritten like the others:\n{styles}\n\n"
    "The same steps, in the same order, saying the same things: every "
    "ingredient, amount, temperature, time and piece of advice, nothing "
    "added, dropped or explained -- but an amount or temperature in units "
    "not metric (pounds, ounces, cups, inches, Fahrenheit) gets its metric "
    "value after it, in brackets, rounded as a cook would (\"3½ lb (1.6 "
    "kg)\", \"350°F (175°C)\"), in every language; metric ones stay as "
    "they are. Only the wording becomes the style above: "
    "no addressing the reader (\"you\", \"voi\", \"Sie\"), no \"I\" or "
    "\"we\", plain and concise sentences. Keep the Markdown: a numbered item "
    "a step, numbered as it is, its paragraphs in it. A marker like {{ref:3}} "
    "is the text's mention of a photo of the recipe: keep every one exactly "
    "as it is, in the same place of the sentence it belongs to -- never "
    "translate, renumber, add or drop one."
)


# A dish split off sub-recipes (food_import's splitting stage) keeps only
# its own sentences, which still speak of the rest loosely ("pour everything
# over the base"): the instructions say what those are.
_USES_PROMPT = (
    "\n\nThis dish is made with these other dishes, each prepared apart, by "
    "its own recipe -- named here in each language:\n{uses}\n"
    "Their making was taken out of these instructions, so what is left may "
    "speak of them loosely (\"pour everything over the base\", \"the "
    "cream\"). These are the only things to change besides the wording: in "
    "every language, begin with one step of your own, numbered 1., saying to "
    "prepare those dishes first, each by its name as given; the given steps "
    "follow, numbered on from 2.; and wherever a step means one of those "
    "dishes, name it as given (\"pour the lemon cream over the biscuit "
    "base\")."
)


def _write_instructions(steps: list[dict], uses: list[dict[str, str]] | None = None) -> dict[str, str]:
    """The steps as Markdown (_markdown, _with_photos) in every language of
    food.LANGUAGES, the house style (_INSTRUCTIONS_STYLE) -- the page's own
    language rewritten too, so it needn't be known. The model never sees
    the photos' lines: they are put back above their steps after. `uses`:
    the dishes it is made with, apart (lang -> name each) -- a first step
    says to prepare them, the others name them (_USES_PROMPT). One retry
    with what was wrong. Raises ImportProblem."""
    md = _markdown(steps)
    prompt = _INSTRUCTIONS_SYSTEM_PROMPT.replace("{styles}", "\n".join(
        f"- {food.LANGUAGES[lang]}: {_INSTRUCTIONS_STYLE[lang]}" for lang in food.LANGUAGES))
    if uses:
        prompt += _USES_PROMPT.replace("{uses}", "\n".join(
            "- " + "; ".join(f"{food.LANGUAGES[lang]}: {u.get(lang) or u['en']}" for lang in food.LANGUAGES)
            for u in uses))
        # The step of its own comes first, with no photos.
        steps = [{"text": "", "images": []}] + steps
    tool = {"type": "function", "function": {
        "name": "save_instructions",
        "description": "Save the instructions in every language.",
        "parameters": {"type": "object", "properties": {
            food.LANGUAGES[lang]: {"type": "string", "description": f"The full instructions in {food.LANGUAGES[lang]}"}
            for lang in food.LANGUAGES},
            "required": list(food.LANGUAGES.values()), "additionalProperties": False},
    }}
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": f'"""\n{md}\n"""'}]
    marks = sorted(food.PHOTO_MARK_RE.findall(md))
    errors: list[str] = []
    for _attempt in range(2):
        args = _call_tool(messages, tool)
        out = {lang: food._unquoted(str(args.get(name, ""))) for lang, name in food.LANGUAGES.items()}
        errors = [f"the {food.LANGUAGES[lang]} instructions are missing" for lang, t in out.items() if not t]
        for lang, t in out.items():
            have = sorted(food.PHOTO_MARK_RE.findall(t))
            if t and _items(t) != list(range(1, len(steps) + 1)):
                errors.append(f"the {food.LANGUAGES[lang]} instructions are not the {len(steps)} steps, "
                              f"numbered 1. to {len(steps)}. as given, each at the start of its line")
            if t and have != marks:
                missing, extra = _diff_marks(marks, have), _diff_marks(have, marks)
                errors.append(f"the {food.LANGUAGES[lang]} instructions' markers are not the original's"
                              + (f" -- missing: {missing}" if missing else "")
                              + (f" -- not in the original: {extra}" if extra else ""))
        if not errors:
            return {lang: _with_photos(t, steps) for lang, t in out.items()}
        print(f"[food import] instructions answer rejected: {'; '.join(errors[:3])}")
        messages += [{"role": "assistant", "content": json.dumps(args, ensure_ascii=False)},
                     {"role": "user", "content": _fix_these(errors)}]
    raise ImportProblem("; ".join(errors[:3]))


def _diff_marks(a: list[tuple[str, str]], b: list[tuple[str, str]]) -> str:
    """The markers of `a` that `b` lacks (a count each), written as they are."""
    rest = list(b)
    out = []
    for m in a:
        if m in rest:
            rest.remove(m)
        else:
            out.append("{{%s:%s}}" % m)
    return ", ".join(out)


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
        return food._store_image(
            f"{food._slug(name)}-step-{secrets.token_hex(4)}{food._ext_for(resp.headers.get('content-type', ''), url)}",
            resp.content)

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
        print(f"[food import] ingredients answer rejected: {'; '.join(errors[:3])}")
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
