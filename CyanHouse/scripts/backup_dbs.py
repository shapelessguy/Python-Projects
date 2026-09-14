#!/usr/bin/env python3
"""Backup of CyanHouse's entire data/ directory (not just the .db files --
food images, weather/forecast caches, everything under it) to OneDrive via
rclone.

Triggered by a `@reboot` entry in cyanserver's crontab (not on every API
process restart -- deliberately not tied to api/main.py, since this backend
also restarts on every source file edit during development (reload=True),
and firing a backup on each of those would be noise, not a backup schedule).
DEBOUNCE_MINUTES is still kept as a safety net in case cron's @reboot ever
fires more than once close together.

Every run produces two things, both locally (~/backups/cyanhouse/) and on
OneDrive (CyanHouseBackups/):
  - a timestamped, immutable snapshot -- uploaded once, never touched again
    until it ages out of retention.
  - `current/` -- always rebuilt fresh and exactly mirrors this run's state
    (a file removed from data/ since the last run doesn't linger here
    forever), so there's always one fixed, unambiguous place holding
    "what the data looked like as of the last backup" without hunting
    through timestamped folders.

Retention keeps at most one snapshot per entry in RETENTION_BUCKET_EDGES_DAYS
(the newest snapshot falling in that age range) -- a geometric/logarithmic
scheme in the same family as Time Machine's or rsnapshot's hourly/daily/
weekly/monthly rotation, simplified to a handful of doubling buckets. With
backups roughly once a day (tied to the daily reboot), the default edges
below keep something from today, ~1 day ago, ~2-4 days ago, ~4-8 days ago,
and ~8-16 days ago -- five snapshots spanning over two weeks of history
instead of five consecutive dailies that all cover almost the same week.
Before that, multiple restarts on the same calendar date (e.g. while
debugging) always collapse to just that date's latest snapshot, regardless
of which bucket they'd land in.

Uses sqlite3's own backup API for .db files rather than a plain file copy --
copying the raw file while the backend is mid-write risks grabbing a torn/
inconsistent snapshot; Connection.backup() is safe against concurrent
writers. Every other file under data/ (images, cached datasets, ...) is a
plain copy, which is fine since nothing else under data/ is written to
continuously the way the databases are.

Run manually with `python3 scripts/backup_dbs.py` to back up on demand.
"""
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

RCLONE = Path.home() / ".local" / "bin" / "rclone"
REMOTE = "onedrive:CyanHouseBackups"
SRC_DIR = PROJECT_DIR / "data"
STAGE_DIR = Path.home() / "backups" / "cyanhouse"
DEBOUNCE_MINUTES = 30
RETENTION_BUCKET_EDGES_DAYS = [0, 1, 2, 4, 8, 16]  # 5 buckets -> up to 5 kept
# Direct children of SRC_DIR to skip entirely -- just the weather/forecast
# cache today, which is fetched fresh from public APIs on demand and isn't
# worth backing up.
EXCLUDE_TOP_LEVEL = {"forecast"}

_STAMP_FMT = "%Y%m%d_%H%M%S"


def backup_db(src: Path, dst: Path) -> None:
    src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dst_conn = sqlite3.connect(dst)
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()


def copy_tree(src_root: Path, dst_root: Path) -> list[str]:
    """Every file under src_root into dst_root, preserving relative layout,
    except EXCLUDE_TOP_LEVEL's direct children. Returns the list of relative
    paths copied."""
    copied = []
    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(src_root)
        if rel.parts[0] in EXCLUDE_TOP_LEVEL:
            continue
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".db":
            backup_db(src, dst)
        else:
            shutil.copy2(src, dst)
        copied.append(str(rel))
    return copied


def _parse_stamp(name: str) -> datetime | None:
    try:
        return datetime.strptime(name, _STAMP_FMT)
    except ValueError:
        return None


def _local_snapshot_names() -> list[str]:
    if not STAGE_DIR.exists():
        return []
    return [d.name for d in STAGE_DIR.iterdir() if d.is_dir() and d.name != "current"]


def most_recent_backup_age_minutes() -> float | None:
    times = [t for t in (_parse_stamp(n) for n in _local_snapshot_names()) if t is not None]
    if not times:
        return None
    return (datetime.now() - max(times)).total_seconds() / 60


def _dedupe_same_calendar_day(parsed: list[tuple[str, datetime]]) -> list[tuple[str, datetime]]:
    """Multiple restarts on the same calendar date (e.g. while debugging)
    collapse to just that date's latest -- this is a calendar-date grouping,
    deliberately not "within the last 24 rolling hours": two backups made
    45 minutes apart either side of local midnight are a different calendar
    day each and both survive this step, while two made 20 hours apart on
    the same date do not."""
    by_date: dict = {}
    for s, ts in parsed:
        d = ts.date()
        if d not in by_date or ts > by_date[d][1]:
            by_date[d] = (s, ts)
    return list(by_date.values())


def select_stamps_to_keep(stamps: list[str], now: datetime | None = None) -> set[str]:
    """One kept stamp per age bucket in RETENTION_BUCKET_EDGES_DAYS -- the
    newest stamp falling in that bucket -- after first collapsing same-day
    restarts down to one. Everything else is prunable. `now` is injectable
    (defaults to the real current time) so tests can pin an exact reference
    instant instead of depending on what wall-clock time they happen to run
    at -- calendar-date grouping makes that matter in a way pure rolling-age
    buckets didn't."""
    now = now or datetime.now()
    parsed = [(s, ts) for s, ts in ((s, _parse_stamp(s)) for s in stamps) if ts is not None]
    parsed = _dedupe_same_calendar_day(parsed)
    keep: set[str] = set()
    edges = RETENTION_BUCKET_EDGES_DAYS
    for lo, hi in zip(edges, edges[1:]):
        in_bucket = [(s, ts) for s, ts in parsed if lo <= (now - ts).total_seconds() / 86400 < hi]
        if in_bucket:
            keep.add(max(in_bucket, key=lambda x: x[1])[0])
    return keep


def prune_local() -> None:
    names = _local_snapshot_names()
    keep = select_stamps_to_keep(names)
    for name in names:
        if name not in keep:
            shutil.rmtree(STAGE_DIR / name, ignore_errors=True)


def prune_remote(remote: str) -> None:
    result = subprocess.run([str(RCLONE), "lsf", remote, "--dirs-only"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[backup] couldn't list remote for pruning: {result.stderr.strip()}", file=sys.stderr)
        return
    names = [line.strip().rstrip("/") for line in result.stdout.splitlines()]
    names = [n for n in names if n != "current" and _parse_stamp(n) is not None]
    keep = select_stamps_to_keep(names)
    for name in names:
        if name not in keep:
            subprocess.run([str(RCLONE), "purge", f"{remote}/{name}"], check=False)


def main() -> None:
    age = most_recent_backup_age_minutes()
    if age is not None and age < DEBOUNCE_MINUTES:
        print(f"skipped -- last backup was {age:.1f} min ago (debounce is {DEBOUNCE_MINUTES}m)")
        return

    if not SRC_DIR.exists():
        print(f"nothing found to back up -- {SRC_DIR} doesn't exist", file=sys.stderr)
        return

    stamp = datetime.now().strftime(_STAMP_FMT)
    out_dir = STAGE_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    copied = copy_tree(SRC_DIR, out_dir)
    if not copied:
        print("nothing found to back up", file=sys.stderr)
        shutil.rmtree(out_dir, ignore_errors=True)
        return

    # Timestamped, immutable snapshot -- uploaded once, never touched again.
    subprocess.run([str(RCLONE), "copy", str(out_dir), f"{REMOTE}/{stamp}", "--quiet"], check=True)

    # current/ always exactly mirrors this run's state -- rebuilt fresh
    # (copied from out_dir locally rather than re-read from SRC_DIR, so the
    # sqlite backup API isn't run twice) and synced (not copied) remotely so
    # a file removed since the last run doesn't linger in either place.
    current_dir = STAGE_DIR / "current"
    if current_dir.exists():
        shutil.rmtree(current_dir)
    shutil.copytree(out_dir, current_dir)
    subprocess.run([str(RCLONE), "sync", str(current_dir), f"{REMOTE}/current", "--quiet"], check=True)

    prune_local()
    prune_remote(REMOTE)
    print(f"backed up {len(copied)} files to {REMOTE}/{stamp} and {REMOTE}/current")


if __name__ == "__main__":
    main()
