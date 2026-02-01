import requests
import json
from gui.utils import matching_string


def from_datacite(item):
    attrs = item.get("attributes", {})
    first_page, last_page = None, None
    pages = attrs.get("pages")
    if pages and "-" in pages:
        first_page, last_page = pages.split("-", 1)
    container_title = None
    venue_type = None
    publisher = attrs.get("publisher")
    issn = None
    isbn = attrs.get("isbn")
    
    container_title_list = attrs.get("container-title") or []
    if isinstance(container_title_list, list) and container_title_list:
        container_title = container_title_list[0]
    
    return {
        "doi": attrs.get("doi"),
        "type": attrs.get("types", {}).get("resourceTypeGeneral"),
        "title": attrs.get("titles", [{}])[0].get("title"),
        "authors": [
            f"{c.get('givenName')} {c.get('familyName')}"
            for c in attrs.get("creators", [])
            if c.get("familyName")
        ],
        "year": attrs.get("publicationYear"),
        "container_title": container_title,
        "venue_type": venue_type,
        "publisher": publisher,
        "first_page": first_page,
        "last_page": last_page,
        "issn": issn,
        "isbn": isbn,
        "url": attrs.get("url")
    }


def fetch_from_datacite(value: str, obj: str):
    headers = {"User-Agent": "LiteratureEngine/1.0"}
    results = []
    if obj == "title":
        url = "https://api.datacite.org/dois"
        params = {"query": value, "page[size]": 5}
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("data", [])
        collection = [item.get("attributes", {}).get("titles", [{}])[0].get("title") for item in items if item.get("attributes")]
        match = matching_string(value, collection)
        if match:
            work = next(item for item in items if item.get("attributes", {}).get("titles", [{}])[0].get("title") == match)
            results.append(work)

    else:
        # fetch by DOI
        doi = value.lower()
        url = f"https://api.datacite.org/dois/{doi}"
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        results = [response.json().get("data", {})]
    return results, from_datacite
