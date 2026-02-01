import requests
import json
import dotenv
from gui.utils import matching_string
SEMANTIC_SCHOLAR_KEY = dotenv.get_key(".env", "GOOGLE_SEMANTIC_SCHOLAR")


FIELDS = ",".join([
    "title",
    "abstract",
    "year",
    "authors",
    "venue",
    "citationCount",
    "referenceCount",
    "influentialCitationCount",
    "url",
    "externalIds",
    "openAccessPdf",
    "publicationTypes"
])


def from_semantic_scholar(data):
    return {
        "doi": data.get("doi") or data.get("externalIds", {}).get("DOI"),
        "title": data.get("title"),
        "authors": [a.get("name") for a in data.get("authors", [])],
        "year": data.get("year"),
        "venue": data.get("venue"),
        "venue_url": data.get("venueUrl"),
        "publisher": data.get("publisher"),
        "volume": data.get("volume"),
        "issue": data.get("issue"),
        "first_page": None,
        "last_page": None,
        "abstract": data.get("abstract"),
        "citation_count": data.get("citationCount"),
        "reference_count": data.get("referenceCount"),
        "influential_citation_count": data.get("influentialCitationCount"),
        "url": data.get("url"),
    }


def fetch_from_semantic_scholar(value: str, obj: str):
    headers={"x-api-key": SEMANTIC_SCHOLAR_KEY}
    results = []
    if obj == "title":
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": value,
            "limit": 5,
            "fields": FIELDS
        }
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        items = data.get("data", [])
        collection = [item.get("title") for item in items if item.get("title")]
        match = matching_string(value, collection)
        if match:
            paper = next(item for item in items if item.get("title") == match)
            results.append(paper)
    else:
        # Fetch by DOI
        doi = value.lower()
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
        params = {
            "fields": "title,authors,year,venue,abstract,url,externalIds"
        }
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        results = [response.json()]
    return results, from_semantic_scholar
