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
import base64
import ipaddress
import html
import itertools
import json
import math
import mimetypes
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from api.config import (
    FFMPEG,
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
from api.services import recipe_sites

DEFAULT_CATEGORIES = [
    "Pasta", "Dough", "Risotti", "Meat", "Fish", "Desserts", "Restaurants",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS food_dishes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    category_id INTEGER,  -- food_categories; NULL: none
    image    TEXT NOT NULL DEFAULT '',
    url      TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    -- What the recipe makes ("4" "persons"); the ingredients are its
    -- food_dish_ingredients rows.
    yield_qty  TEXT NOT NULL DEFAULT '',
    yield_unit TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    -- The facts (_FACT_COLUMNS), filled by the recipe import, editable.
    prep_min   INTEGER,
    cook_min   INTEGER,
    total_min  INTEGER,
    difficulty TEXT NOT NULL DEFAULT '',
    -- The recipe site's own rating and comments: shown, not edited.
    source_rating       TEXT NOT NULL DEFAULT '',
    source_rating_count TEXT NOT NULL DEFAULT '',
    source_comments     TEXT NOT NULL DEFAULT '',
    -- The instructions' photos: {"N": stored image file} for {{photo:N}}.
    photos     TEXT NOT NULL DEFAULT '{}',
    -- The recipe import (food_import.py): the url it last imported, and
    -- its state {"state": "running" | "done" | "failed", "stage", "errors"}.
    import_url   TEXT NOT NULL DEFAULT '',
    import_state TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS food_ratings (
    dish_id  INTEGER NOT NULL,
    username TEXT NOT NULL,
    rating   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dish_id, username)
);
CREATE INDEX IF NOT EXISTS idx_food_ratings_user ON food_ratings(username);
-- The ingredient list: every ingredient the recipes use, by its English name.
CREATE TABLE IF NOT EXISTS food_ingredients (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
-- An ingredient's name in the languages other than English.
CREATE TABLE IF NOT EXISTS food_ingredient_names (
    ingredient_id INTEGER NOT NULL,
    lang          TEXT NOT NULL,
    name          TEXT NOT NULL,
    PRIMARY KEY (ingredient_id, lang)
);
-- How recipe pages have written an ingredient, as food_import._core makes
-- an ingredient line ("cipolle dorate"), and which one it turned out to be.
CREATE TABLE IF NOT EXISTS food_ingredient_aliases (
    alias         TEXT PRIMARY KEY,
    ingredient_id INTEGER NOT NULL
);
-- An ingredient's optional conversions between macro-categories (MACROS),
-- one per pair, kept as entered: a_qty a_unit = b_qty b_unit ("1 tbsp = 12 g").
CREATE TABLE IF NOT EXISTS food_conversions (
    ingredient_id INTEGER NOT NULL,
    pair   TEXT NOT NULL,
    a_qty  REAL NOT NULL,
    a_unit TEXT NOT NULL,
    b_qty  REAL NOT NULL,
    b_unit TEXT NOT NULL,
    PRIMARY KEY (ingredient_id, pair)
);
-- A dish's ingredients, one row each, in the unit the recipe gives it.
CREATE TABLE IF NOT EXISTS food_dish_ingredients (
    dish_id       INTEGER NOT NULL,
    ingredient_id INTEGER NOT NULL,
    position      INTEGER NOT NULL DEFAULT 0,
    quantity      TEXT NOT NULL DEFAULT '',
    unit          TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (dish_id, ingredient_id)
);
CREATE INDEX IF NOT EXISTS idx_food_dish_ingredients_ing ON food_dish_ingredients(ingredient_id);
-- Another dish a dish uses as one of its ingredients (the pizza dough of a
-- pizza), by how much of it, in grams -- how many of its recipes that is
-- follows from what one weighs (dish_grams), whatever its yield says.
-- position is in the same order as the dish's food_dish_ingredients rows.
CREATE TABLE IF NOT EXISTS food_dish_components (
    dish_id      INTEGER NOT NULL,
    component_id INTEGER NOT NULL,
    position     INTEGER NOT NULL DEFAULT 0,
    quantity     TEXT NOT NULL,
    PRIMARY KEY (dish_id, component_id)
);
CREATE INDEX IF NOT EXISTS idx_food_dish_components_comp ON food_dish_components(component_id);
-- A dish's text in the languages other than English (LANGUAGES); field is
-- the food_dishes column it translates.
CREATE TABLE IF NOT EXISTS food_translations (
    dish_id INTEGER NOT NULL,
    field   TEXT NOT NULL,
    lang    TEXT NOT NULL,
    text    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (dish_id, field, lang)
);
-- The categories, in the order they are listed; name is the English one.
CREATE TABLE IF NOT EXISTS food_categories (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);
-- A category's name in the languages other than English (its own name).
CREATE TABLE IF NOT EXISTS food_category_names (
    category_id INTEGER NOT NULL,
    lang        TEXT NOT NULL,
    name        TEXT NOT NULL,
    PRIMARY KEY (category_id, lang)
);
-- A recipe page as fetched: every JSON-LD block in it, and its preparation
-- -- both JSON arrays, the steps each {"text", "images": [{"steps", "url"}]}
-- (giallozafferano.preparation), the text pointing at photos with PHOTO_MARK_RE.
-- By URL; a dish's url finds its page.
CREATE TABLE IF NOT EXISTS food_recipe_pages (
    url         TEXT PRIMARY KEY,
    preparation TEXT NOT NULL DEFAULT '[]',
    json_ld     TEXT NOT NULL DEFAULT '[]',
    fetched_at  TEXT NOT NULL,
    -- What the site shows that schema.org has no field for: {"difficulty"}.
    site_facts  TEXT NOT NULL DEFAULT '{}'
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
# Each stored image also has a small JPEG copy, SMALL_WIDTH wide at most,
# for the cards and lists: small/<its file name>.jpg. Made when the image is
# saved (_store_image); one missing -- an image from before, a copy that
# failed -- is made when first asked for, and all of them on start.
SMALL_DIR = FOOD_IMAGES_DIR / "small"
SMALL_WIDTH = 480  # a card is at most 460px, a phone draws its ~170px at 3x
_small_lock = threading.Lock()


def image_path(name: str, small: bool = False) -> Path | None:
    """A stored image's file; with `small` its small copy, made now if it
    has none yet -- the image itself when it can't be made."""
    base = FOOD_IMAGES_DIR.resolve()
    p = (base / name).resolve()
    if p.parent != base or not p.is_file():
        return None
    return (_small(p) or p) if small else p


def _small(p: Path) -> Path | None:
    """The small copy of the image file `p`, made if it has none."""
    out = SMALL_DIR / f"{p.name}.jpg"
    if out.is_file():
        return out
    with _small_lock:  # one ffmpeg at a time: the start's backfill and a page's requests
        if out.is_file():
            return out
        SMALL_DIR.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.jpg")
        try:
            r = subprocess.run(
                [FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(p), "-frames:v", "1",
                 # Never larger than the image; keeps its shape.
                 "-vf", f"scale='min({SMALL_WIDTH},iw)':-2", "-q:v", "4", str(tmp)],
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"[food] no small copy of {p.name}: {e}")
            tmp.unlink(missing_ok=True)
            return None
        if r.returncode or not tmp.is_file():
            print(f"[food] no small copy of {p.name}: {r.stderr.strip()[:200]}")
            tmp.unlink(missing_ok=True)
            return None
        tmp.replace(out)
        return out


def _store_image(fname: str, raw: bytes) -> str:
    """Save an image into the store under `fname`, with its small copy."""
    (FOOD_IMAGES_DIR / fname).write_bytes(raw)
    _small(FOOD_IMAGES_DIR / fname)
    return fname


def _make_missing_small() -> None:
    """Small copies for the stored images that have none (on start)."""
    made = 0
    for p in sorted(FOOD_IMAGES_DIR.iterdir()):
        if p.is_file() and not (SMALL_DIR / f"{p.name}.jpg").is_file() and _small(p):
            made += 1
    if made:
        print(f"[food] made {made} small image copies")


# ── lifecycle ─────────────────────────────────────────────────────────────
def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database already existed in the wild —
    CREATE TABLE IF NOT EXISTS in _SCHEMA only covers a brand-new DB."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(food_dishes)")}
    if "url" not in cols:
        conn.execute("ALTER TABLE food_dishes ADD COLUMN url TEXT NOT NULL DEFAULT ''")
    if "instructions" not in cols:
        if "description" in cols:
            # Renamed for clarity -- it always held the cooking procedure,
            # never a general "description".
            conn.execute("ALTER TABLE food_dishes RENAME COLUMN description TO instructions")
        else:
            conn.execute("ALTER TABLE food_dishes ADD COLUMN instructions TEXT NOT NULL DEFAULT ''")
    for col in ("yield_qty", "yield_unit"):
        if col not in cols:
            conn.execute(f"ALTER TABLE food_dishes ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    for col, decl in (("prep_min", "INTEGER"), ("cook_min", "INTEGER"), ("total_min", "INTEGER"),
                      ("difficulty", "TEXT NOT NULL DEFAULT ''"),
                      ("source_rating", "TEXT NOT NULL DEFAULT ''"),
                      ("source_rating_count", "TEXT NOT NULL DEFAULT ''"), ("source_comments", "TEXT NOT NULL DEFAULT ''"),
                      ("photos", "TEXT NOT NULL DEFAULT '{}'"), ("import_url", "TEXT NOT NULL DEFAULT ''"),
                      ("import_state", "TEXT NOT NULL DEFAULT '{}'")):
        if col not in cols:
            conn.execute(f"ALTER TABLE food_dishes ADD COLUMN {col} {decl}")
    for col in ("nutrition", "kcal"):
        # The recipe's nutrition list and calories, as imported: to be
        # worked out from the ingredients instead, one day.
        if col in cols:
            conn.execute(f"ALTER TABLE food_dishes DROP COLUMN {col}")
    _migrate_ingredients(conn, cols)
    if "category" in cols:
        _migrate_categories(conn)
    elif not conn.execute("SELECT 1 FROM food_categories LIMIT 1").fetchone():
        conn.executemany("INSERT INTO food_categories (name, position) VALUES (?, ?)",
                         [(c, i) for i, c in enumerate(DEFAULT_CATEGORIES)])
    if conn.execute("PRAGMA user_version").fetchone()[0] < 1:
        _migrate_photo_marks(conn)
        conn.execute("PRAGMA user_version = 1")
    if conn.execute("PRAGMA user_version").fetchone()[0] < 2:
        # Yield units from before they were kept in English (Italian in the
        # English column), and synonyms that read the same in every other
        # language ("porzioni", "Portionen") -- one of each, so the list of
        # the ones in use has no doubles. Their translations stay right.
        for was, now in (("persone", "persons"), ("porzioni", "servings"), ("portions", "servings")):
            conn.execute("UPDATE food_dishes SET yield_unit = ? WHERE yield_unit = ?", (now, was))
        conn.execute("PRAGMA user_version = 2")
    if conn.execute("PRAGMA user_version").fetchone()[0] < 3:
        # The dishes a dish uses were by how much of them in their yield's
        # unit, which meant something else once that changed: grams now.
        weights = _weights(conn, own_only=True)
        for r in conn.execute("SELECT c.dish_id, c.component_id, c.quantity, d.yield_qty FROM food_dish_components c "
                              "JOIN food_dishes d ON d.id = c.component_id").fetchall():
            w = weights.get(r["component_id"])
            if w and _PLAIN_NUMBER_RE.match(r["yield_qty"]) and float(r["yield_qty"]) > 0:
                conn.execute("UPDATE food_dish_components SET quantity = ? WHERE dish_id = ? AND component_id = ?",
                             (_fmt_qty(float(r["quantity"]) / float(r["yield_qty"]) * w), r["dish_id"], r["component_id"]))
        conn.execute("PRAGMA user_version = 3")
    if "html" in {r["name"] for r in conn.execute("PRAGMA table_info(food_recipe_pages)")}:
        # Its first version kept each page's whole HTML. Pages are fetched
        # again when picked again, so the old ones just go.
        conn.execute("DROP TABLE food_recipe_pages")
        conn.execute("CREATE TABLE food_recipe_pages (url TEXT PRIMARY KEY, preparation TEXT NOT NULL DEFAULT '[]', "
                     "json_ld TEXT NOT NULL DEFAULT '[]', fetched_at TEXT NOT NULL)")
    if "site_facts" not in {r["name"] for r in conn.execute("PRAGMA table_info(food_recipe_pages)")}:
        conn.execute("ALTER TABLE food_recipe_pages ADD COLUMN site_facts TEXT NOT NULL DEFAULT '{}'")


def _migrate_categories(conn: sqlite3.Connection) -> None:
    """Categories from when they were known by their English name
    (food_dishes.category, food_category_names.category): food_categories
    rows now, by id -- the default ones, then the others dishes were in, as
    they were listed. Names of a category neither of those is go. The
    INSERTs first: they open the transaction the DDL after them is part of."""
    names = list(DEFAULT_CATEGORIES)
    for (c,) in conn.execute("SELECT DISTINCT category FROM food_dishes WHERE category != '' ORDER BY category"):
        if c not in names:
            names.append(c)
    ids = {n: conn.execute("INSERT INTO food_categories (name, position) VALUES (?, ?)", (n, pos)).lastrowid
           for pos, n in enumerate(names)}
    conn.execute("ALTER TABLE food_dishes ADD COLUMN category_id INTEGER")
    conn.executemany("UPDATE food_dishes SET category_id = ? WHERE category = ?", [(i, n) for n, i in ids.items()])
    conn.execute("ALTER TABLE food_dishes DROP COLUMN category")
    old = conn.execute("SELECT category, lang, name FROM food_category_names").fetchall()
    conn.execute("DROP TABLE food_category_names")
    conn.execute("CREATE TABLE food_category_names (category_id INTEGER NOT NULL, lang TEXT NOT NULL, "
                 "name TEXT NOT NULL, PRIMARY KEY (category_id, lang))")
    conn.executemany("INSERT INTO food_category_names (category_id, lang, name) VALUES (?, ?, ?)",
                     [(ids[r["category"]], r["lang"], r["name"]) for r in old if r["category"] in ids])


def _migrate_ingredients(conn: sqlite3.Connection, dish_cols: set[str]) -> None:
    """From one shopping unit per ingredient (food_ingredients(name, unit))
    and each dish's ingredients as a JSON text column, to ingredient ids and
    food_dish_ingredients rows. The old units were g, ml and "" (a count),
    all units of UNITS still, so every amount carries over as it is."""
    old_list = "unit" in {r["name"] for r in conn.execute("PRAGMA table_info(food_ingredients)")}
    if (old_list or "ingredients" in dish_cols) and not conn.in_transaction:
        conn.execute("BEGIN")  # all of it or none: sqlite3 doesn't open one for DDL
    if old_list:
        conn.execute("ALTER TABLE food_ingredients RENAME TO food_ingredients_old")
        conn.execute("CREATE TABLE food_ingredients ("
                     "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)")
    if old_list or conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'food_ingredients_old'").fetchone():
        # Also the leftover of a run that stopped half way (a reload while
        # this was being written renamed the table, then failed).
        conn.execute("INSERT OR IGNORE INTO food_ingredients (name) SELECT name FROM food_ingredients_old ORDER BY name")
        conn.execute("DROP TABLE food_ingredients_old")
    if "ingredients" in dish_cols:
        for row in conn.execute("SELECT id, ingredients FROM food_dishes WHERE ingredients != ''").fetchall():
            try:
                data = json.loads(row["ingredients"])
                data["ingredients"].items()
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            _set_dish_ingredients(conn, row["id"], data)
        conn.execute("ALTER TABLE food_dishes DROP COLUMN ingredients")


def _photos_shown(text: str, photos: dict) -> str:
    """Instructions from when {{photo:N}} was both a mention and where a
    photo went (each step showing at its start the photos it marked, once a
    file), as they look then with the two told apart: the step's photos a
    {{photo:N}} each on a line above it, its markers {{ref:N}}, a step's
    leading ones -- photos it never mentioned -- gone."""
    blocks: list[list[str]] = []
    for chunk in text.split("\n\n"):
        if blocks and chunk[:1] in (" ", "\t"):
            blocks[-1].append(chunk)  # a further paragraph of the step above
        else:
            blocks.append([chunk])
    out = []
    for block in blocks:
        b = "\n\n".join(block)
        shown: list[str] = []
        for n in re.findall(r"\{\{photo:(\d+)\}\}", b):
            f = photos.get(n)
            if f and f not in [photos[x] for x in shown]:
                shown.append(n)
        m = re.match(r"(\s*\d+\.\s+)?((?:\{\{photo:\d+\}\}\s*)*)", b)
        rest = re.sub(r"\{\{photo:(\d+)\}\}", r"{{ref:\1}}", b[m.end():])
        head = " ".join(photo_mark(int(n)) for n in shown)
        out.append((f"{head}\n" if head else "") + (m[1] or "").lstrip() + rest)
    return "\n\n".join(out)


def _migrate_photo_marks(conn: sqlite3.Connection) -> None:
    """To {{photo:N}} / {{ref:N}} (PHOTO_MARK_RE): the recipe pages' markers
    were all mentions; the dishes' instructions as _photos_shown. Also the
    \"\"\" some translations came back wrapped in."""
    conn.execute("UPDATE food_recipe_pages SET preparation = replace(preparation, '{{photo:', '{{ref:')")
    photos = {r["id"]: json.loads(r["photos"] or "{}") for r in conn.execute("SELECT id, photos FROM food_dishes")}
    for r in conn.execute("SELECT id, instructions FROM food_dishes").fetchall():
        new = _photos_shown(_unquoted(r["instructions"]), photos[r["id"]])
        if new != r["instructions"]:
            conn.execute("UPDATE food_dishes SET instructions = ? WHERE id = ?", (new, r["id"]))
    for r in conn.execute("SELECT dish_id, field, lang, text FROM food_translations").fetchall():
        new = _unquoted(r["text"])
        if r["field"] == "instructions":
            new = _photos_shown(new, photos.get(r["dish_id"], {}))
        if new != r["text"]:
            conn.execute("UPDATE food_translations SET text = ? WHERE dish_id = ? AND field = ? AND lang = ?",
                         (new, r["dish_id"], r["field"], r["lang"]))


def init_db() -> None:
    FOOD_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        if conn.execute("SELECT COUNT(*) FROM food_dishes").fetchone()[0] == 0:
            _seed(conn)
        _seed_missing_ratings(conn)
        # Recipe imports a restart cut short (the nightly reboot, a reload):
        # nothing of them was saved yet, so they start over -- from the
        # sub-recipes picked, when that was where they were.
        interrupted = [(r["id"], json.loads(r["import_state"])) for r in conn.execute(
            "SELECT id, import_state FROM food_dishes WHERE json_extract(import_state, '$.state') = 'running'")]
        for dish_id, st in interrupted:
            _start_import(conn, dish_id, {k: st[k] for k in ("plan", "keep") if k in st})
    _spawn_translations_processing()  # pick up anything left over from before a restart
    threading.Thread(target=_make_missing_small, daemon=True).start()


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
        cat = r.get("category", "").strip()
        cur = conn.execute(
            "INSERT INTO food_dishes(name, category_id, image, position) VALUES(?,?,?,?)",
            (r["name"].strip(), _category_named(conn, {"en": cat}) if cat else None, image, r.get("position", pos)),
        )
        rating = int(r.get("rating", 0) or 0)
        if rating:
            conn.execute(
                "INSERT INTO food_ratings(dish_id, username, rating) VALUES(?,?,?)",
                (cur.lastrowid, SEED_USER, rating),
            )


# ── snapshot (dishes + the caller's own ratings) ────────────────────────
def snapshot(conn: sqlite3.Connection, user: str) -> dict:
    lines: dict[int, list] = {}
    for r in conn.execute(
        "SELECT di.dish_id, i.name, di.quantity, di.unit, di.position FROM food_dish_ingredients di "
        "JOIN food_ingredients i ON i.id = di.ingredient_id ORDER BY di.dish_id, di.position"
    ):
        lines.setdefault(r["dish_id"], []).append(r)
    comps: dict[int, list] = {}
    for r in conn.execute("SELECT dish_id, component_id, quantity, position FROM food_dish_components"):
        comps.setdefault(r["dish_id"], []).append(r)
    weights = _weights(conn)
    translated: dict[tuple[int, str], dict[str, str]] = {}
    for r in conn.execute("SELECT dish_id, field, lang, text FROM food_translations"):
        translated.setdefault((r["dish_id"], r["field"]), {})[r["lang"]] = r["text"]
    category_tr: dict[int, dict[str, str]] = {}
    for r in conn.execute("SELECT category_id, lang, name FROM food_category_names"):
        category_tr.setdefault(r["category_id"], {})[r["lang"]] = r["name"]
    dishes = [
        # name / instructions are the English; *_tr the other languages
        # that have them.
        {"id": r["id"], "name": r["name"], "name_tr": translated.get((r["id"], "name"), {}),
         "category_id": r["category_id"],
         "image": r["image"], "url": r["url"],
         "instructions": r["instructions"],
         "instructions_tr": translated.get((r["id"], "instructions"), {}),
         "ingredients": _ingredients_text(r["yield_qty"], r["yield_unit"], lines.get(r["id"], []),
                                          comps.get(r["id"], [])),
         # The yield's unit (English in `ingredients`) in the other languages.
         "yield_unit_tr": translated.get((r["id"], "yield_unit"), {}),
         # What one recipe of it weighs, in grams (dish_grams); None when
         # nothing of it is in weight -- then no other dish can use it.
         "weight_g": weights.get(r["id"]),
         "facts": _facts(r),
         "photos": json.loads(r["photos"] or "{}"),
         # The recipe import: its state, and whether the linked recipe is
         # the one imported.
         "import": {**{k: v for k, v in json.loads(r["import_state"] or "{}").items() if k not in ("plan", "keep")},
                    "imported": bool(r["url"]) and r["url"] == r["import_url"]},
         "rating": r["rating"]}
        for r in conn.execute(
            "SELECT d.*, COALESCE(rt.rating, 0) AS rating "
            "FROM food_dishes d "
            "LEFT JOIN food_ratings rt ON rt.dish_id = d.id AND rt.username = ? "
            "ORDER BY d.category_id, d.position, d.id",
            (user,),
        )
    ]
    return {
        "dishes": dishes,
        # name is the English; tr the other languages that have it.
        "categories": [{"id": c["id"], "name": c["name"], "tr": category_tr.get(c["id"], {})}
                       for c in _categories(conn)],
        # The ingredient list (food_ingredients) -- ships with the dishes, so
        # a correction reaches the clients on the same poll.
        "ingredients": _catalog_rows(conn),
        "units": [{"unit": u, "macro": m, "factor": f} for u, (m, f) in UNITS.items()],
        "version": get_version(conn, _version_key(user)),
    }


# A dish's facts, editable: prep / cook / total time in minutes, difficulty
# (DIFFICULTIES or ""). The recipe site's rating and comments ride along,
# read-only.
_FACT_COLUMNS = ("prep_min", "cook_min", "total_min", "difficulty")
DIFFICULTIES = ("very_easy", "easy", "medium", "hard", "very_hard")


def _facts(row) -> dict:
    return {"prep_min": row["prep_min"], "cook_min": row["cook_min"], "total_min": row["total_min"],
            "difficulty": row["difficulty"],
            "source_rating": row["source_rating"], "source_rating_count": row["source_rating_count"],
            "source_comments": row["source_comments"]}


def _fact_changes(patch: dict) -> dict:
    """The facts a patch sets, checked -- column -> value. Raises ValueError."""
    out: dict = {}
    for col in ("prep_min", "cook_min", "total_min"):
        if col in patch:
            v = patch[col]
            if v is not None and (not isinstance(v, int) or v < 0):
                raise ValueError(f"{col} is a number of minutes")
            out[col] = v
    if "difficulty" in patch:
        if patch["difficulty"] not in DIFFICULTIES + ("",):
            raise ValueError(f"difficulty is one of {', '.join(DIFFICULTIES)}, or empty")
        out["difficulty"] = patch["difficulty"]
    return out


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


# An uploaded image, as the client sends it: a data: URL of one of these.
_DATA_URL_RE = re.compile(r"^data:image/(jpeg|png|webp|gif);base64,([A-Za-z0-9+/=\s]+)$")
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def store_image_data(data_url: str, name_hint: str) -> str:
    """An uploaded image (a data: URL) into the shared image store; returns
    the stored filename. Raises ValueError for anything but a JPEG / PNG /
    WebP / GIF of at most _MAX_UPLOAD_BYTES."""
    m = _DATA_URL_RE.match(data_url)
    if not m:
        raise ValueError("the image must be a JPEG, PNG, WebP or GIF")
    try:
        raw = base64.b64decode(m[2], validate=False)
    except ValueError:
        raise ValueError("the image is not valid base64")
    if not raw or len(raw) > _MAX_UPLOAD_BYTES:
        raise ValueError("the image is empty or larger than 10 MB")
    return _store_image(f"{_slug(name_hint)}-{secrets.token_hex(4)}.{'jpg' if m[1] == 'jpeg' else m[1]}", raw)


def _new_image(image_url: str | None, image_data: str | None, name_hint: str) -> str:
    """The image a create / edit brings: uploaded, else picked from a search
    (downloaded); "" for none."""
    if image_data:
        return store_image_data(image_data, name_hint)
    return download_image(image_url, name_hint) if image_url else ""


def download_image(url: str, name_hint: str) -> str:
    """Fetch a picked search-result URL into the shared image store; return the
    stored filename. Raises on network / HTTP error."""
    resp = _public_get(url, timeout=20)
    resp.raise_for_status()
    return _store_image(f"{_slug(name_hint)}-{secrets.token_hex(4)}{_ext_for(resp.headers.get('content-type', ''), url)}",
                        resp.content)


# ── LLM (OpenRouter) ──────────────────────────────────────────────────────
def _openrouter(messages: list[dict], **extra) -> dict:
    """One raw OpenRouter chat-completion call, `extra` going into the
    request as it is (tools, ...); returns the reply message. Raises on any
    request/HTTP failure -- callers decide what "the call itself failed"
    should mean for their retry policy, so this doesn't swallow anything.
    Each call is a line in the server log: what for, how long, which
    provider, the tokens -- or how it failed."""
    what = extra["tools"][0]["function"]["name"] if extra.get("tools") else "chat"
    start = time.monotonic()
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": OPENROUTER_MODEL, "messages": messages, **extra},
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:
        print(f"[food llm] {what}: failed after {time.monotonic() - start:.1f}s ({e.__class__.__name__}: {e})")
        raise
    usage = body.get("usage") or {}
    print(f"[food llm] {what}: {time.monotonic() - start:.1f}s, {body.get('provider', '?')}, "
          f"{usage.get('prompt_tokens', '?')} in / {usage.get('completion_tokens', '?')} out")
    return body["choices"][0]["message"]


# ── translations (LLM, a tool call) ─────────────────────────────────────
# The languages a dish's name and instructions, and the categories, are kept
# in, code -> the name the model is told. English is the catalogue's own
# (the food_dishes columns, the category names); the others are
# food_translations / food_category_names rows. Must match the web client's
# LANGUAGES (react_ui/src/i18n).
LANGUAGES = {"en": "english", "it": "italian", "de": "german"}
_TRANSLATED_FIELDS = ("name", "instructions", "yield_unit")  # food_dishes columns

# A recipe's photos in its text, N a photo's number (a dish's `photos`):
# "{{photo:N}}" is the photo itself, shown where it stands -- on a line of
# its own above its step, as imported -- and "{{ref:N}}" the text's mention
# of it, shown as its number ("clean the clams {{ref:1}}"). A recipe page's
# preparation (food_recipe_pages) has only the mentions. Markers no language
# would write, so a translation keeps them as they are -- _translate tells
# the model so, and holds it to the same markers. findall: (kind, N).
PHOTO_MARK_RE = re.compile(r"\{\{(photo|ref):(\d+)\}\}")


def photo_mark(n: int) -> str:
    return f"{{{{photo:{n}}}}}"


def ref_mark(n: int) -> str:
    return f"{{{{ref:{n}}}}}"


class TranslationError(Exception):
    pass


# What is being translated, as the model is told, and anything particular to it.
_TRANSLATE_KINDS = {
    "instructions": ("a recipe's cooking instructions, in Markdown",
                     "A marker like {{photo:3}} is a photo of the recipe, shown where it stands, and one "
                     "like {{ref:3}} the text's mention of that photo: keep every one exactly as it is, "
                     "{{photo:N}} on its own line where it is, {{ref:N}} in the same place of the sentence "
                     "it belongs to; never translate, renumber, add or drop one."),
    "name": ("the name of a dish",
             "A name used as it is in that language -- an international dish or a "
             "proper name (Carbonara, Döner, Tiramisù, Wiener Schnitzel) -- stays "
             "exactly as it is; translate only what that language would say in its own words."),
    "ingredient": ("the name of an ingredient, as it is sold and bought",
                   "Give the plain name a shop and a shopping list use in that language, singular, "
                   "written as that language writes it: English and Italian lowercase (\"onion\", "
                   "\"cipolla\"), German nouns capitalised (\"Zwiebel\").\n"
                   "An ingredient renamed in one language: what matters is the thing bought, not the "
                   "words. Judge from all the names before the edit and the edit what it was: a "
                   "translation corrected or a name respelled -- the other names still name the same "
                   "thing to buy, so they stay exactly as they are; or the ingredient made a different "
                   "thing to buy -- then each other name becomes that thing's name in its language. "
                   "Here that rule comes before copying the edit: a plural, a spelling, an accent or "
                   "a word order changed is never copied into the other languages, and every name "
                   "stays singular."),
    "yield_unit": ("what a recipe's yield counts, the word after its number (\"4 persons\")",
                   "Plural, as after a number above one; the word that language's recipes use "
                   "(\"persons\", \"persone\", \"Personen\"; \"pieces\", \"pezzi\", \"Stück\"). "
                   "English and Italian lowercase, German nouns capitalised."),
    "category": ("the name of a category of dishes in a recipe collection",
                 "A name used as it is in that language (Pasta, Risotti) stays exactly as it is."),
}

_TRANSLATE_SYSTEM_PROMPT = (
    "You keep {what} in sync across languages. You are given the text as it "
    "was just written in one language, and each other language's current "
    "version, if it has one. Call save_translations with every other "
    "language's version.\n\n"
    "A language with a current version: change it only as much as the edit "
    "requires. Find what changed between the text before and after the edit, "
    "and make that same change in it. Every other sentence, word and piece of "
    "formatting stays exactly as it is, even where you would have worded it "
    "differently. If the edit needs nothing changed in it, return it as it is.\n"
    "A language with no current version: translate the text in full, "
    "faithfully, keeping its formatting.\n"
    "{extra}Never add, drop or explain anything."
)


def _translate(kind: str, source: str, before: str, after: str, current: dict[str, str]) -> dict[str, str]:
    """`after`, a text of `kind` (_TRANSLATE_KINDS) just written in `source`
    (where it was `before`), in every other language of LANGUAGES: each
    one's `current` version changed only as the edit requires, or translated
    in full when it has none. Raises TranslationError."""
    if not OPENROUTER_KEY:
        raise TranslationError("no LLM key configured, so nothing can be translated")
    what, extra = _TRANSLATE_KINDS[kind]
    targets = [lang for lang in LANGUAGES if lang != source]
    name = lambda lang: LANGUAGES[lang].capitalize()  # noqa: E731
    parts = [f"EDITED IN: {name(source)}",
             f'BEFORE THE EDIT:\n"""\n{before}\n"""' if before else "BEFORE THE EDIT: (no text yet)",
             f'AFTER THE EDIT:\n"""\n{after}\n"""']
    for lang in targets:
        if current.get(lang):
            parts.append(f'CURRENT {name(lang).upper()} VERSION -- change it only as the edit requires:\n'
                         f'"""\n{current[lang]}\n"""')
        else:
            parts.append(f"{name(lang).upper()}: no version yet -- translate in full.")
    tool = {"type": "function", "function": {
        "name": "save_translations",
        "description": "Save the text in every other language.",
        "parameters": {
            "type": "object",
            "properties": {LANGUAGES[lang]: {"type": "string", "description": f"The full text in {name(lang)}"}
                           for lang in targets},
            "required": [LANGUAGES[lang] for lang in targets],
            "additionalProperties": False,
        },
    }}
    messages = [{"role": "system", "content": _TRANSLATE_SYSTEM_PROMPT.format(
                    what=what, extra=f"{extra}\n" if extra else "")},
                {"role": "user", "content": "\n\n".join(parts)}]
    for _attempt in range(2):
        try:
            msg = _openrouter(messages, tools=[tool], reasoning={"enabled": False},
                              tool_choice={"type": "function", "function": {"name": "save_translations"}})
        except Exception as e:
            raise TranslationError(f"the translation failed: {e}")
        try:
            args = json.loads(msg["tool_calls"][0]["function"]["arguments"])
            out = {lang: _unquoted(str(args[LANGUAGES[lang]])) for lang in targets}
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        marks = sorted(PHOTO_MARK_RE.findall(after))
        if all(out.values()) and all(sorted(PHOTO_MARK_RE.findall(t)) == marks for t in out.values()):
            return out
    raise TranslationError("the translation came back incomplete or with photo markers changed -- try saving again")


def _unquoted(text: str) -> str:
    """A translation without the \"\"\" the prompt quotes texts in, which a
    model sometimes copies around its answer."""
    return re.sub(r'^\s*"""[ \t]*\n?|\n?[ \t]*"""\s*$', "", text).strip()


def _translate_all(jobs: dict, pick=None) -> tuple[dict, str]:
    """Several _translate calls at once (key -> its arguments), and `pick`
    -- a dish's category chosen (_choose_category), no arguments -- alongside
    them: (key -> result, the category picked or ""). Raises the
    TranslationError of any translation that fails."""
    calls = {k: (lambda a=args: _translate(*a)) for k, args in jobs.items()}
    if pick:
        calls["\0pick"] = pick
    if not calls:
        return {}, ""
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = {k: pool.submit(c) for k, c in calls.items()}
        out = {k: f.result() for k, f in futures.items()}
    return out, out.pop("\0pick", "")


_CATEGORY_SYSTEM_PROMPT = (
    "You file a dish into one category of a home recipe collection. You are "
    "given the dish's name, what its recipe page says about it when there is "
    "one, and the collection's categories. Call choose_category with the one "
    "category it belongs in best -- one of the list, exactly as written there."
)


def _choose_category(name: str, url: str, categories: list[str]) -> str:
    """One of `categories` for a dish that has none: picked by the model from
    the dish's name, and what its recipe page says (its own category and
    description, when the page is kept). "" when it can't -- a dish left
    without one is no reason to fail a save."""
    if not OPENROUTER_KEY or not categories:
        return ""
    parts = [f"DISH: {name}"]
    with connect() as conn:
        row = conn.execute("SELECT json_ld FROM food_recipe_pages WHERE url = ?", (url,)).fetchone() if url else None
    if row:
        try:
            recipe = _recipe(json.loads(row["json_ld"]))
        except ValueError:
            recipe = {}
        for label, key in (("ITS RECIPE PAGE'S NAME", "name"), ("ITS RECIPE PAGE'S CATEGORY", "recipeCategory"),
                           ("ITS RECIPE PAGE'S DESCRIPTION", "description")):
            if _ld_text(recipe.get(key)):
                parts.append(f"{label}: {_clean(_ld_text(recipe.get(key)))}")
    parts.append("CATEGORIES:\n" + "\n".join(categories))
    tool = {"type": "function", "function": {
        "name": "choose_category",
        "description": "File the dish into this category.",
        "parameters": {"type": "object", "properties": {"category": {"type": "string", "enum": categories}},
                       "required": ["category"], "additionalProperties": False},
    }}
    try:
        msg = _openrouter([{"role": "system", "content": _CATEGORY_SYSTEM_PROMPT},
                           {"role": "user", "content": "\n\n".join(parts)}],
                          tools=[tool], reasoning={"enabled": False},
                          tool_choice={"type": "function", "function": {"name": "choose_category"}})
        chosen = json.loads(msg["tool_calls"][0]["function"]["arguments"])["category"]
    except Exception:
        return ""
    return chosen if chosen in categories else ""


def _texts(conn: sqlite3.Connection, dish_id: int, field: str) -> dict[str, str]:
    """A dish's `field` (_TRANSLATED_FIELDS), lang -> text, in the languages
    that have it."""
    row = conn.execute(f"SELECT {field} FROM food_dishes WHERE id = ?", (dish_id,)).fetchone()
    if row is None:
        raise KeyError(dish_id)
    out = {"en": row[field]} if row[field] else {}
    for r in conn.execute("SELECT lang, text FROM food_translations WHERE dish_id = ? AND field = ?",
                          (dish_id, field)):
        out[r["lang"]] = r["text"]
    return out


def _set_translations(conn: sqlite3.Connection, dish_id: int, field: str, texts: dict[str, str]) -> None:
    """Replace a dish's `field` in the languages other than English."""
    conn.execute("DELETE FROM food_translations WHERE dish_id = ? AND field = ?", (dish_id, field))
    conn.executemany("INSERT INTO food_translations (dish_id, field, lang, text) VALUES (?, ?, ?, ?)",
                     [(dish_id, field, lang, text) for lang, text in texts.items() if lang != "en" and text])


def name_ingredient(conn: sqlite3.Connection, ingredient_id: int, names: dict[str, str], replace: bool = True) -> None:
    """An ingredient's names in the other languages (lang -> name); with
    `replace` off, a name it has stays."""
    conn.executemany(
        f"INSERT OR {'REPLACE' if replace else 'IGNORE'} INTO food_ingredient_names (ingredient_id, lang, name) "
        "VALUES (?, ?, ?)",
        [(ingredient_id, lang, n.strip().lower() if lang == "it" else n.strip())
         for lang, n in names.items() if lang != "en" and n.strip()])


def _categories(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every category (id, name: its English one), in the order listed."""
    return conn.execute("SELECT id, name FROM food_categories ORDER BY position, id").fetchall()


def _category_names(conn: sqlite3.Connection, category_id: int) -> dict[str, str]:
    """A category's name in every language that has one (lang -> name); {}
    for none."""
    row = conn.execute("SELECT name FROM food_categories WHERE id = ?", (category_id,)).fetchone()
    if row is None:
        return {}
    names = {r["lang"]: r["name"] for r in conn.execute(
        "SELECT lang, name FROM food_category_names WHERE category_id = ?", (category_id,))}
    return {"en": row["name"], **names}


def _find_category(conn: sqlite3.Connection, text: str, lang: str) -> int | None:
    """The category `text` names -- its English name, or its name in `lang`,
    either case -- or None for a new one."""
    low = text.lower()
    for c in _categories(conn):
        if c["name"].lower() == low:
            return c["id"]
    r = conn.execute("SELECT category_id FROM food_category_names WHERE lang = ? AND lower(name) = ?",
                     (lang, low)).fetchone()
    return r["category_id"] if r else None


def _find_yield_unit(conn: sqlite3.Connection, text: str, lang: str) -> dict[str, str] | None:
    """The yield unit `text` names that a dish already has -- its English, or
    its name in `lang`, either case -- in every language that has it
    (lang -> text, "en" its English); None for one no dish has."""
    low = text.lower()
    r = conn.execute("SELECT yield_unit FROM food_dishes WHERE lower(yield_unit) = ? AND yield_unit != ''",
                     (low,)).fetchone()
    if r is None:
        r = conn.execute(
            "SELECT d.yield_unit FROM food_translations t JOIN food_dishes d ON d.id = t.dish_id "
            "WHERE t.field = 'yield_unit' AND t.lang = ? AND lower(t.text) = ? AND d.yield_unit != ''",
            (lang, low)).fetchone()
    if r is None:
        return None
    out = {"en": r["yield_unit"]}
    for t in conn.execute(
        "SELECT t.lang, t.text FROM food_translations t JOIN food_dishes d ON d.id = t.dish_id "
        "WHERE t.field = 'yield_unit' AND d.yield_unit = ?", (r["yield_unit"],)):
        out.setdefault(t["lang"], t["text"])
    return out


def _name_category(conn: sqlite3.Connection, category_id: int, texts: dict[str, str]) -> None:
    """A category's names in the other languages; one it has keeps it."""
    conn.executemany("INSERT OR IGNORE INTO food_category_names (category_id, lang, name) VALUES (?, ?, ?)",
                     [(category_id, lang, text) for lang, text in texts.items() if lang != "en" and text])


def _prepare_texts(conn_texts: dict, lang: str, patch: dict) -> tuple[dict, dict]:
    """What an edit written in `lang` changes of a dish's name, instructions
    and category, and the translations that takes. `conn_texts`: the dish's
    current name and instructions (field -> _texts), and "category_found",
    _find_category of the patch's category. Returns (jobs for _translate_all,
    plain changes: field -> lang -> text for a field cleared or written in
    English without needing a translation)."""
    jobs, plain = {}, {}
    for field in _TRANSLATED_FIELDS:
        if patch.get(field) is None:
            continue
        text = str(patch[field]).strip()
        texts = conn_texts.get(field, {})
        # What the client showed: the language's own, else the English.
        if text == (texts.get(lang) or texts.get("en", "")):
            continue
        if not text:
            if field == "name":
                continue  # a dish always has a name
            plain[field] = {}
        else:
            others = {k: v for k, v in texts.items() if k != lang}
            jobs[field] = (field, lang, texts.get(lang, ""), text, others)
    cat = str(patch.get("category") or "").strip()
    if cat and conn_texts.get("category_found") is None:
        jobs["category"] = ("category", lang, "", cat, {})
    return jobs, plain


_TRANSLATIONS_LOCK = threading.Lock()
_TRANSLATE_BATCH = 4  # translations the background worker asks for at once


def _pending_translations(conn: sqlite3.Connection, skip: set) -> list[tuple]:
    """Texts missing a language -- the generated instructions, and names and
    categories from before translations -- as (key, English text): key is
    ("dish", id, field), ("category", id) or ("ingredient", id)."""
    n = len(LANGUAGES) - 1
    jobs = []
    for field in _TRANSLATED_FIELDS:
        for r in conn.execute(
            f"SELECT id, {field} AS text FROM food_dishes d WHERE {field} != '' AND "
            "(SELECT COUNT(*) FROM food_translations t WHERE t.dish_id = d.id AND t.field = ?) < ? ORDER BY id",
            (field, n),
        ):
            if ("dish", r["id"], field) not in skip:
                jobs.append((("dish", r["id"], field), r["text"]))
    named = {r["category_id"]: r["n"] for r in conn.execute(
        "SELECT category_id, COUNT(*) AS n FROM food_category_names GROUP BY category_id")}
    for c in _categories(conn):
        if named.get(c["id"], 0) < n and ("category", c["id"]) not in skip:
            jobs.append((("category", c["id"]), c["name"]))
    for r in conn.execute(
        "SELECT id, name FROM food_ingredients i WHERE "
        "(SELECT COUNT(*) FROM food_ingredient_names x WHERE x.ingredient_id = i.id) < ? ORDER BY id", (n,),
    ):
        if ("ingredient", r["id"]) not in skip:
            jobs.append((("ingredient", r["id"]), r["name"]))
    return jobs[:_TRANSLATE_BATCH]


def _process_pending_translations() -> None:
    """Fills in the languages texts are missing, _TRANSLATE_BATCH of them at
    once; a worker already running makes this a no-op, it re-queries."""
    if not _TRANSLATIONS_LOCK.acquire(blocking=False):
        return
    failed: set = set()
    try:
        while True:
            with connect() as conn:
                jobs = _pending_translations(conn, failed)
            if not jobs:
                return
            with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                futures = [(key, text, pool.submit(_translate, key[-1] if key[0] == "dish" else key[0],
                                                   "en", "", text, {}))
                           for key, text in jobs]
            with connect() as conn:
                for key, text, f in futures:
                    try:
                        out = f.result()
                    except TranslationError:
                        failed.add(key)
                        continue
                    if key[0] == "category":
                        if _category_names(conn, key[1]).get("en") == text:  # not renamed meanwhile
                            _name_category(conn, key[1], out)
                        continue
                    if key[0] == "ingredient":
                        name_ingredient(conn, key[1], out, replace=False)
                        continue
                    # Only if the English is still what was translated; a
                    # language someone filled in meanwhile stays theirs.
                    if _texts(conn, key[1], key[2]).get("en") != text:
                        continue
                    conn.executemany(
                        "INSERT OR IGNORE INTO food_translations (dish_id, field, lang, text) VALUES (?, ?, ?, ?)",
                        [(key[1], key[2], lang, t) for lang, t in out.items()])
                _bump_all(conn)
    finally:
        _TRANSLATIONS_LOCK.release()


def _spawn_translations_processing() -> None:
    threading.Thread(target=_process_pending_translations, daemon=True).start()


# ── units ────────────────────────────────────────────────────────────────
# Every unit a recipe line may be written in: its macro-category, and how
# many of that category's base unit (g, ml, a piece) one of it is. "" is a
# count of whole pieces. Lines keep the unit they were written in; only the
# grocery list converts.
UNITS: dict[str, tuple[str, float]] = {
    "mg": ("mass", 0.001), "g": ("mass", 1), "hg": ("mass", 100), "kg": ("mass", 1000),
    "ml": ("volume", 1), "cl": ("volume", 10), "l": ("volume", 1000),
    "tsp": ("volume", 5), "tbsp": ("volume", 15), "cup": ("volume", 240),
    "glass": ("volume", 200), "coffee cup": ("volume", 50),
    "": ("count", 1),
}
# Also the grocery list's order of preference: mass, then volume, then count.
MACROS = ("mass", "volume", "count")


def _pair(m1: str, m2: str) -> str:
    """The key of a conversion between two macro-categories, either way round."""
    return "-".join(sorted((m1, m2)))


def _rates(convs) -> dict[tuple[str, str], float]:
    """(from macro, to macro) -> how many of the second's base unit one of the
    first's base unit is, for one ingredient's conversions: each one both ways,
    and a missing pair through the third category when the other two are given
    (1 onion = 150 g and 1 onion = 200 ml make 1 g = 1.33 ml)."""
    r = {(m, m): 1.0 for m in MACROS}
    for c in convs:
        (ma, fa), (mb, fb) = UNITS[c["a_unit"]], UNITS[c["b_unit"]]
        k = (c["b_qty"] * fb) / (c["a_qty"] * fa)
        r[(ma, mb)], r[(mb, ma)] = k, 1 / k
    for a in MACROS:
        for b in MACROS:
            if (a, b) not in r:
                via = next((c for c in MACROS if (a, c) in r and (c, b) in r), None)
                if via:
                    r[(a, b)] = r[(a, via)] * r[(via, b)]
    return r


def _convert(qty: float, unit: str, to: str, rates: dict) -> float | None:
    """`qty` `unit` in `to`, or None when the ingredient has no way there."""
    (ma, fa), (mb, fb) = UNITS[unit], UNITS[to]
    k = rates.get((ma, mb))
    return None if k is None else qty * fa * k / fb


def _conversions(conn: sqlite3.Connection) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in conn.execute("SELECT ingredient_id, a_qty, a_unit, b_qty, b_unit FROM food_conversions ORDER BY pair"):
        out.setdefault(r["ingredient_id"], []).append(
            {"a_qty": r["a_qty"], "a_unit": r["a_unit"], "b_qty": r["b_qty"], "b_unit": r["b_unit"]})
    return out


# ── a dish's ingredients ──────────────────────────────────────────────────
# Clients get and send them as canonical JSON text:
#   {"quantity": "<number>", "unit": "<lowercase word>",
#    "ingredients": {"<lowercase singular name>":
#                     {"quantity": "<number-or-empty>", "unit": "<a unit of UNITS>"}, ...},
#    "dishes": {"<dish id>": {"quantity": "<grams>", "position": <int>}, ...}}
# ("quantity"/"unit" at the top are the recipe's yield, "4" "persons"). Each
# ingredient's quantity/unit are separate fields so clients can edit them as
# two plain fields with no parsing of their own. "dishes" (optional; always
# there in what clients get) are the other dishes it uses, by how many
# grams of each; "position" is the line's place among
# all of them, the ingredients filling the other places in their order.
# Stored as the dish's yield columns, its food_dish_ingredients rows and its
# food_dish_components rows.
_LOWER_WORD_RE = re.compile(r"^[a-z]+(?: [a-z]+)*$")
_PLAIN_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _ingredients_text(yield_qty: str, yield_unit: str, lines, comps=()) -> str:
    """A dish's ingredients as the clients get them; "" for none. `lines`
    and `comps` are its rows of food_dish_ingredients / food_dish_components."""
    if not lines and not comps:
        return ""
    order = sorted([(r["position"], False, r) for r in lines] + [(r["position"], True, r) for r in comps],
                   key=lambda x: (x[0], x[1]))
    return json.dumps({"quantity": yield_qty, "unit": yield_unit,
                       "ingredients": {r["name"]: {"quantity": r["quantity"], "unit": r["unit"]}
                                       for _, is_dish, r in order if not is_dish},
                       "dishes": {str(r["component_id"]): {"quantity": r["quantity"], "position": n}
                                  for n, (_, is_dish, r) in enumerate(order) if is_dish}})


def _dish_ingredients_text(conn: sqlite3.Connection, dish_id: int) -> str:
    """One dish's _ingredients_text."""
    r = conn.execute("SELECT yield_qty, yield_unit FROM food_dishes WHERE id = ?", (dish_id,)).fetchone()
    lines = conn.execute(
        "SELECT i.name, di.quantity, di.unit, di.position FROM food_dish_ingredients di "
        "JOIN food_ingredients i ON i.id = di.ingredient_id WHERE di.dish_id = ? ORDER BY di.position",
        (dish_id,),
    ).fetchall()
    comps = conn.execute("SELECT component_id, quantity, position FROM food_dish_components WHERE dish_id = ?",
                         (dish_id,)).fetchall()
    return _ingredients_text(r["yield_qty"], r["yield_unit"], lines, comps)


def _ingredient_id(conn: sqlite3.Connection, name: str) -> int:
    """The id of the ingredient `name`, added to the list if it is not there."""
    conn.execute("INSERT OR IGNORE INTO food_ingredients (name) VALUES (?)", (name,))
    return conn.execute("SELECT id FROM food_ingredients WHERE name = ?", (name,)).fetchone()[0]


def _set_dish_ingredients(conn: sqlite3.Connection, dish_id: int, data: dict | None) -> None:
    """Replace a dish's ingredients with `data` (the JSON shape above, already
    valid), or clear them; a name not in the list joins it. Without "dishes"
    (a recipe import) the dishes it uses stay as they are."""
    conn.execute("DELETE FROM food_dish_ingredients WHERE dish_id = ?", (dish_id,))
    data = data or {"quantity": "", "unit": "", "ingredients": {}, "dishes": {}}
    if "dishes" in data:
        conn.execute("DELETE FROM food_dish_components WHERE dish_id = ?", (dish_id,))
        conn.executemany(
            "INSERT INTO food_dish_components (dish_id, component_id, position, quantity) VALUES (?, ?, ?, ?)",
            [(dish_id, int(cid), e["position"], e["quantity"]) for cid, e in data["dishes"].items()])
    taken = {r[0] for r in conn.execute("SELECT position FROM food_dish_components WHERE dish_id = ?", (dish_id,))}
    free = (n for n in itertools.count() if n not in taken)
    was = conn.execute("SELECT yield_unit FROM food_dishes WHERE id = ?", (dish_id,)).fetchone()
    if was is not None and was["yield_unit"] != str(data["unit"]):
        # Its translations were of the old one: the caller sets the new
        # ones, or the translation worker fills them in.
        conn.execute("DELETE FROM food_translations WHERE dish_id = ? AND field = 'yield_unit'", (dish_id,))
    conn.execute("UPDATE food_dishes SET yield_qty = ?, yield_unit = ? WHERE id = ?",
                 (str(data["quantity"]), str(data["unit"]), dish_id))
    for pos, (name, e) in zip(free, data["ingredients"].items()):
        conn.execute("INSERT INTO food_dish_ingredients (dish_id, ingredient_id, position, quantity, unit) "
                     "VALUES (?, ?, ?, ?, ?)", (dish_id, _ingredient_id(conn, name), pos, e["quantity"], e["unit"]))


_UNIT_LIST = ", ".join(f'"{u}"' for u in UNITS if u)


# A name as someone types it into a dish's ingredients, in any language
# ("Zwiebel", "olio d'oliva"): letters, words joined by a space, an
# apostrophe or a hyphen. What is stored is the list's English name
# (_LOWER_WORD_RE) -- update_dish checks it against the list first.
_TYPED_NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '’-][^\W\d_]+)*$")


def _validate_ingredients_json(text: str, name_re: re.Pattern = _LOWER_WORD_RE) -> tuple[dict | None, list[str]]:
    """(parsed_dict, []) if `text` matches the required shape exactly, else
    (None, [reason, ...]) listing every violation found, not just the first."""
    try:
        data = json.loads(text)
    except Exception as e:
        return None, [f"not valid JSON ({e})"]
    if not isinstance(data, dict) or set(data.keys()) - {"dishes"} != {"quantity", "unit", "ingredients"}:
        return None, ['top-level value must be a JSON object with exactly the keys "quantity", "unit", '
                      '"ingredients" (and optionally "dishes")']
    quantity, unit, ingredients = data.get("quantity"), data.get("unit"), data.get("ingredients")
    dishes = data.get("dishes", {})
    errors: list[str] = []
    if not _PLAIN_NUMBER_RE.match(str(quantity)):
        errors.append('"quantity" must be a plain number (e.g. "4"), no units or text')
    # The yield's unit, in the language it was written in ("persone",
    # "Personen"); update_dish keeps it in English, the others translations.
    if not isinstance(unit, str) or not _TYPED_NAME_RE.match(unit):
        errors.append('"unit" must be word(s), e.g. "persons"')
    if not isinstance(dishes, dict):
        errors.append('"dishes" must be a JSON object')
        return None, errors
    if not isinstance(ingredients, dict) or not (ingredients or dishes):
        errors.append('"ingredients" must be a non-empty JSON object')
        return None, errors  # nothing left that can be checked
    places = set()
    for did, entry in dishes.items():
        if not did.isdigit():
            errors.append(f'dish "{did}" must be a dish id')
        if not isinstance(entry, dict) or set(entry.keys()) != {"quantity", "position"}:
            errors.append(f'dish "{did}" must be an object with exactly "quantity" and "position"')
            continue
        d_qty, d_pos = entry["quantity"], entry["position"]
        if not isinstance(d_qty, str) or not _PLAIN_NUMBER_RE.match(d_qty) or float(d_qty) <= 0:
            errors.append(f'dish "{did}" quantity "{d_qty}" must be its grams, a plain number above 0')
        if (not isinstance(d_pos, int) or isinstance(d_pos, bool) or not 0 <= d_pos < len(ingredients) + len(dishes)
                or d_pos in places):
            errors.append(f'dish "{did}" position {d_pos!r} must be its own place in the list')
        places.add(d_pos)
    for name, entry in ingredients.items():
        if not isinstance(name, str) or not name_re.match(str(name)):
            errors.append(f'ingredient name "{name}" must be lowercase singular word(s), e.g. "onion"')
        if not isinstance(entry, dict) or set(entry.keys()) != {"quantity", "unit"}:
            errors.append(f'ingredient "{name}" must be an object with exactly "quantity" and "unit"')
            continue  # nothing to check quantity/unit against
        i_qty, i_unit = entry["quantity"], entry["unit"]
        if not isinstance(i_qty, str) or not (i_qty == "" or _PLAIN_NUMBER_RE.match(i_qty)):
            errors.append(f'ingredient "{name}" quantity "{i_qty}" must be a plain number or ""')
        if not isinstance(i_unit, str) or i_unit not in UNITS:
            errors.append(f'ingredient "{name}" unit "{i_unit}" must be one of {_UNIT_LIST}, or "" for pieces')
        elif i_unit and not i_qty:
            errors.append(f'ingredient "{name}" has a unit but no quantity -- use "" for both, or give a quantity')
    if errors:
        return None, errors
    return data, []


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
            (SMALL_DIR / f"{fname}.jpg").unlink(missing_ok=True)
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


# ── recipe pages: searched on the recipe sites, fetched and kept ─────────
# What depends on a site's HTML -- its search, a recipe's preparation photos
# or difficulty -- is in its module (giallozafferano.py, chefkoch.py,
# bbcgoodfood.py), searched together by recipe_sites.py. A picked recipe's
# page is fetched and kept in food_recipe_pages, by URL, for the import on
# Save to work from: every schema.org JSON-LD block in it (Recipe,
# NutritionInformation, AggregateRating, InteractionCounter, Organization...)
# -- a web standard, read here -- its preparation, steps with their photos,
# and its site's facts. Any page with a schema.org Recipe works; the sites are
# the ones searched, and the ones whose extras are read.
_JSON_LD_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def _public_text(url: str) -> str:
    """A public page's text (_public_get). Raises on network / HTTP error."""
    resp = _public_get(url, timeout=15)
    resp.raise_for_status()
    return resp.text


_QUERIES_SYSTEM_PROMPT = (
    "You are given what someone typed to search for a recipe, in any "
    "language. Call search_queries with it as a cook would type it into a "
    "recipe site's search in each language: the dish's usual name there, "
    "short, no explanations. A dish known by one name everywhere keeps it "
    "(\"carbonara\", \"tiramisu\", \"ramen\"); a query already in a language "
    "stays as it is in that one."
)
_queries_cache: dict[str, dict[str, str]] = {}


def _search_queries(query: str) -> dict[str, str]:
    """`query` in each language a recipe site is searched in (lang -> query),
    by the model; the query as typed for every one when it can't say. Kept
    for the server's life, a search typed again costing nothing."""
    langs = sorted(recipe_sites.languages())
    as_typed = {lang: query for lang in langs}
    key = " ".join(query.lower().split())
    if key in _queries_cache:
        return _queries_cache[key]
    if not OPENROUTER_KEY:
        return as_typed
    tool = {"type": "function", "function": {
        "name": "search_queries",
        "description": "The search in each language.",
        "parameters": {"type": "object", "properties": {LANGUAGES[lang]: {"type": "string"} for lang in langs},
                       "required": [LANGUAGES[lang] for lang in langs], "additionalProperties": False},
    }}
    try:
        msg = _openrouter([{"role": "system", "content": _QUERIES_SYSTEM_PROMPT},
                           {"role": "user", "content": query}],
                          tools=[tool], reasoning={"enabled": False},
                          tool_choice={"type": "function", "function": {"name": "search_queries"}})
        args = json.loads(msg["tool_calls"][0]["function"]["arguments"])
        out = {lang: " ".join(str(args.get(LANGUAGES[lang]) or "").split()) or query for lang in langs}
    except Exception as e:
        print(f"[food search] queries as typed: {e}")
        return as_typed
    if len(_queries_cache) > 500:
        _queries_cache.clear()
    _queries_cache[key] = out
    return out


def recipe_search(query: str) -> dict:
    """The recipe sites' results for `query`, each site asked in its own
    language, ranked together (recipe_sites.search): {"results", "failed",
    "queries": what each language was asked}."""
    queries = _search_queries(query.strip())
    return {**recipe_sites.search(queries, _public_text), "queries": queries}


def _clean(fragment: str) -> str:
    """An HTML fragment's text: tags out, entities decoded, spaces collapsed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _ld_objects(blocks: list) -> list[dict]:
    """Every typed object in the JSON-LD blocks, nested ones and @graph included."""
    out: list[dict] = []

    def walk(x):
        if isinstance(x, dict):
            if "@type" in x:
                out.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(blocks)
    return out


def _is_type(obj: dict, name: str) -> bool:
    t = obj.get("@type")
    return t == name or (isinstance(t, list) and name in t)


def _ld_text(v) -> str:
    """A schema.org value that may be a string, a number, an object with a
    name / url / text, or a list of any of those -- as one string."""
    if isinstance(v, list):
        return _ld_text(v[0]) if v else ""
    if isinstance(v, dict):
        return _ld_text(v.get("name") or v.get("url") or v.get("text") or "")
    return "" if v is None else str(v).strip()


def _ld_steps(v) -> list:
    """recipeInstructions as its steps: HowToStep objects or strings, a
    HowToSection's flattened, plain text split into lines."""
    if isinstance(v, str):
        return [line.strip() for line in v.splitlines() if line.strip()]
    out: list = []
    for s in v if isinstance(v, list) else [v]:
        if isinstance(s, dict) and _is_type(s, "HowToSection"):
            out += _ld_steps(s.get("itemListElement") or [])
        elif (isinstance(s, dict) and s.get("text")) or (isinstance(s, str) and s.strip()):
            out.append(s)
    return out


def _ld_step_text(step) -> str:
    return _clean(str(step.get("text", "")) if isinstance(step, dict) else str(step))


def _recipe(blocks: list) -> dict:
    """The page's schema.org Recipe. Raises ValueError when it has none."""
    recipe = next((o for o in _ld_objects(blocks) if _is_type(o, "Recipe")), None)
    if recipe is None:
        raise ValueError("the page has no schema.org Recipe")
    return recipe


def _preparation(url: str, page_html: str, recipe: dict) -> list[dict]:
    """The recipe's steps, each {"text", "images": [{"steps", "url"}]}: its
    site's own, with their photos (GialloZafferano's preparation section),
    else the schema.org steps with the images they have."""
    read = getattr(recipe_sites.site_for(url), "preparation", None)
    steps = read(url, page_html, ref_mark) if read else []
    if steps:
        return steps
    for step in _ld_steps(recipe.get("recipeInstructions") or []):
        img = step.get("image") if isinstance(step, dict) else None
        urls = [_ld_text(i) for i in (img if isinstance(img, list) else [img] if img else [])]
        steps.append({"text": _ld_step_text(step),
                      "images": [{"steps": [], "url": urljoin(url, u)} for u in urls if u]})
    return steps


def _recipe_summary(url: str, recipe: dict) -> dict:
    """What the dish form gets of a fetched page: its schema.org Recipe's
    name, image, times, yield, ingredient lines, steps, nutrition, rating,
    comments and author ("" / [] / {} where the page has none)."""
    rating = recipe.get("aggregateRating") or {}
    rating = rating if isinstance(rating, dict) else {}
    counters = recipe.get("interactionStatistic") or []
    counters = counters if isinstance(counters, list) else [counters]
    comments = next((c.get("userInteractionCount") for c in counters
                     if isinstance(c, dict) and "Comment" in str(c.get("interactionType", ""))), None)
    nutrition = recipe.get("nutrition") or {}
    return {
        "url": url,
        "name": _clean(_ld_text(recipe.get("name"))),
        "image": _ld_text(recipe.get("image")),
        "description": _clean(_ld_text(recipe.get("description"))),
        "category": _ld_text(recipe.get("recipeCategory")),
        "cuisine": _ld_text(recipe.get("recipeCuisine")),
        "yield": _ld_text(recipe.get("recipeYield")),
        "prep_time": _ld_text(recipe.get("prepTime")),
        "cook_time": _ld_text(recipe.get("cookTime")),
        "total_time": _ld_text(recipe.get("totalTime")),
        "ingredients": [_clean(str(i)) for i in recipe.get("recipeIngredient") or []],
        "steps": [_ld_step_text(s) for s in _ld_steps(recipe.get("recipeInstructions") or [])],
        "nutrition": {k: str(v) for k, v in nutrition.items() if not k.startswith("@")}
                     if isinstance(nutrition, dict) else {},
        "rating": _ld_text(rating.get("ratingValue")),
        "rating_count": _ld_text(rating.get("ratingCount") or rating.get("reviewCount")),
        "comments": _ld_text(comments),
        "author": _ld_text(recipe.get("author")),
        "publisher": _ld_text(recipe.get("publisher")),
    }


def _site_difficulty(url: str, page_html: str) -> str:
    """A recipe page's difficulty as its site shows it, "" when it doesn't."""
    read = getattr(recipe_sites.site_for(url), "difficulty", None)
    return read(page_html) if read else ""


def fetch_recipe_page(url: str) -> dict:
    """Fetch a recipe page and keep it (food_recipe_pages: its JSON-LD blocks
    parsed, and its preparation); returns _recipe_summary of it. Raises
    ValueError when it has no schema.org Recipe, else on network / HTTP error."""
    url = url.strip()
    text = _public_text(url)
    blocks = []
    for raw in _JSON_LD_RE.findall(text):
        try:
            blocks.append(json.loads(raw))
        except ValueError:
            continue  # a broken block on someone's page isn't ours to fix
    recipe = _recipe(blocks)
    with connect() as conn:
        conn.execute(
            "INSERT INTO food_recipe_pages (url, preparation, json_ld, fetched_at, site_facts) "
            "VALUES (?, ?, ?, datetime('now'), ?) "
            "ON CONFLICT(url) DO UPDATE SET preparation = excluded.preparation, json_ld = excluded.json_ld, "
            "fetched_at = excluded.fetched_at, site_facts = excluded.site_facts",
            (url, json.dumps(_preparation(url, text, recipe), ensure_ascii=False),
             json.dumps(blocks, ensure_ascii=False),
             json.dumps({"difficulty": _site_difficulty(url, text)})))
    return _recipe_summary(url, recipe)


def recipe_page(url: str) -> dict:
    """A recipe page as kept -- fetched now if it isn't yet: its summary
    (_recipe_summary) and its preparation, for the recipe viewer. Raises as
    fetch_recipe_page does."""
    url = url.strip()
    with connect() as conn:
        row = conn.execute("SELECT preparation, json_ld, fetched_at FROM food_recipe_pages WHERE url = ?",
                           (url,)).fetchone()
    if row is None:
        fetch_recipe_page(url)
        return recipe_page(url)
    return {"recipe": _recipe_summary(url, _recipe(json.loads(row["json_ld"]))),
            "preparation": json.loads(row["preparation"]), "fetched_at": row["fetched_at"]}


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


def _category_named(conn: sqlite3.Connection, names: dict[str, str]) -> int:
    """The category a new name (lang -> text, translated) makes, by its
    English name -- one already there when that is it, else a new one, last
    -- with its names in the other languages; its id."""
    category_id = _find_category(conn, names["en"], "en")
    if category_id is None:
        category_id = conn.execute(
            "INSERT INTO food_categories (name, position) "
            "VALUES (?, (SELECT COALESCE(MAX(position), -1) + 1 FROM food_categories))", (names["en"],)).lastrowid
    _name_category(conn, category_id, names)
    return category_id


def _picked_category(conn: sqlite3.Connection, picked: str) -> int | None:
    """The category _choose_category picked, by its English name."""
    return _find_category(conn, picked, "en") if picked else None


def create_dish(user: str, name: str, category: str, rating, image_url: str | None,
                url: str | None = None, lang: str = "en", image_data: str | None = None) -> dict:
    """A new dish, its name and category written in `lang`: translated into
    the other languages first (all at once), nothing saved if that fails."""
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    if lang not in LANGUAGES:
        raise ValueError(f"no language {lang!r}")
    category = (category or "").strip()
    url = (url or "").strip()
    with connect() as conn:
        found = _find_category(conn, category, lang) if category else 0
        categories = [c["name"] for c in _categories(conn)]
    jobs = {"name": ("name", lang, "", name, {})}
    if found is None:
        jobs["category"] = ("category", lang, "", category, {})
    # No category given: one of the existing ones is chosen for it.
    pick = (lambda: _choose_category(name, url, categories)) if not category else None
    done, picked = _translate_all(jobs, pick)
    full = {k: {lang: jobs[k][3], **v} for k, v in done.items()}
    image = _new_image(image_url, image_data, full["name"]["en"])
    with connect() as conn:
        if found is None:
            found = _category_named(conn, full["category"])
        found = found or _picked_category(conn, picked)
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM food_dishes WHERE category_id IS ?",
            (found,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO food_dishes(name, category_id, image, url, position) VALUES(?,?,?,?,?)",
            (full["name"]["en"], found, image, url, pos),
        )
        dish_id = cur.lastrowid
        _set_translations(conn, dish_id, "name", full["name"])
        r = _clamp_rating(rating)
        if r:
            _set_rating(conn, dish_id, user, r)
        _bump_all(conn)  # new dish visible to everyone
        if url:
            _start_import(conn, dish_id)
        return snapshot(conn, user)


def update_dish(user: str, dish_id: int, patch: dict) -> dict:
    # A name, instructions or category written in `lang` is translated into
    # the other languages before anything is saved -- nothing is saved if
    # that fails -- all the calls at once, and outside the transaction: they
    # take seconds. `full`: field -> lang -> text for each one translated.
    lang = patch.get("lang") or "en"
    if lang not in LANGUAGES:
        raise ValueError(f"no language {lang!r}")
    cat_text = str(patch.get("category") or "").strip()
    with connect() as conn:
        current = {f: _texts(conn, dish_id, f) for f in _TRANSLATED_FIELDS}
        found = _find_category(conn, cat_text, lang) if cat_text else 0
        before = conn.execute("SELECT category_id, url FROM food_dishes WHERE id = ?", (dish_id,)).fetchone()
        categories = [c["name"] for c in _categories(conn)]
    jobs, plain = _prepare_texts({**current, "category_found": found}, lang, patch)
    # A dish this save would leave without a category -- cleared, or never
    # given one -- gets one of the existing ones chosen for it.
    pick = None
    if (patch.get("category") is not None and not cat_text) or (patch.get("category") is None and not before["category_id"]):
        dish_name = str(patch.get("name") or "").strip() or current["name"].get("en", "")
        dish_url = str(patch["url"]).strip() if patch.get("url") is not None else before["url"]
        pick = lambda: _choose_category(dish_name, dish_url, categories)  # noqa: E731
    # Manual edit from the Ingredients modal (the JSON shape of
    # _validate_ingredients_json): False for "unchanged", else the new
    # ingredients (None: cleared). A name not in the ingredient list is
    # checked against it (food_import.resolve_names) -- a typo, a plural,
    # another language becomes the list's ingredient, one genuinely new
    # joins the list -- alongside the translations.
    ingredients: dict | None | bool = False
    unknown: list[str] = []
    unit_texts: dict[str, str] | None = None  # a new yield unit, lang -> text
    if patch.get("ingredients") is not None:
        with connect() as conn:
            r = conn.execute("SELECT yield_qty, yield_unit FROM food_dishes WHERE id = ?", (dish_id,)).fetchone()
            if r is None:
                raise KeyError(dish_id)
            was = _dish_ingredients_text(conn, dish_id)
            listed = {x["name"] for x in conn.execute("SELECT name FROM food_ingredients")}
        ing = str(patch["ingredients"]).strip()
        if ing != was:
            ingredients = None
            if ing:
                ingredients, errors = _validate_ingredients_json(ing, _TYPED_NAME_RE)
                if errors:
                    raise ValueError("invalid ingredients: " + "; ".join(errors))
                ingredients.setdefault("dishes", {})
                with connect() as conn:
                    _check_components(conn, dish_id, [int(d) for d in ingredients["dishes"]])
                unknown = [n for n in ingredients["ingredients"] if n not in listed]
                # The yield's unit as written in `lang`: English stored, the
                # other languages translated -- unless it is the one shown,
                # or another dish's (its languages taken, no model asked).
                typed_unit, units = ingredients["unit"], current["yield_unit"]
                if typed_unit == units.get(lang):
                    ingredients["unit"] = r["yield_unit"]
                elif typed_unit != r["yield_unit"]:
                    with connect() as conn:
                        unit_texts = _find_yield_unit(conn, typed_unit, lang)
                    if unit_texts is None:
                        jobs["yield_unit"] = ("yield_unit", lang, units.get(lang, ""), typed_unit,
                                              {k: v for k, v in units.items() if k != lang})
    from api.services import food_import  # it imports this module
    with ThreadPoolExecutor(max_workers=1) as pool:
        resolving = pool.submit(food_import.resolve_names, unknown) if unknown else None
        done, picked = _translate_all(jobs, pick)
        resolved = resolving.result() if resolving else {}
    if resolved:
        merged, errors = _merge_lines([(resolved.get(n, {}).get("name", n), e)
                                       for n, e in ingredients["ingredients"].items()])
        if errors:
            raise ValueError("; ".join(errors))
        ingredients["ingredients"] = merged
        for n in merged:
            if not _LOWER_WORD_RE.match(n):
                raise ValueError(f'"{n}" could not be checked against the ingredient list -- try saving again')
    full = {k: {lang: jobs[k][3], **v} for k, v in done.items()}
    if "yield_unit" in full:
        unit_texts = {**full["yield_unit"], "en": full["yield_unit"]["en"].lower()}
    if unit_texts is not None:
        ingredients["unit"] = unit_texts["en"]
    instructions: dict[str, str] | None = full.get("instructions", plain.get("instructions"))
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM food_dishes WHERE id = ?",
            (dish_id,),
        ).fetchone()
        if row is None:
            raise KeyError(dish_id)

        # Only count a shared field as changed if it actually differs — so a
        # rating-only edit (clients still send name/category unchanged) bumps
        # just this user, not everyone.
        shared: dict = {}
        import_after = False
        if "name" in full:
            shared["name"] = full["name"]["en"]
            _set_translations(conn, dish_id, "name", full["name"])
        if patch.get("category") is not None or picked:
            if "category" in full:
                cat = _category_named(conn, full["category"])
            else:
                cat = found or _picked_category(conn, picked)
            if cat != row["category_id"]:
                shared["category_id"] = cat
        if patch.get("url") is not None:
            u = str(patch["url"]).strip()
            if u != row["url"]:
                shared["url"] = u
                if u:
                    # A new recipe is imported (the client asks before
                    # replacing what the dish already has).
                    import_after = True
        if patch.get("image_url") or patch.get("image_data"):
            shared["image"] = _new_image(patch.get("image_url"), patch.get("image_data"),
                                         shared.get("name", row["name"]))
        # The facts, from the dish view.
        for col, v in _fact_changes(patch).items():
            if v != row[col]:
                shared[col] = v
        # Manual edit from the Instructions modal.
        if instructions is not None:
            shared["instructions"] = instructions.get("en", "")

        if shared:
            sets = ", ".join(f"{k} = ?" for k in shared)
            conn.execute(f"UPDATE food_dishes SET {sets} WHERE id = ?",
                         (*shared.values(), dish_id))
            if "image" in shared:
                _forget_image(row["image"])
        if ingredients is not False:
            if ingredients:
                _check_components(conn, dish_id, [int(d) for d in ingredients["dishes"]])  # again, in the transaction
            _set_dish_ingredients(conn, dish_id, ingredients)
            if unit_texts is not None:
                _set_translations(conn, dish_id, "yield_unit", unit_texts)
            shared["ingredients"] = True
            for typed, res in resolved.items():
                iid = _ingredient_id(conn, res["name"])
                if res["new_names"]:
                    name_ingredient(conn, iid, res["new_names"])
                if res["alias"]:
                    conn.execute("INSERT OR REPLACE INTO food_ingredient_aliases (alias, ingredient_id) VALUES (?, ?)",
                                 (res["alias"], iid))
            if any(res["new_names"] is None and res["name"] == typed for typed, res in resolved.items()):
                _spawn_translations_processing()  # new ones left as typed get their names
        if instructions is not None:
            _set_translations(conn, dish_id, "instructions", instructions or {})

        rating_given = "rating" in patch and patch["rating"] is not None
        if rating_given:
            _set_rating(conn, dish_id, user, _clamp_rating(patch["rating"]))

        if shared:
            _bump_all(conn)       # catalogue change — everyone refetches
        elif rating_given:
            _bump_user(conn, user)  # only my rating changed
        if import_after:
            _start_import(conn, dish_id)
        return snapshot(conn, user)


def _check_components(conn: sqlite3.Connection, dish_id: int, used: list[int]) -> None:
    """Refuse dishes `dish_id` cannot use: missing ones, ones whose weight
    can't be told (what grams of them are), and ones that use it themselves,
    however far down -- a dish would end up made out of itself."""
    names = {r["id"]: r for r in conn.execute("SELECT id, name, yield_qty FROM food_dishes")}
    weights = _weights(conn)
    uses: dict[int, list[int]] = {}
    for r in conn.execute("SELECT dish_id, component_id FROM food_dish_components"):
        uses.setdefault(r["dish_id"], []).append(r["component_id"])
    for cid in used:
        c = names.get(cid)
        if c is None:
            raise ValueError(f"there is no dish {cid} any more")
        if not weights.get(cid):
            raise ValueError(f'nothing of "{c["name"]}" is in weight -- give its ingredients in grams, or conversions')
        seen, todo = set(), [cid]
        while todo:
            d = todo.pop()
            if d == dish_id:
                raise ValueError("a dish cannot be one of its own ingredients" if cid == dish_id else
                                 f'"{c["name"]}" already uses this dish, so this one cannot use it')
            if d not in seen:
                seen.add(d)
                todo.extend(uses.get(d, []))


def usable_components(conn: sqlite3.Connection, dish_id: int) -> set[int]:
    """The dishes `dish_id` may use (_check_components's rules)."""
    weights = _weights(conn)
    uses: dict[int, list[int]] = {}
    for r in conn.execute("SELECT dish_id, component_id FROM food_dish_components"):
        uses.setdefault(r["dish_id"], []).append(r["component_id"])

    def reaches(d: int, seen: set) -> bool:
        return d == dish_id or (d not in seen and (seen.add(d) or any(reaches(c, seen) for c in uses.get(d, []))))
    return {d for d, w in weights.items() if w and not reaches(d, set())}


def _set_components(conn: sqlite3.Connection, dish_id: int, comps: dict[int, str]) -> None:
    """Replace the dishes `dish_id` uses with `comps` (id -> how much),
    after its ingredients."""
    conn.execute("DELETE FROM food_dish_components WHERE dish_id = ?", (dish_id,))
    start = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM food_dish_ingredients WHERE dish_id = ?",
                         (dish_id,)).fetchone()[0]
    conn.executemany(
        "INSERT INTO food_dish_components (dish_id, component_id, position, quantity) VALUES (?, ?, ?, ?)",
        [(dish_id, cid, start + n, qty) for n, (cid, qty) in enumerate(comps.items())])


def _merge_lines(items: list[tuple[str, dict]]) -> tuple[dict, list[str]]:
    """A dish's ingredient lines (name, {"quantity", "unit"}) with two of one
    name made one: added up when both have an amount, of one kind of unit."""
    out: dict[str, dict] = {}
    errors: list[str] = []
    for name, e in items:
        have = out.get(name)
        if have is None or not have["quantity"]:
            out[name] = dict(e)
        elif e["quantity"]:
            (m1, f1), (m2, f2) = UNITS[have["unit"]], UNITS[e["unit"]]
            if m1 != m2:
                errors.append(f'"{name}" is there twice, in units of different kinds -- give both one')
                continue
            have["quantity"] = _fmt_qty(float(have["quantity"]) + float(e["quantity"]) * f2 / f1)
    return out, errors


def _start_import(conn: sqlite3.Connection, dish_id: int, resume: dict | None = None) -> None:
    """Mark the dish's recipe import running and start it; it runs on its own
    thread once this transaction is committed (food_import.py). `resume`:
    the sub-recipes it found and which were picked ({"plan", "keep"}) -- it
    goes on from there."""
    conn.execute("UPDATE food_dishes SET import_state = ? WHERE id = ?",
                 (json.dumps({"state": "running", "stage": "queued", **(resume or {})}), dish_id))
    from api.services import food_import  # it imports this module
    food_import.start_after_commit(dish_id)


def import_recipe(user: str, dish_id: int) -> dict:
    """Import (again) the recipe a dish links to -- Import / Retry."""
    with connect() as conn:
        row = conn.execute("SELECT url, import_state FROM food_dishes WHERE id = ?", (dish_id,)).fetchone()
        if row is None:
            raise KeyError(dish_id)
        if not row["url"]:
            raise ValueError("the dish has no recipe to import")
        if json.loads(row["import_state"] or "{}").get("state") != "running":
            _start_import(conn, dish_id)
            _bump_all(conn)
        return snapshot(conn, user)


def choose_split(user: str, dish_id: int, keep: list[int]) -> dict:
    """Go on with an import waiting on its sub-recipes (food_import, the
    splitting stage): `keep` the ones picked, by their place in its
    "parts"; none picked keeps the recipe one dish."""
    with connect() as conn:
        row = conn.execute("SELECT import_state FROM food_dishes WHERE id = ?", (dish_id,)).fetchone()
        if row is None:
            raise KeyError(dish_id)
        st = json.loads(row["import_state"] or "{}")
        if st.get("state") != "choosing":
            raise ValueError("the import is not waiting for a choice")
        if any(not 0 <= k < len(st["parts"]) for k in keep):
            raise ValueError("no such sub-recipe")
        _start_import(conn, dish_id, {"plan": st["plan"], "keep": sorted(set(keep))})
        _bump_all(conn)
        return snapshot(conn, user)


def _merge_category(conn: sqlite3.Connection, src: int, dst: int) -> None:
    """Category `src` joins `dst`: its dishes go there, it goes."""
    print(f"[food] category {src} merged into {dst}")
    conn.execute("UPDATE food_dishes SET category_id = ? WHERE category_id = ?", (dst, src))
    conn.execute("DELETE FROM food_category_names WHERE category_id = ?", (src,))
    conn.execute("DELETE FROM food_categories WHERE id = ?", (src,))


def rename_category(user: str, category_id: int, name: str, lang: str = "en") -> dict:
    """Rename a category to `name`, written in `lang`.

    The model is given all its names before and the edit, and changes the
    other languages' only as the edit requires -- outside the transaction,
    it takes seconds; nothing is renamed if it fails. Its dishes have it by
    id, so they stay as they are -- unless another category is called that
    already: then the two become one. Raises KeyError, ValueError,
    TranslationError."""
    if lang not in LANGUAGES:
        raise ValueError(f"no language {lang!r}")
    target = " ".join((name or "").split())
    if not target:
        raise ValueError("a category needs a name")
    with connect() as conn:
        names = _category_names(conn, category_id)
        if not names:
            raise KeyError(category_id)
        if target == names.get(lang, names["en"]):
            return snapshot(conn, user)
        other = _find_category(conn, target, lang)
        if other is not None and other != category_id:
            _merge_category(conn, category_id, other)
            _bump_all(conn)
            return snapshot(conn, user)
    current = {k: v for k, v in names.items() if k != lang}
    out = {lang: target, **_translate("category", lang, names.get(lang, ""), target, current)}
    out = {k: " ".join(_unquoted(v).split()) for k, v in out.items()}
    with connect() as conn:
        if not _category_names(conn, category_id):
            raise KeyError(category_id)
        en = out.get("en") or names["en"]
        other = _find_category(conn, en, "en")
        if other is not None and other != category_id:
            _merge_category(conn, category_id, other)
        else:
            print(f"[food] category {category_id} renamed in {lang}: {names} -> {out}")
            conn.execute("UPDATE food_categories SET name = ? WHERE id = ?", (en, category_id))
            conn.executemany(
                "INSERT OR REPLACE INTO food_category_names (category_id, lang, name) VALUES (?, ?, ?)",
                [(category_id, k, v) for k, v in out.items() if k != "en" and v])
        _bump_all(conn)
        return snapshot(conn, user)


def delete_dish(user: str, dish_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT image, photos FROM food_dishes WHERE id = ?", (dish_id,)
        ).fetchone()
        if row is None:
            raise KeyError(dish_id)
        users = [r["name"] for r in conn.execute(
            "SELECT d.name FROM food_dish_components c JOIN food_dishes d ON d.id = c.dish_id "
            "WHERE c.component_id = ? ORDER BY d.name", (dish_id,))]
        if users:
            raise ValueError("it is an ingredient of " + ", ".join(f'"{n}"' for n in users)
                             + " -- take it out of them first")
        for f in set(json.loads(row["photos"] or "{}").values()):
            _forget_image(f)
        conn.execute("DELETE FROM food_ratings WHERE dish_id = ?", (dish_id,))
        conn.execute("DELETE FROM food_dish_ingredients WHERE dish_id = ?", (dish_id,))
        conn.execute("DELETE FROM food_dish_components WHERE dish_id = ?", (dish_id,))
        conn.execute("DELETE FROM food_translations WHERE dish_id = ?", (dish_id,))
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
    """The list for the clients: each ingredient, its conversions, and how
    many dishes use it."""
    uses = {r["ingredient_id"]: r["n"] for r in conn.execute(
        "SELECT ingredient_id, COUNT(*) AS n FROM food_dish_ingredients GROUP BY ingredient_id")}
    convs = _conversions(conn)
    names: dict[int, dict[str, str]] = {}
    for r in conn.execute("SELECT ingredient_id, lang, name FROM food_ingredient_names"):
        names.setdefault(r["ingredient_id"], {})[r["lang"]] = r["name"]
    return [{"id": r["id"], "name": r["name"], "names": names.get(r["id"], {}), "uses": uses.get(r["id"], 0),
             "conversions": convs.get(r["id"], [])}
            for r in conn.execute("SELECT id, name FROM food_ingredients ORDER BY name")]


def _fmt_qty(x: float) -> str:
    """An amount after a conversion, rounded the way a recipe writes it."""
    x = round(x) if x >= 10 else round(x, 1) if x >= 1 else round(x, 2)
    return f"{x:g}"


def _parse_conversions(raw: list) -> list[dict]:
    """Conversions as a client sent them ([{a_qty, a_unit, b_qty, b_unit}]):
    each between two macro-categories, both amounts positive, at most one
    per pair. Raises IngredientError."""
    out: dict[str, dict] = {}
    for c in raw:
        try:
            a_qty, b_qty = float(c["a_qty"]), float(c["b_qty"])
            a_unit, b_unit = str(c["a_unit"]), str(c["b_unit"])
        except (KeyError, TypeError, ValueError):
            raise IngredientError("a conversion is two amounts and their units")
        if a_unit not in UNITS or b_unit not in UNITS:
            raise IngredientError(f"a unit is one of {_UNIT_LIST}, or pieces")
        if not (a_qty > 0 and b_qty > 0):
            raise IngredientError("a conversion's amounts are positive numbers")
        pair = _pair(UNITS[a_unit][0], UNITS[b_unit][0])
        if UNITS[a_unit][0] == UNITS[b_unit][0]:
            raise IngredientError("a conversion is between two of mass, volume and pieces")
        if pair in out:
            raise IngredientError(f"only one conversion between {pair.replace('-', ' and ')}")
        out[pair] = {"pair": pair, "a_qty": a_qty, "a_unit": a_unit, "b_qty": b_qty, "b_unit": b_unit}
    return list(out.values())


def _save_conversions(conn: sqlite3.Connection, ingredient_id: int, convs: list[dict]) -> None:
    conn.execute("DELETE FROM food_conversions WHERE ingredient_id = ?", (ingredient_id,))
    conn.executemany(
        "INSERT INTO food_conversions (ingredient_id, pair, a_qty, a_unit, b_qty, b_unit) VALUES (?, ?, ?, ?, ?, ?)",
        [(ingredient_id, c["pair"], c["a_qty"], c["a_unit"], c["b_qty"], c["b_unit"]) for c in convs])


def _merge(conn: sqlite3.Connection, src: int, dst: int, src_name: str, dst_name: str) -> None:
    """`src` becomes `dst`: its dishes use `dst`, a dish with both adds them up
    in `dst`'s unit there, and `dst` takes over each conversion of `src` it has
    none of. Raises IngredientError (409) when a dish has both in units no
    conversion links."""
    convs = {c["pair"]: c for c in (
        {**c, "pair": _pair(UNITS[c["a_unit"]][0], UNITS[c["b_unit"]][0])}
        for c in _conversions(conn).get(src, []) + _conversions(conn).get(dst, []))}  # dst's win
    _save_conversions(conn, dst, list(convs.values()))
    rates = _rates(convs.values())
    stuck: list[str] = []
    for r in conn.execute(
        "SELECT s.dish_id, s.quantity AS s_qty, s.unit AS s_unit, d.quantity AS d_qty, d.unit AS d_unit, f.name "
        "FROM food_dish_ingredients s JOIN food_dishes f ON f.id = s.dish_id "
        "LEFT JOIN food_dish_ingredients d ON d.dish_id = s.dish_id AND d.ingredient_id = ? "
        "WHERE s.ingredient_id = ?", (dst, src),
    ).fetchall():
        if r["d_qty"] is None:  # the dish has only src
            conn.execute("UPDATE food_dish_ingredients SET ingredient_id = ? WHERE dish_id = ? AND ingredient_id = ?",
                         (dst, r["dish_id"], src))
            continue
        if r["s_qty"]:
            if not r["d_qty"]:
                qty, unit = r["s_qty"], r["s_unit"]
            else:
                moved = _convert(float(r["s_qty"]), r["s_unit"], r["d_unit"], rates)
                if moved is None:
                    stuck.append(r["name"])
                    continue
                qty, unit = _fmt_qty(float(r["d_qty"]) + moved), r["d_unit"]
            conn.execute("UPDATE food_dish_ingredients SET quantity = ?, unit = ? WHERE dish_id = ? AND ingredient_id = ?",
                         (qty, unit, r["dish_id"], dst))
        conn.execute("DELETE FROM food_dish_ingredients WHERE dish_id = ? AND ingredient_id = ?", (r["dish_id"], src))
    if stuck:
        raise IngredientError(
            f"{', '.join(stuck)} {'has' if len(stuck) == 1 else 'have'} both {src_name!r} and {dst_name!r}, "
            "in units that don't convert -- add a conversion first", 409)
    conn.execute("DELETE FROM food_conversions WHERE ingredient_id = ?", (src,))
    conn.execute("DELETE FROM food_ingredient_names WHERE ingredient_id = ?", (src,))
    conn.execute("UPDATE food_ingredient_aliases SET ingredient_id = ? WHERE ingredient_id = ?", (dst, src))
    conn.execute("DELETE FROM food_ingredients WHERE id = ?", (src,))


def _ingredient_names(conn: sqlite3.Connection, ingredient_id: int) -> dict[str, str]:
    """An ingredient's name in every language that has one (lang -> name)."""
    row = conn.execute("SELECT name FROM food_ingredients WHERE id = ?", (ingredient_id,)).fetchone()
    if row is None:
        return {}
    names = {r["lang"]: r["name"] for r in conn.execute(
        "SELECT lang, name FROM food_ingredient_names WHERE ingredient_id = ?", (ingredient_id,))}
    return {"en": row["name"], **names}


def _ingredient_named(conn: sqlite3.Connection, name: str, lang: str, other_than: int) -> int | None:
    """The ingredient other than `other_than` called `name` in `lang`."""
    if lang == "en":
        r = conn.execute("SELECT id FROM food_ingredients WHERE name = ? AND id != ?",
                         (name.lower(), other_than)).fetchone()
    else:
        r = conn.execute("SELECT ingredient_id AS id FROM food_ingredient_names "
                         "WHERE lang = ? AND lower(name) = ? AND ingredient_id != ? ORDER BY ingredient_id",
                         (lang, name.lower(), other_than)).fetchone()
    return r["id"] if r else None


def _ingredient_name_ok(name: str, lang: str) -> bool:
    """English names are the list's working ones (the import matches against
    them): lowercase words. The others as their language writes them."""
    return bool(_LOWER_WORD_RE.match(name) if lang == "en" else _TYPED_NAME_RE.match(name))


def update_ingredient(user: str, ingredient_id: int, new_name: str | None, conversions: list | None,
                      lang: str = "en") -> dict:
    """Correct one ingredient of the list.

    `conversions`: all of its conversions, replacing the ones it had ([] for
    none). `new_name`: its name in `lang` now. When another ingredient is
    called that in `lang` the two become one (_merge); otherwise the model is
    given all its names before and the edit, and says whether the other
    languages' names change too (a respelling or a translation fixed leaves
    them, a different thing to buy renames them) -- outside the transaction,
    it takes seconds; nothing is renamed if it fails. Raises
    TranslationError."""
    if lang not in LANGUAGES:
        raise IngredientError(f"no language {lang!r}")
    target = (new_name or "").strip()
    target = " ".join(target.split())
    if lang != "de":
        target = target.lower()
    with connect() as conn:
        names = _ingredient_names(conn, ingredient_id)
        if not names:
            raise IngredientError(f"no ingredient {ingredient_id}", 404)
        if conversions is not None:
            _save_conversions(conn, ingredient_id, _parse_conversions(conversions))
        rename = bool(target) and target != names.get(lang)
        if rename and not _ingredient_name_ok(target, lang):
            raise IngredientError("a name is letters, words separated by single spaces")
        other = _ingredient_named(conn, target, lang, ingredient_id) if rename else None
        if other is not None:
            _merge(conn, ingredient_id, other, names.get(lang, names["en"]), target)
            rename = False
        _bump_all(conn)
        if not rename:
            return snapshot(conn, user)
    current = {k: v for k, v in names.items() if k != lang}
    out = {lang: target, **_translate("ingredient", lang, names.get(lang, ""), target, current)}
    with connect() as conn:
        if not _ingredient_names(conn, ingredient_id):
            raise IngredientError(f"no ingredient {ingredient_id}", 404)
        for k in list(out):
            if k == lang:
                continue
            n = out[k] if k == "de" else out[k].lower()
            # One the model got wrong, or another ingredient's: its name stays.
            if not _ingredient_name_ok(n, k) or _ingredient_named(conn, n, k, ingredient_id) is not None:
                print(f"[food] ingredient {ingredient_id}: kept its {k} name, not {n!r}")
                out.pop(k)
            else:
                out[k] = n
        print(f"[food] ingredient {ingredient_id} renamed in {lang}: {names} -> {out}")
        if "en" in out:
            conn.execute("UPDATE food_ingredients SET name = ? WHERE id = ?", (out["en"], ingredient_id))
        name_ingredient(conn, ingredient_id, out)
        _bump_all(conn)
        return snapshot(conn, user)


def delete_ingredient(user: str, ingredient_id: int) -> dict:
    """Take an ingredient off the list -- only one no recipe uses."""
    with connect() as conn:
        row = conn.execute("SELECT name FROM food_ingredients WHERE id = ?", (ingredient_id,)).fetchone()
        if row is None:
            raise IngredientError(f"no ingredient {ingredient_id}", 404)
        used = conn.execute("SELECT COUNT(*) FROM food_dish_ingredients WHERE ingredient_id = ?",
                            (ingredient_id,)).fetchone()[0]
        if used:
            raise IngredientError(f"{used} dish(es) use {row['name']!r} -- rename it into another instead", 409)
        conn.execute("DELETE FROM food_conversions WHERE ingredient_id = ?", (ingredient_id,))
        conn.execute("DELETE FROM food_ingredient_names WHERE ingredient_id = ?", (ingredient_id,))
        conn.execute("DELETE FROM food_ingredient_aliases WHERE ingredient_id = ?", (ingredient_id,))
        conn.execute("DELETE FROM food_ingredients WHERE id = ?", (ingredient_id,))
        _bump_all(conn)
        return snapshot(conn, user)


# ── the grocery list ──────────────────────────────────────────────────────
def _readable(macro: str, base: float) -> dict:
    """A total in its category's base unit, the way it reads best: kg / l
    from 1000 up, and whole pieces -- a third of an onion isn't bought."""
    if macro == "count":
        return {"amount": f"{math.ceil(base - 1e-9):g}", "unit": ""}
    big, small = ("kg", "g") if macro == "mass" else ("l", "ml")
    return {"amount": _fmt_qty(base / 1000), "unit": big} if base >= 1000 else {"amount": _fmt_qty(base), "unit": small}


def _weights(conn: sqlite3.Connection, own_only: bool = False) -> dict[int, float | None]:
    """What one recipe of every dish weighs, in grams: its lines that are in
    mass or convert to it, and the grams of the dishes it uses (unless
    `own_only`). None for one with nothing in weight."""
    convs = _conversions(conn)
    rates: dict[int, dict] = {}
    out: dict[int, float] = {r["id"]: 0.0 for r in conn.execute("SELECT id FROM food_dishes")}
    for r in conn.execute("SELECT dish_id, ingredient_id, quantity, unit FROM food_dish_ingredients WHERE quantity != ''"):
        if r["unit"] in UNITS and r["dish_id"] in out:
            if r["ingredient_id"] not in rates:
                rates[r["ingredient_id"]] = _rates(convs.get(r["ingredient_id"], []))
            out[r["dish_id"]] += _convert(float(r["quantity"]), r["unit"], "g", rates[r["ingredient_id"]]) or 0
    if not own_only:
        for r in conn.execute("SELECT dish_id, quantity FROM food_dish_components"):
            if r["dish_id"] in out:
                out[r["dish_id"]] += float(r["quantity"])
    return {d: (w or None) for d, w in out.items()}


def dish_grams(conn: sqlite3.Connection, dish_id: int) -> float | None:
    """What one recipe of a dish weighs, in grams (_weights)."""
    return _weights(conn).get(dish_id)


def _made(conn: sqlite3.Connection, items: dict[int, float]):
    """How much of every dish is made for `items` (dish id -> how much, in
    its yield's unit), the dishes they use included, and a function giving
    how many times its recipe a dish's amount is."""
    yields = {r["id"]: r["yield_qty"] for r in conn.execute("SELECT id, yield_qty FROM food_dishes")}
    weights = _weights(conn)
    uses: dict[int, list] = {}
    for r in conn.execute("SELECT dish_id, component_id, quantity FROM food_dish_components"):
        uses.setdefault(r["dish_id"], []).append((r["component_id"], float(r["quantity"])))

    def scale_of(dish_id: int, amount: float) -> float:
        base = yields.get(dish_id, "")
        return amount / float(base) if _PLAIN_NUMBER_RE.match(base) and float(base) > 0 else 1

    def amount_of(dish_id: int, recipes: float) -> float:
        base = yields.get(dish_id, "")
        return recipes * float(base) if _PLAIN_NUMBER_RE.match(base) and float(base) > 0 else recipes

    # A dish used by grams is that many of its recipes (one, when its weight
    # can't be told). A loop is refused on save; the depth only guards
    # against one.
    made: dict[int, float] = {}
    todo = [(d, a, 0) for d, a in items.items()]
    while todo:
        d, a, depth = todo.pop()
        made[d] = made.get(d, 0) + a
        if depth < 20:
            todo.extend((c, amount_of(c, g * scale_of(d, a) / weights[c] if weights.get(c) else scale_of(d, a)),
                         depth + 1) for c, g in uses.get(d, []))
    return made, scale_of


def grocery(items: dict[int, float]) -> list[dict]:
    """The shopping list for `items` (dish id -> how much of it is made, in
    its yield's unit): every ingredient of those dishes, scaled and added up
    -- and of the dishes they use, as much of each as they take.
    Each ingredient is totalled in mass when any of its lines is in mass or
    converts to it, else in volume the same way, else in pieces; a line that
    can't get there is totalled the same way on its own, next to it ("200 g +
    3"). `approximate`: some line gave no amount, so it is at least that.
    Each part also has its `macro` and its `base` (total in that macro's base
    unit, unrounded)."""
    if not items:
        return []
    with connect() as conn:
        made, scale_of = _made(conn, items)
        marks = ",".join("?" * len(made))
        rows = conn.execute(
            "SELECT di.dish_id, di.ingredient_id, i.name, di.quantity, di.unit FROM food_dish_ingredients di "
            f"JOIN food_ingredients i ON i.id = di.ingredient_id WHERE di.dish_id IN ({marks})", tuple(made),
        ).fetchall()
        convs = _conversions(conn)
    acc: dict[int, dict] = {}
    for r in rows:
        scale = scale_of(r["dish_id"], made[r["dish_id"]])
        a = acc.setdefault(r["ingredient_id"], {"name": r["name"], "lines": [], "approximate": False})
        if not r["quantity"] or r["unit"] not in UNITS:
            a["approximate"] = True
            continue
        macro, factor = UNITS[r["unit"]]
        a["lines"].append((macro, float(r["quantity"]) * factor * scale))
    out = []
    for iid, a in acc.items():
        rates = _rates(convs.get(iid, []))
        parts, left = [], a["lines"]
        while left:
            target = next(t for t in MACROS if any((m, t) in rates for m, _ in left))
            total = sum(q * rates[(m, target)] for m, q in left if (m, target) in rates)
            # macro/base besides the readable amount: what the client compares
            # a ticked line's bought amount with (500 g vs 1.2 kg).
            parts.append({**_readable(target, total), "macro": target, "base": total})
            left = [(m, q) for m, q in left if (m, target) not in rates]
        out.append({"key": a["name"], "name": a["name"], "parts": parts,
                    "approximate": a["approximate"] and bool(parts)})
    return sorted(out, key=lambda x: x["name"])
