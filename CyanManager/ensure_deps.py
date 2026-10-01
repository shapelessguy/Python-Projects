"""Installs CyanManager's requirements at startup.

First the top-level requirements.txt is upgraded with `--no-deps`, which keeps
startup fast but installs nothing a new release starts to depend on (fastapi 0.142 began needing opentelemetry-api,
and the mouse server stopped loading). Then `pip check` names what is missing
in about a second; only that is installed, with its own dependencies. Nearly
every start, nothing is.

A service's own services/<name>/requirements.txt is not touched here: it is
installed only from the GUI (service_deps.py).

Run by launchCyanManagerAsAdmin.vbs with the same Python, before CyanManager
starts. What it did goes to logs/dependencies.log.
"""
import os
import re
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "logs", "dependencies.log")
MISSING = re.compile(r"^(\S+) \S+ requires (\S+), which is not installed\.$")


def log(msg: str) -> None:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def upgrade() -> int:
    done = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--user", "--quiet",
                           "--no-deps", "-r", os.path.join(ROOT, "requirements.txt")],
                          capture_output=True, text=True)
    if done.returncode != 0:
        log(f"upgrade failed ({done.returncode}): {done.stderr.strip()[-500:]}")
    return done.returncode


def install_missing() -> int:
    check = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
    missing = {}
    for line in check.stdout.splitlines():
        m = MISSING.match(line.strip())
        if m:
            missing.setdefault(m.group(2), m.group(1))
    if not missing:
        return 0
    log("missing: " + ", ".join(f"{dep} (needed by {by})" for dep, by in missing.items()))
    done = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", *missing],
                          capture_output=True, text=True)
    log("installed" if done.returncode == 0 else f"install failed ({done.returncode}): {done.stderr.strip()[-500:]}")
    return done.returncode


def main() -> int:
    upgraded = upgrade()
    missing = install_missing()
    return upgraded or missing


if __name__ == "__main__":
    sys.exit(main())
