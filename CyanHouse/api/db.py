"""SQLite storage for the diary. Every row is owned by a `username` and every
query filters on it, so users never see or touch each other's data. The `meta`
table holds monotonic version counters that clients poll to know when to
refetch; the diary counter is per-user (`"<user>:diary_version"`), `weather` is
global."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from api.config import DB_PATH, SEED_DIR, SEED_USER

SCHEMA = """
CREATE TABLE IF NOT EXISTS diary_columns (
    username    TEXT NOT NULL,
    key         TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    unit        TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL DEFAULT 'number',
    position    INTEGER NOT NULL DEFAULT 0,
    options     TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (username, key)
);
CREATE TABLE IF NOT EXISTS diary_units (
    username TEXT NOT NULL,
    unit     TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (username, unit)
);
CREATE TABLE IF NOT EXISTS diary_entries (
    username TEXT NOT NULL,
    date     TEXT NOT NULL,
    key      TEXT NOT NULL,
    value    TEXT,
    PRIMARY KEY (username, date, key)
);
CREATE INDEX IF NOT EXISTS idx_entries_user_date ON diary_entries(username, date);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""


def diary_version_key(user: str) -> str:
    return f"{user}:diary_version"


@contextmanager
def connect(db_path: "str | Path" = DB_PATH):
    """Open a SQLite connection. Defaults to the diary DB; pluggable service
    modules pass their own file so they stay independent of the diary schema."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def bump(conn: sqlite3.Connection, key: str) -> int:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, 1) "
        "ON CONFLICT(key) DO UPDATE SET value = value + 1",
        (key,),
    )
    return conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()[0]


def get_version(conn: sqlite3.Connection, key: str) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return int(row[0]) if row else 0


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('weather_version', 0)")
        _seed_all_users(conn)


def _seed_all_users(conn: sqlite3.Connection) -> None:
    """Seed each configured user that has no columns yet: the SEED_USER gets the
    exported snapshot (columns + units + entries), everyone else the default
    schema + unit pick-list with no entries."""
    from api.auth import USERS  # imported here to avoid a config import cycle

    for user in USERS:
        has_cols = conn.execute(
            "SELECT 1 FROM diary_columns WHERE username = ? LIMIT 1", (user,)
        ).fetchone()
        if has_cols:
            continue
        if user == SEED_USER:
            _seed_owner(conn, user)
        else:
            _seed_default(conn, user)


def _seed_default(conn: sqlite3.Connection, user: str) -> None:
    schema_file = SEED_DIR / "schema.json"
    units_file = SEED_DIR / "units.json"

    if schema_file.exists():
        cols = json.loads(schema_file.read_text("utf-8")).get("columns", [])
        for pos, c in enumerate(cols):
            conn.execute(
                "INSERT INTO diary_columns(username,key,name,description,unit,type,position,options) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (user, c["key"], c["name"], c.get("description", ""), c.get("unit", ""),
                 c.get("type", "number"), pos, json.dumps(c.get("options", []))),
            )

    if units_file.exists():
        units = json.loads(units_file.read_text("utf-8")).get("units", [])
        for pos, u in enumerate(units):
            conn.execute(
                "INSERT OR IGNORE INTO diary_units(username,unit,position) VALUES(?,?,?)",
                (user, u, pos),
            )


def _seed_owner(conn: sqlite3.Connection, user: str) -> None:
    """Restore the exported api/seed/personal_seed.json into `user`'s space."""
    seed_file = SEED_DIR / "personal_seed.json"
    if not seed_file.exists():
        _seed_default(conn, user)
        return
    data = json.loads(seed_file.read_text("utf-8"))

    for pos, c in enumerate(data.get("columns", [])):
        opts = c.get("options", "[]")
        if not isinstance(opts, str):
            opts = json.dumps(opts)
        conn.execute(
            "INSERT INTO diary_columns(username,key,name,description,unit,type,position,options) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (user, c["key"], c["name"], c.get("description", ""), c.get("unit", ""),
             c.get("type", "number"), c.get("position", pos), opts),
        )

    for pos, u in enumerate(data.get("units", [])):
        conn.execute(
            "INSERT OR IGNORE INTO diary_units(username,unit,position) VALUES(?,?,?)",
            (user, u, pos),
        )

    for e in data.get("entries", []):
        d = (e.get("date") or "").strip()
        k = (e.get("key") or "").strip()
        if not d or not k:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO diary_entries(username,date,key,value) VALUES(?,?,?,?)",
            (user, d, k, e.get("value")),
        )
