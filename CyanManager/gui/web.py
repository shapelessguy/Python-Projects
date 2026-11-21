"""CyanManager's window, as a web page: the React app in web_ui/ and the API it calls.

Served on this PC only (127.0.0.1, WEB_PORT in .env, 8000 by default): the
tray icon opens it in the browser. Every route acts on this PC, so besides the
loopback binding it refuses a Host other than localhost (DNS rebinding) and a
cross-site Origin (another page in the browser posting here).

What the Qt window did, it does here:
- General: profile, quick password (keyring), each service's Enabled box,
  parameters and "Install dependencies" (service_deps.py), the log terminal.
- Functions: every registered function with a Run button.
- Applications: each application's state, start/kill, window placement and
  settings. Their state (WMI, MultiMonitorTool) is only refreshed while a page
  is asking for it, as the Qt window only did while it was shown.
"""
import os
import threading
import time
from collections import deque

import keyring
import uvicorn
from dotenv import dotenv_values
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import service_deps
from utils import Application, Thread, ENV_PATH, ICONS_FOLDER_PATH, wait

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_PATH = os.path.join(ROOT, "web_ui", "dist")
DEFAULT_PORT = 8000
LOG_LINES = 1000
WATCH_SECONDS = 3  # application state keeps refreshing this long after a page last asked
WIN_STATES = ["normal", "minimized", "maximized", "hidden"]
PROC_TYPES = ["exe", "python", "chrome"]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}

# The Qt widget a service's Parameter names, as the page's field kind
PARAM_KINDS = {"QLineEdit": "text", "QTimeEdit": "time", "QCheckBox": "check", "QComboBox": "select"}


def port() -> int:
    try:
        return int((dotenv_values(ENV_PATH).get("WEB_PORT") or "").strip() or DEFAULT_PORT)
    except ValueError:
        return DEFAULT_PORT


def url() -> str:
    return f"http://localhost:{port()}"


class Logs:
    """What was printed (the Tee's queue), numbered so a page asks only for what it hasn't seen."""
    def __init__(self, signal):
        self.signal = signal
        self.lines = deque(maxlen=LOG_LINES)
        self.next = 0
        self.lock = threading.Lock()

    def run(self):
        while self.signal.is_alive():
            while not self.signal.log_queue.empty():
                line = self.signal.log_queue.get().rstrip()
                if line:
                    with self.lock:
                        self.lines.append((self.next, line))
                        self.next += 1
            wait(self.signal, 50)

    def after(self, seq: int):
        with self.lock:
            return {"next": self.next, "lines": [{"seq": s, "text": t} for s, t in self.lines if s >= seq]}


class AppsWatcher:
    """Applications' state and the screens, refreshed every half second while a page is watching."""
    def __init__(self, signal):
        self.signal = signal
        self.last_asked = 0.0
        self.apps = None  # list[Application] with process/window, from GET_APPS_STATUS
        self.monitors = []
        self.wake = threading.Event()

    def ask(self):
        self.last_asked = time.time()
        self.wake.set()

    def run(self):
        signal = self.signal
        while signal.is_alive():
            if time.time() - self.last_asked > WATCH_SECONDS:
                self.wake.wait(0.5)
                self.wake.clear()
                continue
            try:
                apps = signal.reg_functions.GET_APPS_STATUS.run()
                monitors = signal.reg_functions.GET_SCREENS.run()
                if isinstance(apps, list):
                    self.apps = apps
                    signal.update_exe_table({a.name: a.process.ExecutablePath for a in apps if a.process})
                if isinstance(monitors, list):
                    self.monitors = sorted({str(m._id) for m in monitors})
                wait(signal, 500)
            except Exception as e:
                print(f"web: application state not refreshed: {e.__class__.__name__} - {e}")
                wait(signal, 800)

    def running(self) -> dict:
        return {a.name: bool(a.process or a.window) for a in (self.apps or [])}


class Installs:
    """Services whose dependencies are being installed, and the last failure of each."""
    def __init__(self):
        self.running = set()
        self.errors = {}


def service_status(tm, installs: Installs) -> str:
    if tm.name in installs.running:
        return "installing"
    if not tm.installed():
        return "install_failed" if tm.name in installs.errors else "not_installed"
    if tm.is_alive():
        return "stopping" if tm.to_kill else "running"  # told to stop, still finishing
    return "down"


def saved_threads(signal) -> dict:
    return {t.name: t for t in signal.get_threads()}


def thread_values(tm, saved: dict):
    """(enabled, parameters) of a service as the profile has them, defaults filled in."""
    t = saved.get(tm.name)
    enabled = tm.installed() and (t.enabled if t else True)
    params = {k: p.default for k, p in tm.parameters.items()}
    if t:
        if not tm.installed():  # its PARAMETERS are unknown until imported: keep the profile's
            params = dict(t.parameters)
        else:
            params.update({k: v for k, v in t.parameters.items() if k in tm.parameters})
    return enabled, params


def save_threads(signal, name=None, enabled=None, params=None):
    """Every registered service into the profile, with this one's changes."""
    saved = saved_threads(signal)
    threads = []
    for tm in signal.thread_managers.values():
        t_enabled, t_params = thread_values(tm, saved)
        if tm.name == name:
            if enabled is not None:
                t_enabled = enabled and tm.installed()
            if params:
                t_params.update({k: v for k, v in params.items() if k in t_params})
        threads.append(Thread(tm.name, enabled=t_enabled, parameters=t_params))
    signal.set_threads(threads)


def service_json(signal, tm, saved: dict, installs: Installs) -> dict:
    enabled, values = thread_values(tm, saved)
    params = []
    for k, p in tm.parameters.items():
        kind = PARAM_KINDS.get(getattr(p.type, "__name__", ""), "text")
        params.append({"key": k, "label": k.capitalize(), "kind": kind,
                       "options": list(p.categ or []), "value": values.get(k, p.default)})
    return {
        "name": tm.name,
        "module": tm.module,
        "installed": tm.installed(),
        "enabled": enabled,
        "status": service_status(tm, installs),
        "error": installs.errors.get(tm.name, ""),
        "params": params,
    }


def app_json(app: Application, running: dict, exe_map: dict) -> dict:
    return {
        "name": app.name,
        **app.to_dict(),
        "running": running.get(app.name),  # None until the state is known
        "icon": f"/api/applications/{app.name}/icon?v={abs(hash((app.path, exe_map.get(app.name))))}",
    }


def find_app(signal, name):
    return next((a for a in signal.get_applications() if a.name == name), None)


def create_app(signal, ui_manager) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    logs = Logs(signal)
    watcher = AppsWatcher(signal)
    installs = Installs()
    threading.Thread(target=logs.run, name="web logs", daemon=True).start()
    threading.Thread(target=watcher.run, name="web apps", daemon=True).start()

    @app.middleware("http")
    async def same_site_only(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
        if host not in LOCAL_HOSTS:
            return JSONResponse({"error": "forbidden host"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1].rsplit(":", 1)[0].lower() not in LOCAL_HOSTS:
            return JSONResponse({"error": "forbidden origin"}, status_code=403)
        return await call_next(request)

    # ---- General ----

    @app.get("/api/state")
    def state():
        saved = saved_threads(signal)
        managers = sorted(signal.thread_managers.values(), key=lambda tm: len(tm.parameters))
        modules = {}
        for f_name, f in signal.reg_functions.get_functions().items():
            modules.setdefault(f.module_name, []).append({"name": f_name, "description": f.description})
        return {
            "profile": signal.profile,
            "profiles": signal.get_all_profiles(),
            "password_set": bool(keyring.get_password("CyanManager", signal.profile)),
            "services": [service_json(signal, tm, saved, installs) for tm in managers],
            "functions": [{"module": m.title(), "functions": fs} for m, fs in modules.items()],
        }

    @app.put("/api/profile")
    def set_profile(body: dict):
        name = body.get("profile")
        if name not in signal.get_all_profiles():
            return JSONResponse({"error": f"no profile {name}"}, status_code=404)
        signal.set_profile(name)  # restarts the services
        return {"ok": True}

    @app.put("/api/password")
    def set_password(body: dict):
        keyring.set_password("CyanManager", signal.profile, body.get("password") or "")
        return {"ok": True}

    @app.put("/api/services/{name}")
    def update_service(name: str, body: dict):
        tm = signal.thread_managers.get(name)
        if tm is None:
            return JSONResponse({"error": f"no service {name}"}, status_code=404)
        enabled = body.get("enabled")
        save_threads(signal, name, enabled, body.get("params"))
        if enabled is True and tm.installed() and not tm.is_alive():
            tm.start()
        elif enabled is False and tm.is_alive():
            tm.kill()
            tm.join()
        return {"ok": True}

    @app.post("/api/services/{name}/install")
    def install_service(name: str):
        tm = signal.thread_managers.get(name)
        if tm is None:
            return JSONResponse({"error": f"no service {name}"}, status_code=404)
        if tm.installed() or name in installs.running:
            return {"ok": True}
        installs.running.add(name)
        installs.errors.pop(name, None)
        module = tm.module

        def run():
            try:
                ok, error = service_deps.install(module)
                if ok:
                    service_deps.load(signal, module)
            except Exception as e:
                ok, error = False, f"{e.__class__.__name__}: {e}"
            if ok:
                print(f"Installed the dependencies of {name}")
                save_threads(signal)  # still disabled: enabling is left to the user
            else:
                print(f"Installing the dependencies of {name} failed: {error}")
                installs.errors[name] = error
            installs.running.discard(name)

        threading.Thread(target=run, name=f"install {module}", daemon=True).start()
        return {"ok": True}

    @app.get("/api/logs")
    def get_logs(after: int = 0):
        return logs.after(after)

    # ---- Functions ----

    @app.post("/api/functions/{name}/run")
    def run_function(name: str):
        f = signal.reg_functions.get_functions().get(name)
        if f is None:
            return JSONResponse({"error": f"no function {name}"}, status_code=404)
        result = f.run_shortcut()
        text = repr(result) if result is not None else ""
        return {"ok": True, "result": text[:2000]}

    HOTKEYS_SERVICE = "Hotkeys"

    @app.get("/api/hotkeys")
    def hotkeys():
        """The profile's hotkeys, for the keyboard view, and every function one can be bound to."""
        functions = signal.reg_functions.get_functions()
        tm = signal.thread_managers.get(HOTKEYS_SERVICE)
        return {
            "bindings": [{"vk": h["key"], "modifiers": h.get("modifiers", 0), "function": h["function"],
                          "description": getattr(functions.get(h["function"]), "description", None)}
                         for h in signal.get_hotkeys()],
            "functions": [{"name": n, "description": f.description} for n, f in functions.items()],
            "active": bool(tm and tm.is_alive() and not tm.to_kill),
        }

    @app.put("/api/hotkeys")
    def save_hotkeys(body: dict):
        """The whole list of bindings ({vk, modifiers, function}); the Hotkeys service then restarts the keyboard exe."""
        functions = signal.reg_functions.get_functions()
        hotkeys, seen = [], set()
        for b in body.get("bindings") or []:
            try:
                key, mods, name = int(b["vk"]), int(b.get("modifiers", 0)), str(b["function"])
            except (KeyError, TypeError, ValueError):
                return JSONResponse({"error": f"not a binding: {b}"}, status_code=400)
            if not 0 < key < 256 or not 0 <= mods < 16:
                return JSONResponse({"error": f"no such key: {key} with modifiers {mods}"}, status_code=400)
            if name not in functions:
                return JSONResponse({"error": f"no function {name}"}, status_code=400)
            if (key, mods) in seen:
                return JSONResponse({"error": "the same keys are bound twice"}, status_code=409)
            seen.add((key, mods))
            hotkeys.append({"key": key, "modifiers": mods, "function": name})
        signal.set_hotkeys(hotkeys)
        return {"ok": True}

    # ---- Applications ----

    @app.get("/api/applications")
    def applications():
        watcher.ask()
        running = watcher.running() if watcher.apps is not None else {}
        apps = sorted(signal.get_applications(), key=lambda a: a.name.lower())
        monitors = set(watcher.monitors) | {a.window_props["monitor_id"] for a in apps}
        return {
            "applications": [app_json(a, running, signal.exe_map) for a in apps],
            "monitors": sorted(monitors, key=str),
            "win_states": WIN_STATES,
            "proc_types": PROC_TYPES,
        }

    def merged(current: Application, body: dict) -> Application:
        d = current.to_dict()
        for k in ("window_kw", "excluded_kw", "proc_name", "proc_type", "path", "arguments", "runas", "startup"):
            if k in body:
                d[k] = body[k]
        if isinstance(body.get("window_props"), dict):
            d["window_props"] = {**d["window_props"], **body["window_props"]}
        return Application(body.get("name", current.name).strip(), **d)

    @app.post("/api/applications")
    def add_application(body: dict):
        apps = signal.get_applications()
        new = merged(Application("", [], [], "", "exe", ""), body)
        if not new.name:
            return JSONResponse({"error": "the name is empty"}, status_code=400)
        if any(a.name == new.name for a in apps):
            return JSONResponse({"error": f"{new.name} already exists"}, status_code=409)
        signal.set_applications(apps + [new])
        return {"ok": True, "name": new.name}

    @app.put("/api/applications/{name}")
    def update_application(name: str, body: dict):
        apps = signal.get_applications()
        current = next((a for a in apps if a.name == name), None)
        if current is None:
            return JSONResponse({"error": f"no application {name}"}, status_code=404)
        new = merged(current, body)
        if not new.name:
            return JSONResponse({"error": "the name is empty"}, status_code=400)
        if new.name != name and any(a.name == new.name for a in apps):
            return JSONResponse({"error": f"{new.name} already exists"}, status_code=409)
        signal.set_applications([a for a in apps if a.name != name] + [new])
        return {"ok": True, "name": new.name}

    @app.delete("/api/applications/{name}")
    def remove_application(name: str):
        signal.set_applications([a for a in signal.get_applications() if a.name != name])
        return {"ok": True}

    @app.post("/api/applications/{name}/start")
    def start_application(name: str):
        if find_app(signal, name) is None:
            return JSONResponse({"error": f"no application {name}"}, status_code=404)
        threading.Thread(target=signal.reg_functions.STARTUP.run_shortcut, args=([name],), daemon=True).start()
        return {"ok": True}

    @app.post("/api/applications/{name}/kill")
    def kill_application(name: str):
        application = find_app(signal, name)
        if application is None:
            return JSONResponse({"error": f"no application {name}"}, status_code=404)
        threading.Thread(target=signal.reg_functions.KILL_APP.run_shortcut, args=(application,), daemon=True).start()
        return {"ok": True}

    @app.post("/api/applications/{name}/nudge")
    def nudge_application(name: str, body: dict):
        """One pixel of position or size (prop: x, y, width, height; delta: 1 or -1), then the window follows."""
        prop, delta = body.get("prop"), 1 if body.get("delta", 1) > 0 else -1
        if prop not in ("x", "y", "width", "height"):
            return JSONResponse({"error": f"no property {prop}"}, status_code=400)
        apps = signal.get_applications()
        application = next((a for a in apps if a.name == name), None)
        if application is None:
            return JSONResponse({"error": f"no application {name}"}, status_code=404)
        value = application.window_props[prop] + delta
        if prop in ("width", "height") and value == 0:
            value = 1
        application.window_props[prop] = value
        signal.set_applications(apps)
        signal.reg_functions.ORDER.run_shortcut([name])
        return {"ok": True, "value": value}

    @app.post("/api/applications/save_positions")
    def save_positions():
        """Where the windows are now, into the applications whose placement is on."""
        apps = signal.get_applications()
        positions = signal.reg_functions.GET_WIN_POSITIONS.run_shortcut()
        if not isinstance(positions, dict):
            return JSONResponse({"error": "window positions not read"}, status_code=500)
        for a in apps:
            if a.window_props["order"] and a.name in positions:
                a.window_props = {**a.window_props, **positions[a.name]}
        signal.set_applications(apps)
        return {"ok": True}

    @app.get("/api/applications/{name}/icon")
    def application_icon(name: str):
        application = find_app(signal, name)
        png = ui_manager.app_icon_png(application, signal.exe_map.get(name)) if application else None
        if not png:
            return FileResponse(os.path.join(ICONS_FOLDER_PATH, "cyan_system_manager.png"))
        return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=86400"})

    # ---- The page ----

    app.mount("/icons", StaticFiles(directory=ICONS_FOLDER_PATH), name="icons")
    if os.path.isdir(os.path.join(DIST_PATH, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(DIST_PATH, "assets")), name="assets")

    @app.get("/{path:path}")
    def page(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": "not found"}, status_code=404)
        file = os.path.normpath(os.path.join(DIST_PATH, path))
        if path and file.startswith(DIST_PATH + os.sep) and os.path.isfile(file):
            return FileResponse(file)
        index = os.path.join(DIST_PATH, "index.html")
        if not os.path.exists(index):
            return Response("The page is not built: run `npm install` and `npm run build` in web_ui/.",
                            media_type="text/plain", status_code=503)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


def start(signal, ui_manager):
    """The server in its own thread; it stops with CyanManager."""
    server = uvicorn.Server(uvicorn.Config(create_app(signal, ui_manager), host="127.0.0.1", port=port(),
                                           log_level="warning", timeout_graceful_shutdown=3))

    def run():
        try:
            server.run()
        except Exception as e:
            print(f"web: the page's server stopped: {e.__class__.__name__} - {e}")

    def stop_with_signal():
        while signal.is_alive():
            wait(signal, 500)
        server.should_exit = True

    threading.Thread(target=run, name="web server", daemon=True).start()
    threading.Thread(target=stop_with_signal, name="web server stop", daemon=True).start()
    print(f"CyanManager page: {url()}")
