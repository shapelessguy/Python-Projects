# Cyan House

Client/server rebuild of the old Streamlit dashboard. A FastAPI REST backend
serves both the React web UI and (later) an Android app.

```
<project root>/       (folder name doesn't matter — nothing imports it by name)
  api/              FastAPI backend
    main.py           app entry: auto-discovers routers/, serves react_ui/dist at /
    db.py             SQLite store (api/data/diary.db, auto-seeded from api/seed/)
    models.py         Pydantic request/response models
    services/         weather.py (CSV cache + refresh), forecast.py, diary.py (CRUD), food.py
    routers/          controls.py, environment.py, forecast.py, personal.py, food.py
    seed/             schema.json, units.json, entries.csv, food.json + food_images/
  react_ui/         Vite + React + TypeScript frontend (Plotly charts)
  android_ui/       Jetpack Compose Android client for the same API (see its README)
  utilities/ variables/ monitor_md.py   weather (history) download package
  forecast/         DWD + Open-Meteo precipitation forecast fetch + hourly cache
```

## Adding a service (plug-and-play)

`api/main.py` auto-discovers every module in `api/routers/`. A new service is one
file there — no edit to `main.py` — exposing:

| symbol | required | purpose |
|---|---|---|
| `router: APIRouter` | yes | mounted under its own `/api/<name>` prefix (behind auth) |
| `VERSION_NAMES: list[str]` | no | keys it adds to `/api/version` + `X-<Name>-Version` headers |
| `init()` | no | create its own storage; run once at startup |
| `versions(user) -> dict[str,int]` | no | that user's current counter(s), merged into `/api/version` |

`routers/food.py` + `services/food.py` are the reference implementation: they keep
their own SQLite file (`api/data/food.db`), their own image store
(`api/data/food_images/`) and their own `food_version` counter — nothing touches
the diary schema. `db.connect(path)` takes an optional path so a module can point
at its own file while reusing `bump()` / `get_version()`.

## Run (dev)

Backend — from this project's root directory (the folder holding `api/`), so the
top-level packages resolve. Its name is irrelevant:

```bash
pip install -r requirements.txt
python -m api                        # binds API_PORT from .env (default 10001)
```

`python -m api` is the way to run it — it reads `API_PORT` / `HOST` from `.env`.
The bare `uvicorn api.main:app` form works too but ignores `.env` and defaults to
port 8000, so pass `--port 10001` (matching `.env`) or the web UI's `/api` proxy
won't find it.

Frontend:

```bash
cd react_ui
npm install
npm run dev
```

## Run (single process)

```bash
cd react_ui && npm run build      # emits dist/
cd .. && python -m api
# open http://localhost:10001  (API + UI on one origin)
```

## Auth

Every `/api/*` route requires a **username + token** (HTTP Basic, or a
`diary_auth` cookie holding `base64("user:token")`). Define users via either:

- env var `DIARY_USERS='{"alice":{"token":"tok1","permissions":{}}}'`, or
- `cp api/users.json.example api/users.json` and edit it (git-ignored)

The React UI has a sign-in screen and keeps the credential in the `diary_auth`
cookie; the Android app keeps it in EncryptedSharedPreferences. `/` (the SPA) and
`/docs` stay open; the SPA's own API calls carry the cookie.

**Per-user data.** The **Personal** diary is fully partitioned by username —
every row carries `username` and every query filters on it, so users never see
or affect each other's columns, units, or entries. **Food** is a *shared*
catalogue: a dish's name / category / image is the same for everyone and adding,
renaming, re-imaging or deleting a dish is a global change; only the **rating**
is per-user (`food_ratings(dish_id, username)`). Version counters are per-user
(`"<user>:diary_version"`, `"<user>:food_version"`); a diary write or a rating
change bumps only that user, a shared-catalogue change bumps everyone, `weather`
stays global. On a fresh DB the user named by `SEED_USER` (env, default
`cian_cl`) has the diary restored from `api/seed/personal_seed.json` and gets the
seeded ratings from `api/seed/food.json`; the dish catalogue + images
(`api/data/food_images/`) are shared, so every user sees them. Other configured
users start from the default `schema.json` / `units.json` with unrated dishes.

## API

- `GET  /api/version` → `{diary, weather, food, forecast}` for the calling user — polled every second.
- `GET  /api/environment/bootstrap` → cities, variables, available date range
- `GET  /api/environment/series?cities=&start=&end=&resample=&vars=`
- `POST /api/environment/refresh` → re-download weather, bump `weather`
- `GET  /api/forecast/bootstrap` → cities, per-city `issued_at`, `dwd_hours`
- `GET  /api/forecast/series?cities=` → hourly `precip_mm` / `precip_prob` /
  `source` for the next ~16 days. DWD (MOSMIX via Bright Sky) for the first 72 h
  of German cities, Open-Meteo for the rest. Cached to
  `forecast/datasets/<city>_forecast.csv`, re-fetched hourly by a background
  poller that bumps `forecast`.
- `POST /api/forecast/refresh` → re-fetch now, bump `forecast`
- `GET  /api/controls/info` → OS volume + active audio device (polled ~1 s)
- `POST /api/controls/room/{topic}` `{command, ...}` → the Room actuator
  (in-process, `api/services/room.py`), sent to the Arduino over
  `ARDUINO_DEVICE` from `.env`
- `POST /api/controls/fn/{name}` `{...}?` → forwards to `…/functions/{name}/run`
  on the function server (`CONTROLS_FN_HOST`, a `host:port` on the LAN)
- `GET/POST/PATCH/DELETE /api/personal/columns[/{key}]`
- `PUT /api/personal/columns/order` `{keys:[...]}` → set column order (positions 0..n-1)
- `GET/POST /api/personal/units`, `DELETE /api/personal/units?unit=<name>`
- `GET  /api/personal/entries?month=YYYY-MM` → one row per day of the month
- `PUT  /api/personal/entries/{YYYY-MM-DD}` `{values:{key:val}}` → upsert a day
- `PATCH /api/personal/entries` `{rows:[{date,values}]}` → bulk upsert
- `GET  /api/food/dishes` → `{dishes, categories, version}` — dishes shared,
  each `rating` is the calling user's
- `POST /api/food/dishes` `{name, category, rating, image_url?}` → snapshot
  (dish added for everyone; `rating` is the creator's; a picked `image_url` is
  downloaded into `api/data/food_images/`)
- `PATCH /api/food/dishes/{id}` — `name`/`category`/`image_url` edit the shared
  dish (bumps everyone), `rating` sets just the caller's; `DELETE` removes it
  for everyone → snapshot
- `GET  /api/food/image-search?q=&num=` → server-side proxy to serper.dev
  (needs `SERPER_API_KEY` in `.env`; the key never reaches the clients)
- `GET  /api/food/images/{file}` → a stored dish image

Every mutating call returns the fresh collection (columns list / month rows) so
the UI updates from the response without waiting for the next poll. Interactive
docs at `/docs`.
