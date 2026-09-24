"""Check that every song in a music folder can be played to the end.

Each file is decoded in full with ffmpeg (nothing is written) and sorted:

    ok        decodes cleanly, start to end
    glitch    decodes, but ffmpeg reports errors — usually a few broken
              frames at the start of a song cut from a longer file. Players
              that are strict about it (a browser) may refuse the song.
    short     decodes, but stops well before the length its header claims:
              the file is truncated
    broken    cannot be decoded at all

    cd CyanHouse && ../.venv/bin/python scripts/check_audio.py [folder] [--fix]

The folder defaults to MUSIC_DIR. The report goes to data/api/data/music/
audio_check.csv, worst first. --fix repairs the "glitch" MP3s whose broken
frames sit in the silence a song opens with: they are cut out without
re-encoding (at most 1.5 s of silence, tags and cover kept), and the cut is
kept only when the song then decodes cleanly.
"""
import csv
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIO_EXT = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav"}
REPORT = ROOT / "data" / "api" / "data" / "music" / "audio_check.csv"
# Errors only in the first this-many seconds count as a broken start.
START = 0.5


def probe(path: Path) -> float | None:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        return None


def decode(path: Path) -> tuple[float, list[str], list[float]]:
    """Seconds decoded, the error lines, and roughly where each error was.

    -debug_ts is too noisy, so the position comes from decoding with
    progress output: every error line is stamped with the last position
    reported before it."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-progress", "pipe:2", "-stats_period", "0.05",
                        "-i", str(path), "-map", "0:a:0", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=600)
    at, errors, where = 0.0, [], []
    for line in r.stderr.splitlines():
        if line.startswith("out_time_us="):
            try:
                at = max(at, int(line.split("=", 1)[1]) / 1e6)
            except ValueError:
                pass
        elif "=" in line and " " not in line.split("=", 1)[0]:
            continue  # the rest of the progress block
        elif line.strip() and not line.startswith("    Last message repeated"):
            errors.append(line.strip())
            where.append(at)
    return at, errors, where


def check(path: Path, root: Path) -> dict:
    rel = str(path.relative_to(root))
    try:
        length = probe(path)
        seconds, errors, where = decode(path)
    except subprocess.TimeoutExpired:
        return {"path": rel, "status": "broken", "length": "", "decoded": "", "errors": 1,
                "first_error": "timed out", "start_only": False}
    if not seconds and errors:
        status = "broken"
    elif length and seconds < length - max(2.0, length * 0.02):
        status = "short"
    elif errors:
        status = "glitch"
    else:
        status = "ok"
    return {"path": rel, "status": status, "length": round(length or 0, 1), "decoded": round(seconds, 1),
            "errors": len(errors), "first_error": errors[0] if errors else "",
            "start_only": bool(errors) and all(w <= START for w in where)}


def _peak(path: Path, seconds: float) -> float:
    """The loudest point (dB) in the first `seconds` of a file."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-t", str(seconds), "-i", str(path), "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:")[1].split()[0])
            except ValueError:
                pass
    return 0.0


def fix_start(path: Path) -> bool:
    """Cut a song's broken first frames out, without re-encoding — only when
    they sit in the silence songs open with, so nothing audible is lost.

    Songs cut from a longer recording can open with frames that point back
    at audio that is not in the file. ffmpeg only warns about them; Chrome
    gives up on the song."""
    if path.suffix.lower() != ".mp3":
        return False
    tmp = path.with_name(path.stem + ".fixing" + path.suffix)
    for cut in (0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5):
        if _peak(path, cut) > -40:
            break  # it would cut into the music
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(cut), "-i", str(path),
                            "-map", "0:a:0", "-c", "copy", str(tmp)], capture_output=True, text=True)
        if r.returncode or not tmp.exists():
            break
        if not decode(tmp)[1]:
            # The tags and cover, exactly as they were.
            try:
                import mutagen.id3
                mutagen.id3.ID3(path).save(tmp)
            except Exception:
                pass
            shutil.move(str(tmp), str(path))
            return True
    tmp.unlink(missing_ok=True)
    return False


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        root = Path(args[0]).expanduser()
    else:
        from api.config import MUSIC_DIR
        root = MUSIC_DIR
    files = sorted(p for p in set(root.rglob("*"))
                   if p.is_file() and p.suffix.lower() in AUDIO_EXT
                   and not any(part.startswith(".") for part in p.relative_to(root).parts))
    print(f"{len(files)} songs in {root}")
    rows = []
    with ThreadPoolExecutor(max(2, (os.cpu_count() or 4) // 2)) as pool:
        for i, row in enumerate(pool.map(lambda p: check(p, root), files), 1):
            rows.append(row)
            if row["status"] != "ok":
                print(f"  {row['status']:7} {row['path']}  ({row['first_error'][:80]})", flush=True)
            if i % 100 == 0:
                print(f"  … {i}/{len(files)}", flush=True)

    order = {"broken": 0, "short": 1, "glitch": 2, "ok": 3}
    rows.sort(key=lambda r: (order[r["status"]], r["path"]))
    if "--fix" in sys.argv:
        for r in rows:
            if r["status"] == "glitch":
                r["fixed"] = fix_start(root / r["path"])
                print(f"  {'fixed ' if r['fixed'] else 'NOT fixed'} {r['path']}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["status", "path", "length", "decoded", "errors",
                                           "start_only", "fixed", "first_error"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in order}
    print(" ".join(f"{s}={n}" for s, n in counts.items()), f"\nreport: {REPORT}")


if __name__ == "__main__":
    main()
