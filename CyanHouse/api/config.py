"""Paths and settings for the API. Importing this also puts the project root on
sys.path so the top-level packages (`api`, `forecast`, `utilities`, `variables`)
resolve no matter where uvicorn is launched from, and loads secrets.json so
every setting (previously split across .env and api/users.json) lives in
exactly one place. Nothing here depends on what the project folder or its
parent are named."""
import json
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent     # the folder holding api/, forecast/, ...
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


# Which keys this loader put into the environment last time it ran. An env
# var it planted itself is not "the environment" -- it is a stale copy of
# this very file, and treating it as an override is what makes editing
# secrets.json appear to do nothing: `python -m api` runs uvicorn with
# reload=True, the parent process loads this module (for API_PORT), and every
# reloaded child inherits the parent's environment. With a plain setdefault
# the child then keeps whatever the file said when the *service* started,
# for as long as the service runs.
_PLANTED = "CYANHOUSE_SECRET_ENV"


def _load_secrets(path: Path) -> dict:
    """Every top-level scalar becomes an environment variable -- see
    secrets.json.example. A real environment variable still wins, same as the
    old .env loader; one this loader planted on an earlier start does not,
    because that is just an older copy of the file being read now.

    Objects and lists are skipped: an env var is a string, and `str()` of a
    dict is not something anything can read back. They stay in the returned
    data for whoever wants them -- "users" for api/auth.py, "movie_staging"
    for the movie prep workflow -- which is also why the skip is by *type*
    rather than a list of known key names that has to be edited every time
    another structured setting is added."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: couldn't parse {path}: {e}")
        return {}
    planted = {k for k in os.environ.get(_PLANTED, "").split(",") if k}
    fresh = []
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            continue
        if key in os.environ and key not in planted:
            continue  # set from outside: that genuinely outranks the file
        os.environ[key] = str(value)
        fresh.append(key)
    os.environ[_PLANTED] = ",".join(fresh)
    return data


_SECRETS = _load_secrets(PROJECT_DIR / "secrets.json")
# api/auth.py's own DIARY_USERS-env-var override still takes precedence over
# this -- see its _load_users().
SECRET_USERS: dict = _SECRETS.get("users", {})

# Root for all generated/runtime data: api's sqlite DBs + food images, the
# forecast cache (forecast/update.py), and the historical weather CSVs
# (utilities/update_data.py). Blank -> each stays exactly where it always
# was, project-relative — forecast/update.py and utilities/update_data.py
# each read this same env var independently (they stay free of any `api`
# import), so this is the one place all three actually share.
_data_dir = os.environ.get("DATA_DIR", "").strip()
DATA_ROOT = Path(_data_dir) if _data_dir else PROJECT_DIR

API_DIR = PROJECT_DIR / "api"
API_DATA_DIR = DATA_ROOT / "api" / "data"
SEED_DIR = API_DIR / "seed"
API_DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("DIARY_DB", API_DATA_DIR / "diary.db"))

# The user whose exported data (api/seed/personal_seed.json + food.json) is
# restored on a fresh DB. Everyone else starts from the default schema / empty.
SEED_USER = os.environ.get("SEED_USER", "cian_cl").strip()

# ── forecast service (self-contained: own CSV cache in forecast/, own poller)
FORECAST_POLL_SECONDS = int(os.environ.get("FORECAST_POLL_SECONDS", "1800"))

# ── food service (self-contained: own DB, own image store) ────────────────
FOOD_DB = Path(os.environ.get("FOOD_DB", API_DATA_DIR / "food.db"))
FOOD_IMAGES_DIR = Path(os.environ.get("FOOD_IMAGES_DIR", API_DATA_DIR / "food_images"))
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "").strip()
SERPER_IMAGE_URL = os.environ.get("SERPER_IMAGE_URL", "https://google.serper.dev/images").strip()

# LLM (OpenRouter) — used to turn a dish's scraped recipe text into a
# formatted description. LLM_FOOD_MODEL is overridable per-deployment
# without touching code; the default is a cheap, fast, widely-available model.
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "").strip()
OPENROUTER_MODEL = os.environ.get("LLM_FOOD_MODEL", "openai/gpt-4o-mini").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ── calendar service (self-contained: own DB) — no external account, local only
CALENDAR_DB = Path(os.environ.get("CALENDAR_DB", API_DATA_DIR / "calendar.db"))

# ── movies service (on-demand ffmpeg transcode of a local film library) ───
# No DB and no index: the library is the filesystem. MOVIES_DIR is scanned on
# demand (cached for MOVIES_SCAN_TTL seconds), everything else is derived from
# ffprobe per file. MOVIES_CACHE_DIR only ever holds throwaway artefacts —
# extracted subtitle tracks — so it lives under the normal data root and can
# be deleted at any time.
MOVIES_DIR = Path(os.environ.get("MOVIES_DIR", "/mnt/pangea/Video/Movies"))
# Staging areas for films that are not library-ready yet: each is an inbox of
# "dirty" downloads plus where a finished one should land. This is where the
# remuxing actually happens -- MOVIES_DIR itself holds files that are already
# done and is only ever read. Shaped as
#   {"<name>": {"inbox": "/path/in", "output": "/path/out"}}
# "output" may be omitted to prepare straight into MOVIES_DIR; "library" is
# accepted as the older spelling of the same key. "inbox" may be omitted
# too: an entry with only an output is somewhere finished work is kept and
# browsed (the series library is configured this way), with nothing staged.
MOVIE_STAGING: dict = _SECRETS.get("movie_staging", {})
MOVIES_CACHE_DIR = Path(os.environ.get("MOVIES_CACHE_DIR", API_DATA_DIR / "movies_cache"))
# Durable, unlike MOVIES_CACHE_DIR above: subtitles uploaded through the UI
# and the index linking them to films live here, and deleting it loses work
# that cannot be regenerated. Kept out of the library itself so the movie
# folders stay exactly as they are.
MOVIES_DATA_DIR = Path(os.environ.get("MOVIES_DATA_DIR", API_DATA_DIR / "movies"))
# A text subtitle is ~150 KB; anything near this is not one.
MOVIES_SUB_MAX_BYTES = int(os.environ.get("MOVIES_SUB_MAX_BYTES", str(8 * 1024 * 1024)))
# Bitmap subtitles are whole images and genuinely large — the VobSub payloads
# in this library run to 11 MB, and a PGS track for a long film more.
MOVIES_SUB_IMAGE_MAX_BYTES = int(
    os.environ.get("MOVIES_SUB_IMAGE_MAX_BYTES", str(64 * 1024 * 1024))
)
MOVIES_SCAN_TTL = int(os.environ.get("MOVIES_SCAN_TTL", "600"))
# "auto" picks h264_nvenc when this ffmpeg build + GPU actually accept it
# (probed once at startup), else libx264. Force one explicitly to skip that.
MOVIES_ENCODER = os.environ.get("MOVIES_ENCODER", "auto").strip()
# Each stream is one ffmpeg process pinning several cores; two at once is
# already most of this box.
MOVIES_MAX_STREAMS = int(os.environ.get("MOVIES_MAX_STREAMS", "2"))
# How long a stream may go unread before it's killed. A paused film reads
# nothing, so this is also the longest a pause survives — after that,
# pressing play just restarts the transcode where it left off.
MOVIES_IDLE_TIMEOUT = int(os.environ.get("MOVIES_IDLE_TIMEOUT", "1800"))
FFMPEG = os.environ.get("FFMPEG", "ffmpeg").strip()
FFPROBE = os.environ.get("FFPROBE", "ffprobe").strip()

# ── film metadata (TMDb) — used to turn a release name into the canonical
# "Title (Year)" the library is organised by. Optional: without it the prep
# workflow still runs, it just can't correct a name it was given.
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()

# Loopback only. nginx runs with network_mode: host and proxies to
# 127.0.0.1:API_PORT, so it is the only thing that needs to reach the backend
# and everything from outside arrives over TLS on 443. Binding all interfaces
# instead would publish the entire API — including the movie streams — in
# cleartext to anyone on the LAN, for no benefit. Overridable for the case
# where something genuinely has to reach it from another machine.
HOST = os.environ.get("API_HOST", "127.0.0.1").strip()
API_PORT = int(os.environ.get("API_PORT", "8000"))
WEB_PORT = int(os.environ.get("WEB_PORT", "5173"))
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "").strip()

FRONTEND_DIST = PROJECT_DIR / "react_ui" / "dist"
DEV_ORIGINS = [
    f"http://{host}:{p}"
    for host in ("localhost", "127.0.0.1")
    for p in (API_PORT, WEB_PORT)
]
if PUBLIC_HOST:
    DEV_ORIGINS += [f"http://{PUBLIC_HOST}:{API_PORT}", f"https://{PUBLIC_HOST}"]

# ── controls (CyanControls home automation) ────────────────────────────────
# The Room actuator (top/lights/strip/tv/audio -> ESP32 boards over HTTP) runs
# in-process — see api/services/room.py — board addresses are hardcoded there
# (ESP32_HOSTS), same as the fn service below.
# The fn service is still a separate process, reached over the LAN.
CONTROLS_FN_HOST = os.environ.get("CONTROLS_FN_HOST", "").strip()  # e.g. LAN IP
CONTROLS_FN_PORT = os.environ.get("CONTROLS_FN_PORT", "").strip()
CONTROLS_FN_URL = f"http://{CONTROLS_FN_HOST}:{CONTROLS_FN_PORT}" if CONTROLS_FN_HOST else ""
