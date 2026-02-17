import traceback
import time
from bs4 import BeautifulSoup
from gui.utils import pprint, wait
from fetch_papers.crossref import fetch_from_crossref
from fetch_papers.openalex import fetch_from_openalex
from fetch_papers.datacite import fetch_from_datacite
from fetch_papers.unpaywall import fetch_from_unpaywall
from fetch_papers.semantic_scholar import fetch_from_semantic_scholar, search_dois_from_semantic_scholar
from concurrent.futures import ThreadPoolExecutor, as_completed


source_map = {
    "semantic_scholar": fetch_from_semantic_scholar,
    "crossref": fetch_from_crossref,
    "openalex": fetch_from_openalex,
    "datacite": fetch_from_datacite,
    "unpaywall": fetch_from_unpaywall
}


def process_title(signal, k, v, title):
    """Wrapper function to process a single title."""
    return k, fetch_from_source(v, signal, title, "title")


def process_doi(signal, k, v, doi):
    """Wrapper function to process a single DOI."""
    return k, fetch_from_source(v, signal, doi, "doi")


def fetch_from_title(signal, title):
    sources = {k: [] for k in source_map}
    tasks = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        for k, v in source_map.items():
            tasks.append(executor.submit(process_title, signal, k, v, title))
        
        for future in as_completed(tasks):
            k, result = future.result()
            sources[k] += result
    return sources


def fetch_from_dois(signal, dois, prev_sources=None):
    if prev_sources:
        sources = {k: prev_sources[k] for k in source_map}
    else:
        sources = {k: [] for k in source_map}
    tasks = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        for k, v in source_map.items():
            for doi in dois:
                if doi not in [x.get("doi", None) for x in sources[k]]:
                    tasks.append(executor.submit(process_doi, signal, k, v, doi))
        
        for future in as_completed(tasks):
            k, result = future.result()
            sources[k] += result
    return sources


def get_dois(sources):
    dois = set()
    for v in sources.values():
        for r in v:
            if "doi" in r and r["doi"] is not None:
                dois.add(r["doi"].lower())
    return list(dois)


def fetch_metadata(signal, value: str, obj: str):
    result = None
    try:
        if obj == "title":
            main_doi = value.lower() if obj == "doi" else None
            sources = fetch_from_title(signal, value)
            if not signal.is_alive():
                return
            dois = get_dois(sources)
            main_doi = main_doi if (main_doi in dois) else (dois[0] if len(dois) else None)
            sources = fetch_from_dois(signal, dois, sources)
            result = merge_sources(sources, main_doi)
        elif obj == "doi":
            sources = fetch_from_dois(signal, [value])
            result = merge_sources(sources, value)
        elif obj == "paper_ids":
            result = []
            for paper_id in value:
                formated = merge_sources(fetch_from_dois(signal, [paper_id]), paper_id)
                if "title" in formated:
                    result.append(formated)
    except Exception as e:
        pprint("Exception while fetching metadata:")
        pprint(traceback.format_exc())
    return result


def expand_dois(signal, query: str):
    final = []
    repeat = True
    try:
        while signal.is_alive() and repeat:
            try:
                results, _ = search_dois_from_semantic_scholar(query)
                final = results
                repeat = False
            except:
                repeat = True
    except Exception as e:
        pprint("Exception while fetching Semantic Scholar ids:")
        pprint(traceback.format_exc())
    return final


def fetch_from_source(fetch_funct, signal, value: str, obj: str):
    repeat = True
    repeat_idx = 0
    results = []
    if not hasattr(signal, "missing_fetches"):
        signal.missing_fetches = {obj: set()}
    elif obj not in signal.missing_fetches:
        signal.missing_fetches[obj] = set()

    while repeat and repeat_idx < 5:
        if value in signal.missing_fetches[obj]:
            break
        repeat_idx += 1
        repeat = False
        try:
            results, extract_func = fetch_funct(value, obj)
            results = [extract_func(result) for result in results]
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                print(traceback.format_exc())
                repeat = True
                wait(signal, 1000 * repeat_idx)
            elif "404" in str(e):
                signal.missing_fetches[obj].add(value)
            else:
                print(f"{fetch_funct.__name__} fetch failed: {e}")
                print(traceback.format_exc())
    return results


# Standard: CrossRef
type_to_crossref = {

    # OpenAlex
    "article": "journal-article",
    "review": "journal-article",
    "preprint": "posted-content",
    "letter": "journal-article",
    "editorial": "journal-article",
    "erratum": "journal-article",
    "supplementary-materials": "other",
    "libguides": "other",
    "paratext": "other",
    "proceedings-article": "proceedings-article",
    "dataset": "dataset",
    "book": "book",
    "book-chapter": "book-chapter",
    "patent": "other",
    "thesis": "dissertation",
    "report": "report",
    "news-article": "other",

    # Semantic Scholar
    "journalarticle": "journal-article",
    "conference": "proceedings-article",
    "review": "journal-article",
    "dataset": "dataset",
    "casereport": "journal-article",
    "editorial": "journal-article",
    "clinicaltrial": "journal-article",
    "preprint": "posted-content",
    "book": "book",
    "bookchapter": "book-chapter",
    "thesis": "dissertation",
    "report": "report",
    "other": "other",

    # DataCite
    "text": "journal-article",
    "book": "book",
    "bookchapter": "book-chapter",
    "conferencepaper": "proceedings-article",
    "dataset": "dataset",
    "dissertation": "dissertation",
    "report": "report",
    "preprint": "posted-content",
    "other": "other",
    "patent": "other",
    "thesis": "dissertation",
    "journal": "journal-article"
}


def merge_sources(sources, main_doi=None):
    final = {"doi": main_doi} if main_doi else {}
    pdf_urls = set()
    for l in sources.values():
        for result in l:
            if "pdf_url" in result and result["pdf_url"]:
                pdf_urls.add(result["pdf_url"])
            final = {**{k: v for k, v in result.items() if v not in [None, '', []]}, **final}
    final["pdf_url"] = list(pdf_urls)

    if final.get("abstract", "") != "":
        try:
            soup = BeautifulSoup(final.get("abstract", ""), "html.parser")

            final["abstract"] = soup.get_text(separator=" ", strip=True)
        except:
            pass

    if final.get("venue_type", "").lower() in type_to_crossref:
        final["venue_type"] = type_to_crossref[final["venue_type"].lower()]
    
    final["notes"] = ""
    return final
