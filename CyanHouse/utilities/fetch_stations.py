"""
Fetches Beschreibung_Stationen.txt for each DWD hourly variable
and merges them into a single file: all_stations.txt
Run this from the project root: python -m utilities.fetch_stations
"""

import re
import requests

BASE_URL = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly"

VARIABLES = [
    "air_temperature",
    "pressure",
    "precipitation",
    "moisture",
    "wind",
    "cloudiness",
    "sun",
    "solar",
    "soil_temperature",
]

OUTPUT_FILE = "all_stations.txt"


def get_beschreibung_url(variable: str) -> str:
    """Find the Beschreibung_Stationen.txt URL inside the recent/ folder."""
    index_url = f"{BASE_URL}/{variable}/recent/"
    resp = requests.get(index_url, timeout=30)
    resp.raise_for_status()
    matches = re.findall(r'href="([^"]*Beschreibung_Stationen\.txt)"', resp.text)
    if not matches:
        raise FileNotFoundError(f"No Beschreibung_Stationen.txt found for {variable}")
    href = matches[0]
    if href.startswith("http"):
        return href
    return index_url + href


def main():
    lines = []
    for variable in VARIABLES:
        print(f"Fetching {variable}...")
        try:
            url = get_beschreibung_url(variable)
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            content = resp.content.decode("latin-1")
            lines.append(f"{'=' * 60}")
            lines.append(f"VARIABLE: {variable}")
            lines.append(f"{'=' * 60}")
            lines.append(content.strip())
            lines.append("")  # blank line between sections
        except Exception as e:
            lines.append(f"ERROR for {variable}: {e}")
            lines.append("")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nDone! Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
