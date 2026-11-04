"""Does a recipe page work with the Food import? Runs the import's own
parsing on it -- no model called, nothing saved -- and grades it against the
page requirements of RECIPE_SITES.md (P1-P7).

    python3 scripts/check_recipe_site.py <recipe url> [<recipe url> ...]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.services import food, recipe_sites  # noqa: E402


def check(url: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        r = food._public_get(url, 15)
    except Exception as e:
        return {"P1 reachable": f"FAIL {e}"}
    challenge = r.headers.get("cf-mitigated")
    out["P1 reachable"] = ("ok" if r.status_code == 200 and not challenge
                           else f"FAIL {r.status_code}{' (bot challenge)' if challenge else ''}")
    if r.status_code != 200:
        return out
    blocks = []
    for raw in food._JSON_LD_RE.findall(r.text):
        try:
            blocks.append(json.loads(raw))
        except ValueError:
            pass
    try:
        recipe = food._recipe(blocks)
    except ValueError:
        out["P2 ingredients"] = "FAIL no schema.org Recipe in the HTML served"
        return out
    lines = recipe.get("recipeIngredient") or []
    out["P2 ingredients"] = f"ok {len(lines)} lines, e.g. {food._clean(str(lines[0]))!r}" if lines else "FAIL none"
    steps = food._preparation(url, r.text, recipe)
    out["P3 steps"] = f"ok {len(steps)}" if steps else "FAIL none"
    photos = sum(len(s["images"]) for s in steps)
    refs = sum(len(food.PHOTO_MARK_RE.findall(s["text"])) for s in steps)
    out["P4 step photos"] = str(photos) if photos else "none"
    out["P5 photo mentions"] = str(refs) if refs else "none"
    s = food._recipe_summary(url, recipe)
    times = (s["prep_time"], s["cook_time"], s["total_time"])
    iso = all(t.startswith("P") for t in times if t)
    out["P6 times"] = " / ".join(t or "-" for t in times) + ("" if iso else "  (not ISO 8601: lost)")
    site = recipe_sites.site_for(url)
    out["P7 difficulty"] = (food._site_difficulty(url, r.text) or "none") if site else "none (no site module)"
    out["site module"] = site.NAME if site else "none -- generic schema.org only"
    return out


if __name__ == "__main__":
    for u in sys.argv[1:]:
        print(f"\n## {u}")
        for k, v in check(u).items():
            print(f"  {k:20} {v}")
