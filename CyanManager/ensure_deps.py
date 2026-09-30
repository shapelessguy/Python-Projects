"""Installs what the packages of requirements.txt need but do not have.

The launcher upgrades requirements.txt with `--no-deps`, which keeps startup
fast but installs nothing a new release starts to depend on (fastapi 0.142
began needing opentelemetry-api, and the mouse server stopped loading).
`pip check` names what is missing in about a second; only that is installed,
with its own dependencies. Nearly every start, nothing is.

Run by launchCyanManagerAsAdmin.vbs with the same Python, right after the
upgrade. What it did goes to logs/dependencies.log.
"""
import os
import re
import subprocess
import sys
from datetime import datetime

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "dependencies.log")
MISSING = re.compile(r"^(\S+) \S+ requires (\S+), which is not installed\.$")


def log(msg: str) -> None:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def main() -> int:
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


if __name__ == "__main__":
    sys.exit(main())
