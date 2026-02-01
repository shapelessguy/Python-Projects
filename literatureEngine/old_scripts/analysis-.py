import os
import re
import sys
import json
import requests
from extract_ref import extract_reference, extract_reference_latex


COMPLETE_JSON_NAME = "complete.json"
DOI_NOT_FOUND_FILE = "doi_not_found.txt"


def print_json(dict_: dict):
    print(json.dumps(dict_, ensure_ascii=False, indent=2))


def get_keywords(json_name):
    return [x.replace(".json", "") for x in json_name.split("_") if not x.startswith("202")]


def chunk_list(items, chunk_size=10):
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def add_md():
    papers = {}
    for json_name in [x for x in os.listdir(os.path.join(os.path.dirname(__file__), "indexes")) if '.json' in x]:
        json_path = os.path.join(os.path.dirname(__file__), "indexes", json_name)
        with open(json_path, "r", encoding='utf8') as file:
            pps = json.load(file)
            for p in pps:
                if p["paperId"] not in papers:
                    p["kws"] = get_keywords(json_name)
                    papers[p["paperId"]] = p
                else:
                    papers[p["paperId"]]["kws"] = list(set(papers[p["paperId"]]["kws"] + get_keywords(json_name)))
    # paper without DOI divided by year: {2022: 178, 2023: 160, 2024: 107, 2025: 234, 2026: 39}
    papers = [p for p in papers.values() if "DOI" in p["externalIds"]]

    if os.path.exists(os.path.join(os.path.dirname(__file__), COMPLETE_JSON_NAME)):
        with open(COMPLETE_JSON_NAME, "r") as file:
            paper_list = [x for x in json.load(file) if "doi_metadata" in x]
    else:
        paper_list = []

    if os.path.exists(os.path.join(os.path.dirname(__file__), DOI_NOT_FOUND_FILE)):
        with open(DOI_NOT_FOUND_FILE, "r") as file:
            doi_not_found = file.read().split("\n")
    else:
        doi_not_found = []

    papers = [p for p in papers if p["externalIds"]["DOI"] not in doi_not_found]
    saved_papers = {x['paperId']: x for x in paper_list}
    
    done, total = 0, len(papers)
    papers = chunk_list(papers, 200)
    for chunk in papers:
        new_papers = 0
        doi_nf = 0
        for p in chunk:
            done += 1
            if p["paperId"] in saved_papers:
                saved_papers[p["paperId"]]["kws"] = p["kws"]
            else:
                doi = p["externalIds"].get("DOI")
                url = f"https://api.crossref.org/works/{doi}"
                response = requests.get(url)
                try:
                    response.raise_for_status()
                    metadata = response.json()["message"]
                    p["doi_metadata"] = metadata
                    new_papers += 1
                    paper_list.append(p)
                except Exception as e:
                    if "Client Error: Not Found" in str(e):
                        doi_nf += 1
                        doi_not_found.append(p["externalIds"]["DOI"])

            percent = (done / total) * 100
            bar_len = 30
            filled = int(bar_len * done // total)
            bar = "█" * filled + "-" * (bar_len - filled)
            sys.stdout.write(f"\r[{bar}] {done}/{total} ({percent:.1f}%)")
            sys.stdout.flush()

        if doi_nf > 0 or new_papers > 0:
            print("   Saving checkpoint...")
        if doi_nf > 0:
            with open(DOI_NOT_FOUND_FILE, "w") as file:
                file.write("\n".join(doi_not_found))
        if new_papers > 0:
            with open("complete.json", "w") as file:
                json.dump(paper_list, file, indent=2)


def has_word(sentence, word):
    pattern = rf'\b{re.escape(word.lower())}\b'
    return bool(re.search(pattern, sentence.lower()))


def get_statistics():
    with open(COMPLETE_JSON_NAME, "r") as file:
        papers_source = json.load(file)
    papers = []
    for p in papers_source:
        ref = extract_reference(p["doi_metadata"])
        info = {
            **ref,
            "abstract": p["abstract"],
            "citationCount": p["citationCount"],
            "referenceCount": p["referenceCount"],
            "url": p["url"],
            "kws": p["kws"]
        }
        # if info["abstract"] and info["citationCount"] and info["referenceCount"]:
        #     papers.append(SimplePaper(**info))
    
    # relevant = []
    # for p in papers:
    #     contained_kw = [
    #         ["requirements", "re"],
    #         ["ai", "llm", "chatgpt", "gpt", "llama", "gemini", "generative", "artificial intelligence"]
    #     ]

    #     not_met = False
    #     for and_cond in contained_kw:
    #         if not any([has_word(p.abstract, or_cond) for or_cond in and_cond]):
    #             not_met = True
    #             break
    #     if not not_met:
    #         # REMOVE SURVEYS
    #         contained_kw_ = ["literature review", "survey", "comprehensive review"]
    #         if not any([c.lower() in p.title.lower() for c in contained_kw_]):
    #             relevant.append(p)
    
    # for i, p in enumerate(sorted(relevant, key=lambda x: x.citationCount)):
    #     print(i, p.title, p.citationCount)


if __name__ == "__main__":
    # add_md()
    get_statistics()
