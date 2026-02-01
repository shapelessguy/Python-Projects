import requests
import dotenv
import json
import time
import os
from pybliometrics.scopus import ScopusSearch, init
from requests.exceptions import HTTPError
from utils import get_raw_paper_headers, encode_name


init()
SEMANTIC_SCHOLAR_KEY = dotenv.get_key(".env", "GOOGLE_SEMANTIC_SCHOLAR")
url_semantic_scholar = "http://api.semanticscholar.org/graph/v1/paper/search/bulk"


PARAMS = {
    "fields": ",".join([
        "title",
        "abstract",
        "year",
        "authors",
        "venue",
        "citationCount",
        "referenceCount",
        "influentialCitationCount",
        "url",
        "externalIds"
    ])
}


def scrape_on_semantic_scholar(params, results):
    print("Scraping with Semantic Scholar...")
    try:
        response = requests.get(url_semantic_scholar, headers={"x-api-key": SEMANTIC_SCHOLAR_KEY}, params=params)
        data = response.json()
        for paper in data['data']:
            if paper["abstract"]:
                results.append(paper)
    except:
        if 'message' in data and 'Too Many Requests'.lower() in data['message'].lower():
            pass
        else:
            print("Issue found while scraping on Semantic Scholar...")
        time.sleep(2)
        return False
    return True


# def scrape_on_scopus(query, results, retries=5):
#     for attempt in range(retries):
#         try:
#             print(1)
#             print(query)
#             query = "test"
#             search = ScopusSearch(query, view="STANDARD", refresh=False)
#             print(search)
#             raise
#             print(2)
#             time.sleep(0.25)
#             return search
#         except HTTPError as e:
#             if "429" in str(e):
#                 wait = 2 ** attempt
#                 print(f"429 received. Sleeping {wait}s")
#                 time.sleep(wait)
#             else:
#                 raise
#     raise RuntimeError("Scopus quota exhausted or unstable connection")


def scrape(queries: list[str], workspace: str):
    processed_jsons = [x for x in os.listdir(get_raw_paper_headers(workspace)) if ".json" in x]
    for query in queries:
        json_name = encode_name(query, workspace)
        if json_name in processed_jsons:
            continue
        results = []
        params = {k: v for k, v in PARAMS.items()}
        params["query"] = query
        
        # while True:
        #     success = scrape_on_scopus(query, results)
        #     if not success:
        #         continue
        #     break
        
        while True:
            success = scrape_on_semantic_scholar(params, results)
            if not success:
                continue
            break

        print(f"Fetched {len(results)} papers...")
        with open(os.path.join(get_raw_paper_headers(workspace), json_name), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    print("Papers scraped.")



def simple_scrape(query: str):
    results = []
    params = {k: v for k, v in PARAMS.items()}
    params["query"] = query
        
    # while True:
    #     success = scrape_on_scopus(query, results)
    #     if not success:
    #         continue
    #     break

    while True:
        success = scrape_on_semantic_scholar(params, results)
        if not success:
            continue
        break

    print(f"Fetched {len(results)} papers...")
    return results



if __name__ == "__main__":
    # scrape(["(LLM + requirement engineering) -exploration"], "scraping_bulk")
    paper_name = "Challenges in applying large language models to requirements engineering tasks"
    results = simple_scrape(paper_name)
    print(json.dumps(results, indent=2))