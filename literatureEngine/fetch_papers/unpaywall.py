import requests
import json
import os
import dotenv
from gui.utils import SEARCH_REQ_TIMEOUT
EMAIL = dotenv.get_key(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), "EMAIL")


def from_unpaywall(item):
    return {
        "pdf_url": item.get("pdf_url", ""),
    }


def fetch_from_unpaywall(value: str, obj: str):
    results = []
    if obj == "doi":
        doi = value.lower()
        url = f"https://api.unpaywall.org/v2/{doi}"
        response = requests.get(url, params={"email": EMAIL}, timeout=SEARCH_REQ_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if data.get("is_oa") and data.get("best_oa_location"):
            pdf_url = data["best_oa_location"].get("url_for_pdf")
            if pdf_url:
                results.append({"pdf_url": pdf_url})
    return results, from_unpaywall
