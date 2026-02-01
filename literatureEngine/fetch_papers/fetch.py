import traceback
from bs4 import BeautifulSoup
from gui.utils import pprint, create_paper_id
from fetch_papers.crossref import fetch_from_crossref
from fetch_papers.openalex import fetch_from_openalex
from fetch_papers.datacite import fetch_from_datacite
from fetch_papers.semantic_scholar import fetch_from_semantic_scholar
from concurrent.futures import ThreadPoolExecutor, as_completed


source_map = {
    "crossref": fetch_from_crossref,
    "openalex": fetch_from_openalex,
    "datacite": fetch_from_datacite,
    "semantic_scholar": fetch_from_semantic_scholar
}


def process_title(k, v, title):
    """Wrapper function to process a single title."""
    return k, fetch_from_source(v, title, "title")


def process_doi(k, v, doi):
    """Wrapper function to process a single DOI."""
    return k, fetch_from_source(v, doi, "doi")


def fetch_from_title(title):
    sources = {k: [] for k in source_map}
    tasks = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        for k, v in source_map.items():
            tasks.append(executor.submit(process_title, k, v, title))
        
        for future in as_completed(tasks):
            k, result = future.result()
            sources[k] += result
    return sources


def fetch_from_dois(dois, prev_sources=None):
    if prev_sources:
        sources = {k: prev_sources[k] for k in source_map}
    else:
        sources = {k: [] for k in source_map}
    tasks = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        for k, v in source_map.items():
            for doi in dois:
                if doi not in [x.get("doi", None) for x in sources[k]]:
                    tasks.append(executor.submit(process_doi, k, v, doi))
        
        for future in as_completed(tasks):
            k, result = future.result()
            sources[k] += result
    return sources


def get_dois(sources):
    dois = []
    for v in sources.values():
        for r in v:
            if "doi" in r and r["doi"] is not None:
                dois.append(r["doi"])
    return dois


def fetch_metadata(value: str, obj: str):
    result = None
    main_doi = value if obj == "doi" else None
    try:
        if obj == "title":
            sources = fetch_from_title(value)
            dois = get_dois(sources)
            main_doi = main_doi if (main_doi in dois) else (dois[0] if len(dois) else None)
            sources = fetch_from_dois(dois, sources)
            result = merge_sources(sources, main_doi)
        elif obj == "doi":
            sources = fetch_from_dois([value])
            result = merge_sources(sources, value)
    except Exception as e:
        pprint("Exception while fetching metadata:")
        pprint(traceback.format_exc())
    return result




def fetch_from_source(fetch_funct, value: str, obj: str):
    repeat = True
    results = []
    while repeat:
        repeat = False
        try:
            results, extract_func = fetch_funct(value, obj)
            results = [extract_func(result) for result in results]
        except Exception as e:
            if "Too Many Requests" in str(e):
                repeat = True
            print(f"{fetch_funct.__name__} fetch failed: {e}")
    
    # import json
    # for r in results:
    #     print(json.dumps(r, indent=2))

    return results


def merge_sources(sources, main_doi=None):
    final = {"doi": main_doi} if main_doi else {}
    for l in sources.values():
        for result in l:
            final = {**{k: v for k, v in result.items() if v is not None}, **final}

    if final.get("abstract", "") != "":
        try:
            soup = BeautifulSoup(final.get("abstract", ""), "html.parser")
            final["abstract"] = soup.get_text(separator=" ", strip=True)
        except:
            pass

    final["notes"] = ""
    final["paperId"] = create_paper_id(final.get("title", ""), final.get("doi", ""), final.get("year", 2025))
    return final
