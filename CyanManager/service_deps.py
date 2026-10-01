"""Each service's own requirements: checked at startup, installed only from the GUI.

A service whose services/<name>/requirements.txt is not all installed is not
imported (its imports would fail): it is registered without a target, under
the NAME read from its service.py, and the General tab shows it with an
"Install dependencies" button instead of a usable Enabled checkbox. The
button runs pip on that file; once nothing is missing the service is imported
and registered for real, and can be enabled.

"Installed" means a distribution of that name is present: versions are not
compared, the launcher never upgrades service requirements. Lines whose
marker does not apply (e.g. torch for another Python) are skipped. What an
install did goes to logs/dependencies.log, like ensure_deps.py.
"""
import ast
import importlib
import importlib.metadata
import os
import re
import site
import subprocess
import sys
from datetime import datetime

try:
    from pip._vendor.packaging.requirements import Requirement
except ImportError:
    from packaging.requirements import Requirement

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVICES_PATH = os.path.join(ROOT, "services")
LOG = os.path.join(ROOT, "logs", "dependencies.log")
COMMENT = re.compile(r"(^|\s)#.*$")


def log(msg: str) -> None:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def requirements_path(module: str) -> str | None:
    path = os.path.join(SERVICES_PATH, module, "requirements.txt")
    return path if os.path.exists(path) else None


def service_name(module: str) -> str | None:
    """NAME from services/<module>/service.py, without importing it: it must be a plain string."""
    with open(os.path.join(SERVICES_PATH, module, "service.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NAME" for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def missing(module: str) -> list[str]:
    """The requirements of this service that are not installed."""
    path = requirements_path(module)
    if not path:
        return []
    absent = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = COMMENT.sub("", line).strip()
            if not line or line.startswith("-"):  # pip options such as --extra-index-url
                continue
            req = Requirement(line)
            if req.marker and not req.marker.evaluate():
                continue
            try:
                importlib.metadata.distribution(req.name)
            except importlib.metadata.PackageNotFoundError:
                absent.append(req.name)
    return absent


def install(module: str) -> tuple[bool, str]:
    """pip-install this service's requirements.txt; (ok, what went wrong)."""
    path = requirements_path(module)
    if not path:
        return True, ""
    log(f"{module}: installing {path}")
    user = [] if sys.prefix != sys.base_prefix else ["--user"]  # a virtualenv refuses --user
    done = subprocess.run([sys.executable, "-m", "pip", "install", *user, "--quiet", "-r", path],
                          capture_output=True, text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    # pip may have just created the user site-packages: Python only puts it on
    # sys.path at startup if it already existed.
    user_site = site.getusersitepackages()
    if os.path.isdir(user_site) and user_site not in sys.path:
        site.addsitedir(user_site)
    importlib.invalidate_caches()
    if done.returncode != 0:
        error = done.stderr.strip()[-500:]
        log(f"{module}: install failed ({done.returncode}): {error}")
        return False, error
    still = missing(module)
    if still:
        log(f"{module}: still missing after install: {', '.join(still)}")
        return False, f"still missing: {', '.join(still)}"
    log(f"{module}: installed")
    return True, ""


def load(signal, module: str) -> bool:
    """Register services/<module>: for real if its requirements are installed, else without a target."""
    absent = missing(module)
    if absent:
        print(f"Service {module} not installed, missing: {', '.join(absent)}")
        signal.register_thread(name=service_name(module) or module, target=None, parameters={}, module=module)
        return False
    service = importlib.import_module(f"services.{module}.service")
    if not hasattr(service, "entrypoint"):
        print(f"Service {module} has no 'entrypoint' function")
        return False
    signal.register_thread(name=service.NAME, target=service.entrypoint, parameters=service.PARAMETERS, module=module)
    return True
