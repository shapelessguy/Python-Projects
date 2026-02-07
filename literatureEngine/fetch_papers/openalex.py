import requests
import json
from gui.utils import matching_string, SEARCH_REQ_TIMEOUT


def from_openalex(work):
    biblio = work.get("biblio", {})
    venue = work.get("host_venue", {})
    doi = work["doi"] if work.get("doi", None) is not None else ""

    return {
        "doi": doi.replace("https://doi.org/", "").replace("http://doi.org/", ""),
        "type": work.get("type"),
        "title": work.get("title"),
        "authors": [
            a.get("author", {}).get("display_name")
            for a in work.get("authorships", [])
            if a.get("author")
        ],
        "year": work.get("publication_year"),
        "container_title": venue.get("display_name"),
        "venue_type": venue.get("type"),
        "publisher": venue.get("publisher"),
        "first_page": biblio.get("first_page"),
        "last_page": biblio.get("last_page"),
        "issn": venue.get("issn"),
        "isbn": biblio.get("isbn"),
        "pdf_url": work.get("primary_location", {}).get("pdf_url"),
    }


def fetch_from_openalex(value: str, obj: str):
    headers = {"User-Agent": "LiteratureEngine/1.0"}
    results = []
    if obj == "title":
        url = "https://api.openalex.org/works"
        params = {"search": value, "per_page": 5}
        response = requests.get(url, params=params, headers=headers, timeout=SEARCH_REQ_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        items = data.get("results", [])
        collection = [item.get("title") for item in items if item.get("title")]
        match = matching_string(value, collection)
        if match:
            work = next(item for item in items if item.get("title") == match)
            results.append(work)

    else:
        doi = value.lower()
        url = f"https://api.openalex.org/works/doi:{doi}"
        response = requests.get(url, headers=headers, timeout=SEARCH_REQ_TIMEOUT)
        response.raise_for_status()
        results = [response.json()]
    return results, from_openalex
