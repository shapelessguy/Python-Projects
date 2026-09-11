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
import json
import mimetypes
import re
import secrets
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import requests

from api.config import (
    FOOD_DB,
    FOOD_IMAGES_DIR,
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
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS food_ratings (
    dish_id  INTEGER NOT NULL,
    username TEXT NOT NULL,
    rating   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dish_id, username)
);
CREATE INDEX IF NOT EXISTS idx_food_ratings_user ON food_ratings(username);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""

_REQ_HEADERS = {"User-Agent": "Mozilla/5.0 (cyanhouse-food)"}


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
def init_db() -> None:
    FOOD_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(_SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM food_dishes").fetchone()[0] == 0:
            _seed(conn)
        _seed_missing_ratings(conn)


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
        {"id": r["id"], "name": r["name"], "category": r["category"],
         "image": r["image"], "rating": r["rating"]}
        for r in conn.execute(
            "SELECT d.id, d.name, d.category, d.image, "
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
    resp = requests.get(url, headers=_REQ_HEADERS, timeout=20)
    resp.raise_for_status()
    fname = f"{_slug(name_hint)}-{secrets.token_hex(4)}{_ext_for(resp.headers.get('content-type', ''), url)}"
    (FOOD_IMAGES_DIR / fname).write_bytes(resp.content)
    return fname


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
        raise RuntimeError("SERPER_API_KEY is not set in .env")
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


def create_dish(user: str, name: str, category: str, rating, image_url: str | None) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    image = download_image(image_url, name) if image_url else ""
    with connect() as conn:
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM food_dishes WHERE category = ?",
            ((category or "").strip(),),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO food_dishes(name, category, image, position) VALUES(?,?,?,?)",
            (name, (category or "").strip(), image, pos),
        )
        r = _clamp_rating(rating)
        if r:
            _set_rating(conn, cur.lastrowid, user, r)
        _bump_all(conn)  # new dish visible to everyone
        return snapshot(conn, user)


def update_dish(user: str, dish_id: int, patch: dict) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, category, image FROM food_dishes WHERE id = ?", (dish_id,)
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
        if patch.get("image_url"):
            shared["image"] = download_image(patch["image_url"], shared.get("name", row["name"]))

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
        return snapshot(conn, user)


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
