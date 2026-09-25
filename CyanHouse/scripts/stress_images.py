"""Fill a folder of the Images library with thousands of photos, to see how
the Images tab copes — the gallery's batches, the thumbnails, the listing —
and take them away again.

    cd CyanHouse && ../.venv/bin/python scripts/stress_images.py            # 10000 photos
    cd CyanHouse && ../.venv/bin/python scripts/stress_images.py --count 2000 --from random
    cd CyanHouse && ../.venv/bin/python scripts/stress_images.py --remove

The photos are the ones in --from (a folder of IMAGE_DIR, "random" by
default) over and over, as `stress test/stress_00001.jpg` and on. They are
hard links by default: each is its own file to the page and the server (its
own thumbnail, its own row), but they share the bytes on the drive, so ten
thousand of them take no space and are made in seconds. --copy makes real
copies instead (about the size of the source folder times count / its
number of photos).

--remove deletes the folder — only one this script made (it leaves a marker
in it) — and the thumbnails the server made of its photos.
"""
import argparse
import hashlib
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import IMAGE_DIR  # noqa: E402
from api.services.movie_prep import IMAGE_EXT  # noqa: E402

MARKER = ".stress-test"


def fill(target: Path, source: Path, count: int, copy: bool) -> None:
    photos = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT)
    if not photos:
        sys.exit(f"no photos directly in {source}")
    target.mkdir(parents=True, exist_ok=True)
    (target / MARKER).write_text("made by scripts/stress_images.py; --remove deletes this folder\n")
    width = len(str(count))
    started, linked, copied = time.time(), 0, 0
    for i in range(count):
        src = photos[i % len(photos)]
        dest = target / f"stress_{i + 1:0{width}d}{src.suffix.lower()}"
        if dest.exists():
            continue
        if not copy:
            try:
                os.link(src, dest)
                linked += 1
                continue
            except OSError:
                copy = True  # this drive cannot link: copy from here on
                print("  hard links not possible here — copying instead")
        shutil.copy2(src, dest)
        copied += 1
        if (i + 1) % 1000 == 0:
            print(f"  {i + 1}/{count}", flush=True)
    print(f"{count} photos in {target} ({linked} linked, {copied} copied) "
          f"in {time.time() - started:.1f}s, from {len(photos)} in {source}")


def remove(target: Path) -> None:
    if not target.is_dir():
        sys.exit(f"nothing to remove: {target} does not exist")
    if not (target / MARKER).exists():
        sys.exit(f"{target} was not made by this script (no {MARKER} in it) — not touching it")
    # The server's thumbnails of these photos: keyed by path, size, time and
    # width (api/services/thumbs.py), so they can be found before the photos go.
    from api.services import thumbs
    gone = 0
    for p in target.iterdir():
        if p.suffix.lower() not in IMAGE_EXT:
            continue
        st = p.stat()
        for w in thumbs.WIDTHS:
            key = hashlib.sha1(f"{p}|{st.st_size}|{int(st.st_mtime)}|{w}".encode()).hexdigest()
            t = thumbs.THUMB_DIR / key[:2] / f"{key}.jpg"
            if t.exists():
                t.unlink()
                gone += 1
    shutil.rmtree(target)
    print(f"removed {target} and {gone} thumbnails")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=10000)
    ap.add_argument("--from", dest="source", default="random", help="folder of IMAGE_DIR to take photos from")
    ap.add_argument("--to", dest="target", default="stress test", help="folder of IMAGE_DIR to fill")
    ap.add_argument("--copy", action="store_true", help="real copies instead of hard links")
    ap.add_argument("--remove", action="store_true", help="delete the folder this script made")
    args = ap.parse_args()
    if IMAGE_DIR is None:
        sys.exit("IMAGE_DIR is not configured in secrets.json")
    target = IMAGE_DIR / args.target
    if args.remove:
        remove(target)
    else:
        fill(target, IMAGE_DIR / args.source, args.count, args.copy)


if __name__ == "__main__":
    main()
