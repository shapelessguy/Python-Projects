import requests
import json
from gui.utils import matching_string, SEARCH_REQ_TIMEOUT


def from_crossref(message):
    issued = (
        message.get("published-print")
        or message.get("published-online")
        or message.get("issued", {})
    )

    year = issued.get("date-parts", [[None]])[0][0]
    pages = message.get("page")
    references = [x["DOI"] for x in message.get("reference", []) if "DOI" in x]

    first_page, last_page = (None, None)
    if pages and "-" in pages:
        first_page, last_page = pages.split("-", 1)

    return {
        "doi": message.get("DOI"),
        "venue_type": message.get("type"),
        "title": message.get("title", [None])[0],
        "authors": [
            f"{a.get('given')} {a.get('family')}"
            for a in message.get("author", [])
            if a.get("family")
        ],
        "year": year,
        "container_title": message.get("container-title", [None])[0],
        "publisher": message.get("publisher"),
        "publisher_location": message.get("publisher-location"),
        "references": references,
        "volume": message.get("volume"),
        "issue": message.get("issue"),
        "first_page": first_page,
        "last_page": last_page,
        "isbn": message.get("ISBN"),
        "issn": message.get("ISSN"),
        "abstract": message.get("abstract"),
        "url": message.get("URL"),
    }


def fetch_from_crossref(value: str, obj: str):
    headers = {"User-Agent": "LiteratureEngine/1.0"}
    results = []
    if obj == "title":
        url = "https://api.crossref.org/works"
        params = {
            "query.title": value,
            "rows": 5
        }
    else:
        url = f"https://api.crossref.org/works/{value}"
        params = {}
    
    response = requests.get(url, params=params, headers=headers, timeout=SEARCH_REQ_TIMEOUT)
    response.raise_for_status()

    data = response.json()
    message = data.get("message", {})
    items = message.get("items", [])
    if obj == "title":
        collection = [item.get(obj, [""])[0] for item in items if "DOI" in item]
        match = matching_string(value, collection)
        if match:
            work = next(item for item in items if item.get("title", [""])[0] == match)
            results.append(work)
    else:
        results = [response.json().get("message", {})]
    return results, from_crossref
