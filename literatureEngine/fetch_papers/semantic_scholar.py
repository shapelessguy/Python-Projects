import requests
import os
import json
import dotenv
from gui.utils import matching_string, SEARCH_REQ_TIMEOUT
SEMANTIC_SCHOLAR_KEY = dotenv.get_key(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), "GOOGLE_SEMANTIC_SCHOLAR")


FIELDS = [
    "title",
    "abstract",
    "year",
    "authors",
    "venue",
    "citationCount",
    "references",
    "referenceCount",
    "influentialCitationCount",
    "url",
    "externalIds",
    "openAccessPdf",
    "publicationTypes"
]


def from_semantic_scholar(data):
    references = []
    if data.get("references", None):
        references = [x["paperId"] for x in data["references"] if "paperId" in x]
    publTypes = "other" if data.get("publicationTypes", None) is None else data["publicationTypes"][0]
    return {
        "doi": data.get("doi") or data.get("externalIds", {}).get("DOI"),
        "title": data.get("title"),
        "authors": [a.get("name") for a in data.get("authors", [])],
        "year": data.get("year"),
        "venue": data.get("venue"),
        "venue_type": publTypes,
        "venue_url": data.get("venueUrl"),
        "publisher": data.get("publisher"),
        "volume": data.get("volume"),
        "issue": data.get("issue"),
        "first_page": None,
        "last_page": None,
        "abstract": data.get("abstract"),
        "citation_count": data.get("citationCount"),
        "reference_count": data.get("referenceCount"),
        "references": references,
        "influential_citation_count": data.get("influentialCitationCount"),
        "url": data.get("url"),
        "pdf_url": data.get("openAccessPdf", {"url": ""})["url"],
    }


def fetch_from_semantic_scholar(value: str, obj: str):
    headers={"x-api-key": SEMANTIC_SCHOLAR_KEY}
    results = []
    if obj == "title":
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": value,
            "limit": 5,
            "fields": ",".join(FIELDS)
        }
        response = requests.get(url, params=params, headers=headers, timeout=SEARCH_REQ_TIMEOUT)
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
            "fields": ",".join(FIELDS)
        }
        response = requests.get(url, params=params, headers=headers, timeout=SEARCH_REQ_TIMEOUT)
        response.raise_for_status()
        results = [response.json()]
    return results, from_semantic_scholar


def search_bulk_from_semantic_scholar(query: str):
    url = "http://api.semanticscholar.org/graph/v1/paper/search/bulk"
    headers = {"x-api-key": SEMANTIC_SCHOLAR_KEY}

    response = requests.get(url, params={"fields": ",".join([x for x in FIELDS if x not in ["references"]]), "query": query}, headers=headers)
    response.raise_for_status()
    results = response.json()['data']
    results = [x for x in results if x.get("abstract", None) is not None]
    for r in results:
        print(r.get("openAccessPdf", None))
    return results, from_semantic_scholar


def fetch_from_semantic_scholar_ids(doi_list: list[str]):
    url = "https://api.semanticscholar.org/graph/v1/paper/batch"
    headers = {
        "x-api-key": SEMANTIC_SCHOLAR_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(url, params={'fields': ",".join(FIELDS)}, headers=headers, json={"ids": [f"{doi}" for doi in doi_list]})
    response.raise_for_status()
    data = response.json()
    return data, from_semantic_scholar
