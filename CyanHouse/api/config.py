"""Paths and settings for the API. Importing this also puts the project root on
sys.path so the top-level packages (`api`, `forecast`, `utilities`, `variables`)
resolve no matter where uvicorn is launched from, and loads .env so the port
lives in exactly one place. Nothing here depends on what the project folder or
its parent are named."""
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent     # the folder holding api/, forecast/, ...
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader — real environment variables still win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.split("#", 1)[0].strip())


_load_dotenv(PROJECT_DIR / ".env")

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
FORECAST_POLL_SECONDS = int(os.environ.get("FORECAST_POLL_SECONDS", "3600"))

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

# uvicorn bind address — always all interfaces, not a per-deployment knob.
HOST = "0.0.0.0"
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
# The Room actuator (top/lights/strip/tv/audio -> Arduino over serial) now runs
# in-process — see api/services/room.py — so it only needs the device path.
# The fn service is still a separate process, reached over the LAN.
ARDUINO_DEVICE = os.environ.get("ARDUINO_DEVICE", "").strip()

_fn_addr = os.environ.get("CONTROLS_FN_HOST", "").strip()  # host:port, e.g. LAN IP
CONTROLS_FN_URL = f"http://{_fn_addr}" if _fn_addr else ""
