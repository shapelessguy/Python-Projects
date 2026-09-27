"""Food service storage — a self-contained module: its own SQLite file
(`api/data/food.db`), its own image store (`api/data/food_images/`), its own
per-user `"<user>:food_version"` counter. Nothing here touches the diary schema.

The **catalogue is shared**: a dish's name / category / image is the same for
everyone, and adding, renaming, re-imaging or deleting a dish is a global change
(it bumps every user's version). Only the **rating** is per-user, kept in
`food_ratings(dish_id, username)` — changing your own rating bumps only your
version.

Every mutating helper returns the caller's full catalogue snapshot so the reply
already carries what the UI should render."""
import ipaddress
import json
import mimetypes
import re
import secrets
import shutil
import socket
import sqlite3
import threading
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from api.config import (
    FOOD_DB,
    FOOD_IMAGES_DIR,
    OPENROUTER_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_URL,
    SEED_DIR,
    SEED_USER,
    SERPER_API_KEY,
    SERPER_IMAGE_URL,
)
from api.db import bump, connect as _connect, get_version

DEFAULT_CATEGORIES = [
    "Pasta", "Dough", "Risotti", "Meat", "Fish", "Desserts", "Restaurants",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS food_dishes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    image    TEXT NOT NULL DEFAULT '',
    url      TEXT NOT NULL DEFAULT '',
    page_text    TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    ingredients  TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS food_ratings (
    dish_id  INTEGER NOT NULL,
    username TEXT NOT NULL,
    rating   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dish_id, username)
);
CREATE INDEX IF NOT EXISTS idx_food_ratings_user ON food_ratings(username);
-- The ingredient list: every ingredient the generated recipes use, with
-- the one unit it is bought and measured in (SHOP_UNITS).
CREATE TABLE IF NOT EXISTS food_ingredients (
    name TEXT PRIMARY KEY,
    unit TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""

_REQ_HEADERS = {"User-Agent": "Mozilla/5.0 (cyanhouse-food)"}

# A dish's image and recipe URLs come from whoever edits it, and the server
# fetches them -- from inside the home network. Left unchecked that reaches
# what only trusts the LAN or localhost: the ESP32 boards (a GET switches the
# lights), qBittorrent (no login from 127.0.0.1), the router. So only public
# addresses are fetched, every redirect is checked the same way, and the body
# is capped.
_MAX_FETCH_BYTES = 15 * 1024 * 1024
_MAX_REDIRECTS = 5


def _check_public(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not a web address: {url!r}")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as e:
        raise ValueError(f"cannot resolve {parts.hostname}: {e}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            raise ValueError(f"{parts.hostname} is not a public address")


def _public_get(url: str, timeout: float) -> requests.Response:
    """requests.get for a URL a user gave, refusing anything not on the
    public internet (see above)."""
    for _ in range(_MAX_REDIRECTS + 1):
        _check_public(url)
        resp = requests.get(url, headers=_REQ_HEADERS, timeout=timeout,
                            allow_redirects=False, stream=True)
        if resp.is_redirect and resp.headers.get("location"):
            url = urljoin(url, resp.headers["location"])
            resp.close()
            continue
        body = bytearray()
        for chunk in resp.iter_content(64 * 1024):
            body += chunk
            if len(body) > _MAX_FETCH_BYTES:
                resp.close()
                raise ValueError("response too large")
        resp._content = bytes(body)
        return resp
    raise ValueError("too many redirects")


def _version_key(user: str) -> str:
    return f"{user}:food_version"


def _users() -> list[str]:
    from api.auth import USERS
    return list(USERS)


@contextmanager
def connect():
    with _connect(FOOD_DB) as conn:
        yield conn


def _bump_user(conn: sqlite3.Connection, user: str) -> None:
    bump(conn, _version_key(user))


def _bump_all(conn: sqlite3.Connection) -> None:
    """A shared-catalogue change: every user's clients must refetch."""
    for u in _users():
        bump(conn, _version_key(u))


# ── image store (shared) ─────────────────────────────────────────────────
def image_path(name: str) -> Path | None:
    base = FOOD_IMAGES_DIR.resolve()
    p = (base / name).resolve()
    return p if p.parent == base and p.is_file() else None


# ── lifecycle ─────────────────────────────────────────────────────────────
def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database already existed in the wild —
    CREATE TABLE IF NOT EXISTS in _SCHEMA only covers a brand-new DB."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(food_dishes)")}
    if "url" not in cols:
        conn.execute("ALTER TABLE food_dishes ADD COLUMN url TEXT NOT NULL DEFAULT ''")
    if "page_text" not in cols:
        if "html" in cols:
            # Short-lived column from an earlier version of this feature
            # (stored raw fetched HTML, images and all) -- repurpose it
            # rather than losing whatever's already been fetched.
            conn.execute("ALTER TABLE food_dishes RENAME COLUMN html TO page_text")
        else:
            conn.execute("ALTER TABLE food_dishes ADD COLUMN page_text TEXT NOT NULL DEFAULT ''")
    if "instructions" not in cols:
        if "description" in cols:
            # Renamed for clarity -- it always held the cooking procedure,
            # never a general "description".
            conn.execute("ALTER TABLE food_dishes RENAME COLUMN description TO instructions")
        else:
            conn.execute("ALTER TABLE food_dishes ADD COLUMN instructions TEXT NOT NULL DEFAULT ''")
    if "ingredients" not in cols:
        conn.execute("ALTER TABLE food_dishes ADD COLUMN ingredients TEXT NOT NULL DEFAULT ''")


def init_db() -> None:
    FOOD_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        if conn.execute("SELECT COUNT(*) FROM food_dishes").fetchone()[0] == 0:
            _seed(conn)
        _seed_missing_ratings(conn)
    _spawn_instructions_processing()  # pick up anything left over from before a restart
    _spawn_ingredients_processing()


def _seed_missing_ratings(conn: sqlite3.Connection) -> None:
    """Every configured user starts from the same baseline: for any seed dish a
    user has no rating row on yet, give them the seed rating. Idempotent — runs
    each startup, so a newly added user gets seeded on the next restart, while
    users who've already rated a dish are left alone."""
    seed_file = SEED_DIR / "food.json"
    if not seed_file.exists():
        return
    by_name = {
        r["name"].strip(): int(r.get("rating", 0) or 0)
        for r in json.loads(seed_file.read_text("utf-8"))
    }
    dishes = conn.execute("SELECT id, name FROM food_dishes").fetchall()
    for user in _users():
        rated = {
            row["dish_id"] for row in conn.execute(
                "SELECT dish_id FROM food_ratings WHERE username = ?", (user,)
            )
        }
        for d in dishes:
            if d["id"] in rated:
                continue
            r = by_name.get(d["name"], 0)
            if r:
                conn.execute(
                    "INSERT OR IGNORE INTO food_ratings(dish_id, username, rating) "
                    "VALUES(?,?,?)",
                    (d["id"], user, r),
                )


def version(user: str) -> int:
    with connect() as conn:
        return get_version(conn, _version_key(user))


def _seed(conn: sqlite3.Connection) -> None:
    """Load api/seed/food.json into the shared catalogue; the seeded ratings
    become SEED_USER's personal ratings."""
    seed_file = SEED_DIR / "food.json"
    seed_imgs = SEED_DIR / "food_images"
    if not seed_file.exists():
        return
    for pos, r in enumerate(json.loads(seed_file.read_text("utf-8"))):
        image = r.get("image") or ""
        if image and (seed_imgs / image).exists():
            dst = FOOD_IMAGES_DIR / image
            if not dst.exists():
                shutil.copyfile(seed_imgs / image, dst)
        else:
            image = ""
        cur = conn.execute(
            "INSERT INTO food_dishes(name, category, image, position) VALUES(?,?,?,?)",
            (r["name"].strip(), r.get("category", "").strip(), image, r.get("position", pos)),
        )
        rating = int(r.get("rating", 0) or 0)
        if rating:
            conn.execute(
                "INSERT INTO food_ratings(dish_id, username, rating) VALUES(?,?,?)",
                (cur.lastrowid, SEED_USER, rating),
            )


# ── snapshot (dishes + the caller's own ratings) ────────────────────────
def snapshot(conn: sqlite3.Connection, user: str) -> dict:
    dishes = [
        # The extracted page text itself is only ever used server-side (as
        # the LLM's input); clients just need to know whether it's there yet,
        # to color the url/text status dot -- no reason to ship the whole
        # text blob on every dish list poll. instructions/ingredients, once
        # there, ARE for the client -- that's the buttons.
        {"id": r["id"], "name": r["name"], "category": r["category"],
         "image": r["image"], "url": r["url"], "has_text": bool(r["page_text"]),
         "instructions": r["instructions"], "ingredients": r["ingredients"],
         "rating": r["rating"]}
        for r in conn.execute(
            "SELECT d.id, d.name, d.category, d.image, d.url, d.page_text, "
            "       d.instructions, d.ingredients, "
            "       COALESCE(rt.rating, 0) AS rating "
            "FROM food_dishes d "
            "LEFT JOIN food_ratings rt ON rt.dish_id = d.id AND rt.username = ? "
            "ORDER BY d.category, d.position, d.id",
            (user,),
        )
    ]
    used = {d["category"] for d in dishes if d["category"]}
    categories = list(DEFAULT_CATEGORIES)
    for c in sorted(used):
        if c not in categories:
            categories.append(c)
    return {
        "dishes": dishes,
        "categories": categories,
        # The ingredient list (food_ingredients) -- ships with the dishes, so
        # a correction reaches the clients on the same poll.
        "ingredients": _catalog_rows(conn),
        "version": get_version(conn, _version_key(user)),
    }


def get_all(user: str) -> dict:
    with connect() as conn:
        return snapshot(conn, user)


# ── images ───────────────────────────────────────────────────────────────
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_") or "dish"


def _ext_for(content_type: str, url: str) -> str:
    ext = mimetypes.guess_extension((content_type or "").split(";")[0].strip() or "")
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if ext == ".jpeg" else ext
    m = re.search(r"\.(jpe?g|png|webp|gif)(?:\?|$)", url or "", re.I)
    return f".{m.group(1).lower()}" if m else ".jpg"


def download_image(url: str, name_hint: str) -> str:
    """Fetch a picked search-result URL into the shared image store; return the
    stored filename. Raises on network / HTTP error."""
    resp = _public_get(url, timeout=20)
    resp.raise_for_status()
    fname = f"{_slug(name_hint)}-{secrets.token_hex(4)}{_ext_for(resp.headers.get('content-type', ''), url)}"
    (FOOD_IMAGES_DIR / fname).write_bytes(resp.content)
    return fname


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


# ── LLM plumbing shared by the instructions and ingredients pipelines ────
# Recipe pages are long and repetitive (nav/ads/comments alongside the actual
# procedure); cap what's sent so a single dish can't blow the model's context.
_MAX_LLM_INPUT_CHARS = 12000


def _openrouter_chat(messages: list[dict]) -> str:
    """One raw OpenRouter chat-completion call. Raises on any request/HTTP
    failure -- callers decide what "the call itself failed" should mean for
    their retry policy, so this doesn't swallow anything."""
    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": OPENROUTER_MODEL, "messages": messages},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


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
    finally:
        _PROCESS_LOCK.release()


def _spawn_instructions_processing() -> None:
    threading.Thread(target=_process_pending_instructions, daemon=True).start()


# ── ingredients (LLM, background, one dish at a time, strictly validated) ─
# Stored as canonical JSON text:
#   {"quantity": "<number>", "unit": "<lowercase word>",
#    "ingredients": {"<lowercase singular name>":
#                     {"quantity": "<number-or-empty>", "unit": "<lowercase-or-empty>"}, ...}}
# Each ingredient's quantity/unit are separate fields (not a combined
# "<number><unit>" string) so clients can render/edit them as two plain
# textboxes with no parsing of their own. Regex-checked below; a dish is
# only ever saved once its output matches, so any client reading a
# non-empty `ingredients` column can trust the shape completely.
_LOWER_WORD_RE = re.compile(r"^[a-z]+(?: [a-z]+)*$")
_PLAIN_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
_MAX_INGREDIENT_ATTEMPTS = 3
# The shopping units an ingredient of the list (food_ingredients) is measured
# in: what it is sold by at the supermarket, so the shopping list adds each
# ingredient up across recipes and says it the way it is bought. A count is
# "" in a recipe, "count" to the model. Manual edits of a dish are not held
# to this.
SHOP_UNITS = ("g", "ml", "")
_MODEL_UNIT = {"g": "g", "ml": "ml", "": "count"}
_FROM_MODEL_UNIT = {v: k for k, v in _MODEL_UNIT.items()}

_INGREDIENTS_SYSTEM_PROMPT = (
    "You extract the ingredients of a recipe from messy text scraped from "
    "its webpage, for a shopping list. You are given the INGREDIENT LIST: "
    "every ingredient already known, each with the one unit it is always "
    "measured in. Work in two steps.\n\n"
    "Step 1 -- new ingredients. Go through the recipe's ingredients. Each one "
    "that is the same thing to buy as an ingredient of the list IS that "
    "ingredient: use the list's name. Only one that is genuinely different "
    "to buy is new: give it a name and decide its unit, the way a "
    "supermarket sells it:\n"
    '  - "g" for anything sold by weight: vegetables, fruit, meat, fish, '
    "cheese, pasta, rice, flour, sugar, butter, bread, nuts, herbs, spices, "
    "salt.\n"
    '  - "ml" for liquids sold by volume: oil, vinegar, milk, cream, wine, '
    "beer, stock, water, passata, sauces sold in bottles.\n"
    '  - "count" only for things sold and used as whole pieces: egg, lemon, '
    "lime, avocado, bread roll.\n\n"
    "Step 2 -- the recipe. Write every ingredient in exactly the unit the "
    "list (or your step 1) gives it, converting the recipe's amounts: kg, "
    "pounds, ounces and cups to g or ml; spoons of a liquid to ml (1 tbsp = "
    "15 ml, 1 tsp = 5 ml); spoons of a solid to g (1 tbsp flour or sugar = "
    "12 g, 1 tsp salt = 5 g, 1 tsp of a dried spice = 2 g); pieces to g "
    "with the typical weight of that exact ingredient (1 medium onion = "
    "150 g, 1 potato = 200 g, 1 carrot = 60 g, 1 celery stalk = 40 g, "
    "1 garlic clove = 5 g, 1 tomato = 120 g, 1 cherry tomato = 15 g). "
    "Round converted amounts sensibly (150 g, not 147.87 g).\n\n"
    "Output ONLY a single JSON object (no markdown fences, no commentary) "
    "with exactly this shape, the keys in this order:\n\n"
    '{"new_ingredients": {"<name>": "<g, ml or count>", ...}, '
    '"quantity": "<number>", "unit": "<recipe yield unit, e.g. persons, '
    'servings -- lowercase>", "ingredients": {"<name>": '
    '{"quantity": "<number or empty string>", "unit": "<the ingredient\'s '
    'unit, or empty string>"}, ...}}\n\n'
    "Rules, all mandatory:\n"
    '- "new_ingredients" holds only names that are not in the list, each '
    "used in the recipe; {} when there are none.\n"
    "- Every name is in English whatever the page's language (\"onion\" not "
    '"cipolla"), lowercase and singular ("egg" not "eggs"), and the plain '
    "name it is bought under: no quality, brand or preparation words "
    '("olive oil" not "extra virgin olive oil", "tomato" not "chopped '
    'tomato", "parmesan" not "grated parmesan cheese"). Keep a word only '
    'when it names a different thing to buy ("cherry tomato", "red onion").\n'
    "- Name the product, not a part of it: \"celery\" not \"celery stalk\", "
    '"garlic" (in g) not "garlic clove", "parsley" not "parsley leaf". And '
    'not a whole category: the cheese, bean or pasta it actually is ("provola", '
    '"cannellini bean"), never just "cheese".\n'
    '- An ingredient\'s "quantity" is a plain number, or "" when the '
    'recipe gives no amount ("salt to taste"). Never a range, a fraction '
    "or text.\n"
    '- An ingredient\'s "unit" is "g" or "ml" when its unit is g or ml, and '
    '"" when its unit is count (2 eggs is {"quantity": "2", "unit": ""}). '
    'With no amount, both are "": {"quantity": "", "unit": ""}.\n'
    "- Do not include any text outside the JSON object."
)


def _validate_ingredients_json(text: str) -> tuple[dict | None, list[str]]:
    """(parsed_dict, []) if `text` matches the required shape exactly, else
    (None, [reason, ...]) listing EVERY violation found, not just the first
    -- fed back to the model in full on a retry, so fixing one problem can't
    reveal a second one it was never told about and burn the remaining
    attempts one-issue-at-a-time. Only the shape: what a generated recipe
    must also meet is _validate_generated's."""
    try:
        data = json.loads(text)
    except Exception as e:
        return None, [f"not valid JSON ({e})"]
    if not isinstance(data, dict) or set(data.keys()) != {"quantity", "unit", "ingredients"}:
        return None, ['top-level value must be a JSON object with exactly the keys "quantity", "unit", "ingredients"']
    quantity, unit, ingredients = data.get("quantity"), data.get("unit"), data.get("ingredients")
    errors: list[str] = []
    if not _PLAIN_NUMBER_RE.match(str(quantity)):
        errors.append('"quantity" must be a plain number (e.g. "4"), no units or text')
    if not isinstance(unit, str) or not _LOWER_WORD_RE.match(unit):
        errors.append('"unit" must be lowercase word(s), e.g. "persons"')
    if not isinstance(ingredients, dict) or not ingredients:
        errors.append('"ingredients" must be a non-empty JSON object')
        return None, errors  # nothing left that can be checked
    for name, entry in ingredients.items():
        if not isinstance(name, str) or not _LOWER_WORD_RE.match(str(name)):
            errors.append(f'ingredient name "{name}" must be lowercase singular word(s), e.g. "onion"')
        if not isinstance(entry, dict) or set(entry.keys()) != {"quantity", "unit"}:
            errors.append(f'ingredient "{name}" must be an object with exactly "quantity" and "unit"')
            continue  # nothing to check quantity/unit against
        i_qty, i_unit = entry["quantity"], entry["unit"]
        if not isinstance(i_qty, str) or not (i_qty == "" or _PLAIN_NUMBER_RE.match(i_qty)):
            errors.append(f'ingredient "{name}" quantity "{i_qty}" must be a plain number or ""')
        if not isinstance(i_unit, str) or not (i_unit == "" or _LOWER_WORD_RE.match(i_unit)):
            errors.append(f'ingredient "{name}" unit "{i_unit}" must be lowercase word(s) or ""')
        if i_unit and not i_qty:
            errors.append(f'ingredient "{name}" has a unit but no quantity -- use "" for both, or give a quantity')
    if errors:
        return None, errors
    return data, []


def _validate_generated(text: str, catalog: dict[str, str]) -> tuple[dict | None, dict[str, str], list[str]]:
    """The model's answer (_INGREDIENTS_SYSTEM_PROMPT) against the ingredient
    list `catalog` (name -> unit): (recipe, the new ingredients with their
    units, []) when every ingredient is in the list or declared new and is
    in its unit; otherwise (None, {}, [reason, ...])."""
    try:
        data = json.loads(text)
    except Exception as e:
        return None, {}, [f"not valid JSON ({e})"]
    if not isinstance(data, dict) or "new_ingredients" not in data:
        return None, {}, ['top-level value must be a JSON object with the keys "new_ingredients", '
                          '"quantity", "unit", "ingredients"']
    new_raw = data.pop("new_ingredients")
    recipe, errors = _validate_ingredients_json(json.dumps(data))
    if not isinstance(new_raw, dict):
        return None, {}, errors + ['"new_ingredients" must be a JSON object ({} when there are none)']
    new: dict[str, str] = {}
    for name, unit in new_raw.items():
        if not isinstance(name, str) or not _LOWER_WORD_RE.match(name):
            errors.append(f'new ingredient name "{name}" must be lowercase singular word(s)')
        elif name in catalog:
            errors.append(f'"{name}" is already in the ingredient list (unit {_MODEL_UNIT[catalog[name]]}) '
                          '-- use it; do not add it to "new_ingredients"')
        elif unit not in _FROM_MODEL_UNIT:
            errors.append(f'new ingredient "{name}" unit "{unit}" must be "g", "ml" or "count"')
        else:
            new[name] = _FROM_MODEL_UNIT[unit]
    if recipe is None:
        return None, {}, errors
    units = {**catalog, **new}
    for name, entry in recipe["ingredients"].items():
        if name not in units:
            if name not in new_raw:
                errors.append(f'ingredient "{name}" is not in the ingredient list -- use the list\'s name for '
                              'it, or, if it is genuinely different to buy, add it to "new_ingredients"')
            continue
        want = units[name]
        if entry["quantity"] and entry["unit"] != want:
            errors.append(f'ingredient "{name}" must be in {_MODEL_UNIT[want]} as the list says'
                          + (' (unit "")' if want == "" else f' (unit "{want}")')
                          + f', not "{entry["unit"]}" -- convert the amount')
    for name in new_raw:
        if name not in catalog and name not in recipe["ingredients"]:
            errors.append(f'new ingredient "{name}" is not used in "ingredients" -- drop it or use it')
    if errors:
        return None, {}, errors
    return recipe, new, []


def catalog(conn) -> dict[str, str]:
    """The ingredient list: name -> unit ("g", "ml", or "" for a count)."""
    return {r["name"]: r["unit"] for r in conn.execute("SELECT name, unit FROM food_ingredients")}


def _generate_ingredients(dish_name: str, page_text: str, known: dict[str, str]) -> tuple[str, dict[str, str]]:
    """Up to _MAX_INGREDIENT_ATTEMPTS attempts: each time the model's output
    fails validation, the invalid output and the specific reason are fed
    back so it can correct itself. A network/API failure is a different
    failure mode -- not worth retrying against, so it aborts immediately
    instead of spending the remaining attempts. Returns the canonical
    (re-serialized) recipe JSON and the ingredients it adds to the list
    (`known`, the list as it is), or ("", {}) if it never validated."""
    if not OPENROUTER_KEY:
        return "", {}
    listing = "\n".join(f"{n}: {_MODEL_UNIT[u]}" for n, u in sorted(known.items())) or "(empty -- every ingredient is new)"
    messages = [
        {"role": "system", "content": _INGREDIENTS_SYSTEM_PROMPT},
        {"role": "user", "content": f"INGREDIENT LIST (name: unit):\n{listing}\n\n"
                                    f"Dish: {dish_name}\n\n{page_text[:_MAX_LLM_INPUT_CHARS]}"},
    ]
    for _attempt in range(_MAX_INGREDIENT_ATTEMPTS):
        try:
            raw = _openrouter_chat(messages)
        except Exception:
            return "", {}
        recipe, new, errors = _validate_generated(raw, known)
        if recipe is not None:
            return json.dumps(recipe), new
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
    return "", {}


_INGREDIENTS_LOCK = threading.Lock()


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
                    f"WHERE page_text != '' AND ingredients = '' {exclude}"
                    "ORDER BY id LIMIT 1",
                    tuple(failed_ids),
                ).fetchone()
                # Read again for every dish: the one just done may have
                # added to it.
                known = catalog(conn)
            if row is None:
                return
            ingredients, new = _generate_ingredients(row["name"], row["page_text"], known)
            if not ingredients:
                failed_ids.add(row["id"])
                continue
            with connect() as conn:
                # The new ingredients join the list together with the dish
                # that brought them, never on their own.
                conn.executemany("INSERT OR IGNORE INTO food_ingredients (name, unit) VALUES (?, ?)",
                                 list(new.items()))
                conn.execute(
                    "UPDATE food_dishes SET ingredients = ? WHERE id = ?",
                    (ingredients, row["id"]),
                )
                _bump_all(conn)
    finally:
        _INGREDIENTS_LOCK.release()


def _spawn_ingredients_processing() -> None:
    threading.Thread(target=_process_pending_ingredients, daemon=True).start()


def _seed_image_names() -> set[str]:
    d = SEED_DIR / "food_images"
    return {f.name for f in d.glob("*")} if d.is_dir() else set()


def _forget_image(fname: str) -> None:
    """Delete a now-unreferenced image. Seed images are committed assets shared
    by the seeded catalogue, so leave those in place."""
    if not fname or fname in _seed_image_names():
        return
    base = FOOD_IMAGES_DIR
    p = base / fname
    try:
        if p.is_file() and p.parent == base:
            p.unlink()
    except OSError:
        pass


def search_images(query: str, num: int = 60) -> list[dict]:
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY is not set in secrets.json")
    resp = requests.post(
        SERPER_IMAGE_URL,
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "num": max(1, min(num, 100))},
        timeout=15,
    )
    resp.raise_for_status()
    out = []
    for it in resp.json().get("images", []):
        if it.get("imageUrl"):
            out.append({
                "url": it["imageUrl"],
                "thumbnail": it.get("thumbnailUrl") or it["imageUrl"],
                "title": it.get("title", ""),
                "source": it.get("source", ""),
            })
    return out


# ── CRUD ────────────────────────────────────────────────────────────────
def _clamp_rating(v) -> int:
    try:
        return max(0, min(int(v), 10))
    except (TypeError, ValueError):
        return 0


def _set_rating(conn: sqlite3.Connection, dish_id: int, user: str, rating: int) -> None:
    conn.execute(
        "INSERT INTO food_ratings(dish_id, username, rating) VALUES(?,?,?) "
        "ON CONFLICT(dish_id, username) DO UPDATE SET rating = excluded.rating",
        (dish_id, user, rating),
    )


def create_dish(user: str, name: str, category: str, rating, image_url: str | None, url: str | None = None) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    image = download_image(image_url, name) if image_url else ""
    url = (url or "").strip()
    with connect() as conn:
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM food_dishes WHERE category = ?",
            ((category or "").strip(),),
        ).fetchone()[0]
        # page_text starts empty -- fetched on a background thread below,
        # once the dish (and its id) are actually committed -- so the
        # request returns immediately instead of blocking on a
        # slow/unreachable recipe site.
        cur = conn.execute(
            "INSERT INTO food_dishes(name, category, image, url, page_text, position) VALUES(?,?,?,?,?,?)",
            (name, (category or "").strip(), image, url, "", pos),
        )
        dish_id = cur.lastrowid
        r = _clamp_rating(rating)
        if r:
            _set_rating(conn, dish_id, user, r)
        _bump_all(conn)  # new dish visible to everyone
        result = snapshot(conn, user)
    if url:
        _spawn_text_fetch(dish_id, url)
    # Explicit trigger point per the pipeline's contract; in practice this
    # almost never finds anything yet since page_text for *this* dish is
    # still being fetched above -- it's the _apply_text_fetch trigger that
    # does the real work. Kept anyway so any other dish stuck mid-pipeline
    # (e.g. the process restarted between its text fetch and
    # instructions/ingredients generation) gets picked back up too.
    _spawn_instructions_processing()
    _spawn_ingredients_processing()
    return result


def update_dish(user: str, dish_id: int, patch: dict) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, category, image, url, instructions, ingredients "
            "FROM food_dishes WHERE id = ?",
            (dish_id,),
        ).fetchone()
        if row is None:
            raise KeyError(dish_id)

        # Only count a shared field as changed if it actually differs — so a
        # rating-only edit (clients still send name/category unchanged) bumps
        # just this user, not everyone.
        shared: dict = {}
        if patch.get("name") is not None:
            n = str(patch["name"]).strip()
            if n and n != row["name"]:
                shared["name"] = n
        if patch.get("category") is not None:
            cat = str(patch["category"]).strip()
            if cat != row["category"]:
                shared["category"] = cat
        new_url: str | None = None  # set below when the url actually changes
        if patch.get("url") is not None:
            u = str(patch["url"]).strip()
            if u != row["url"]:
                shared["url"] = u
                # Cleared immediately; the background fetch below fills
                # page_text in once the (possibly slow/unreachable) page
                # responds, which in turn re-triggers instructions
                # processing. instructions/ingredients were generated from
                # the *old* url's text, so they'd be wrong left in place.
                shared["page_text"] = ""
                shared["instructions"] = ""
                shared["ingredients"] = ""
                new_url = u
        if patch.get("image_url"):
            shared["image"] = download_image(patch["image_url"], shared.get("name", row["name"]))
        # Manual edit from the Instructions modal. Checked after the url
        # branch above so an explicit edit always wins over the "url changed,
        # clear it" default -- relevant if a client ever sent both at once.
        if patch.get("instructions") is not None:
            ins = str(patch["instructions"]).strip()
            if ins != row["instructions"]:
                shared["instructions"] = ins
        # Manual edit from the Ingredients modal -- held to the exact same
        # structure/regex rules as the LLM output, so nothing downstream
        # ever has to distinguish "generated" from "hand-edited" data.
        if patch.get("ingredients") is not None:
            ing = str(patch["ingredients"]).strip()
            if ing != row["ingredients"]:
                if ing:
                    data, errors = _validate_ingredients_json(ing)
                    if errors:
                        raise ValueError("invalid ingredients: " + "; ".join(errors))
                    ing = json.dumps(data)  # canonical formatting
                shared["ingredients"] = ing

        if shared:
            sets = ", ".join(f"{k} = ?" for k in shared)
            conn.execute(f"UPDATE food_dishes SET {sets} WHERE id = ?",
                         (*shared.values(), dish_id))
            if "image" in shared:
                _forget_image(row["image"])

        rating_given = "rating" in patch and patch["rating"] is not None
        if rating_given:
            _set_rating(conn, dish_id, user, _clamp_rating(patch["rating"]))

        if shared:
            _bump_all(conn)       # catalogue change — everyone refetches
        elif rating_given:
            _bump_user(conn, user)  # only my rating changed
        result = snapshot(conn, user)
    if new_url:
        _spawn_text_fetch(dish_id, new_url)
    return result


def delete_dish(user: str, dish_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT image FROM food_dishes WHERE id = ?", (dish_id,)
        ).fetchone()
        if row is None:
            raise KeyError(dish_id)
        conn.execute("DELETE FROM food_ratings WHERE dish_id = ?", (dish_id,))
        conn.execute("DELETE FROM food_dishes WHERE id = ?", (dish_id,))
        _bump_all(conn)
        _forget_image(row["image"])
        return snapshot(conn, user)


# ── the ingredient list, as people correct it ────────────────────────────
class IngredientError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _catalog_rows(conn: sqlite3.Connection) -> list[dict]:
    """The list for the clients: each ingredient, its unit, and how many
    dishes use it."""
    uses: dict[str, int] = {}
    for (text,) in conn.execute("SELECT ingredients FROM food_dishes WHERE ingredients != ''"):
        try:
            for name in json.loads(text)["ingredients"]:
                uses[name] = uses.get(name, 0) + 1
        except (ValueError, KeyError, TypeError):
            continue
    return [{"name": n, "unit": u, "uses": uses.get(n, 0)} for n, u in sorted(catalog(conn).items())]


def _fmt_qty(x: float) -> str:
    """An amount after a conversion, rounded the way a recipe writes it."""
    x = round(x) if x >= 10 else round(x, 1) if x >= 1 else round(x, 2)
    return f"{x:g}"


def _rewrite_dishes(conn: sqlite3.Connection, change) -> None:
    """Apply `change(ingredients: dict) -> bool` (True when it changed
    something) to every dish's ingredients."""
    for row in conn.execute("SELECT id, ingredients FROM food_dishes WHERE ingredients != ''").fetchall():
        try:
            data = json.loads(row["ingredients"])
            items = data["ingredients"]
        except (ValueError, KeyError, TypeError):
            continue
        if change(items):
            conn.execute("UPDATE food_dishes SET ingredients = ? WHERE id = ?",
                         (json.dumps(data), row["id"]))


def update_ingredient(user: str, name: str, new_name: str | None, unit: str | None,
                      factor: float | None) -> dict:
    """Correct one ingredient of the list, and every recipe with it.

    `unit`: its new unit; the amounts in it are multiplied by `factor` (how
    many of the new unit one of the old is -- 1 g of water is 1 ml, so g and
    ml may leave it out; a count and a weight need it: 1 onion = 150 g).
    `new_name`: renamed, and when that name is already in the list the two
    become one -- they have to be in the same unit by then -- and a recipe
    with both adds them up."""
    with connect() as conn:
        units = catalog(conn)
        if name not in units:
            raise IngredientError(f"no ingredient {name!r}", 404)
        old = units[name]
        if unit is not None and unit != old:
            if unit not in SHOP_UNITS:
                raise IngredientError('the unit is "g", "ml" or "" (a count)')
            if factor is None:
                if {old, unit} != {"g", "ml"}:
                    per = {"g": "g", "ml": "ml", "": "pieces"}
                    raise IngredientError(f"say how many {per[unit]} one {'piece' if old == '' else old} is")
                factor = 1.0
            if factor <= 0:
                raise IngredientError("the conversion has to be a positive number")

            def convert(items: dict) -> bool:
                e = items.get(name)
                if not e or e.get("unit", "") != old or not _PLAIN_NUMBER_RE.match(e.get("quantity", "")):
                    return False
                e["quantity"], e["unit"] = _fmt_qty(float(e["quantity"]) * factor), unit
                return True
            _rewrite_dishes(conn, convert)
            conn.execute("UPDATE food_ingredients SET unit = ? WHERE name = ?", (unit, name))
            old = unit
        target = (new_name or "").strip().lower()
        if target and target != name:
            if not _LOWER_WORD_RE.match(target):
                raise IngredientError("a name is lowercase letters, words separated by single spaces")
            if target in units and units[target] != old:
                raise IngredientError(
                    f"{target!r} is measured in {_MODEL_UNIT[units[target]]} and {name!r} in "
                    f"{_MODEL_UNIT[old]} -- give them the same unit first", 409)

            def rename(items: dict) -> bool:
                if name not in items:
                    return False
                moved = items.pop(name)
                have = items.get(target)
                if have is None:
                    items[target] = moved
                elif _PLAIN_NUMBER_RE.match(have["quantity"]) and _PLAIN_NUMBER_RE.match(moved["quantity"]):
                    have["quantity"] = _fmt_qty(float(have["quantity"]) + float(moved["quantity"]))
                elif not have["quantity"]:
                    items[target] = moved
                return True
            _rewrite_dishes(conn, rename)
            conn.execute("DELETE FROM food_ingredients WHERE name = ?", (name,))
            conn.execute("INSERT OR IGNORE INTO food_ingredients (name, unit) VALUES (?, ?)", (target, old))
        _bump_all(conn)
        return snapshot(conn, user)


def delete_ingredient(user: str, name: str) -> dict:
    """Take an ingredient off the list -- only one no recipe uses."""
    with connect() as conn:
        if name not in catalog(conn):
            raise IngredientError(f"no ingredient {name!r}", 404)
        used = next((r for r in _catalog_rows(conn) if r["name"] == name), {}).get("uses", 0)
        if used:
            raise IngredientError(f"{used} dish(es) use {name!r} -- rename it into another instead", 409)
        conn.execute("DELETE FROM food_ingredients WHERE name = ?", (name,))
        _bump_all(conn)
        return snapshot(conn, user)
