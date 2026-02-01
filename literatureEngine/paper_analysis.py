
import os
import sys
import json
import importlib
import textwrap
import difflib
import requests
import shutil
import re
import inspect
from ai_queries import CONTENT_TAG, SCOPE_QUERY_GENERATOR_TITLES, execute_simple_request
from utils import PAPER_LOCATION_MAP_PATH, FAILED_PDF_RETRIEVAL_PATH, SAVED_RESPONSES_PATH
from utils import CUSTOM_TEXT_PATH_TEMPLATE, AI_TASKS, query_to_hash, clean_pdf_name
from utils import get_pdfs_path, get_extracted_path, get_user_pdfs_path, decode_name
from utils import get_saved_pdfs_path, get_raw_paper_headers, get_responses_path, get_user_pdf_map
from scraping_bulk import scrape, simple_scrape
from ai_queries import execute_ai
from pdfminer.high_level import extract_text


class SimplePaper:
    def __init__(self, p_id, **paper_stats):
        self.id = p_id
        self.authors = paper_stats.get("authors", None)
        self.title = paper_stats.get("title", "unknown")
        self.year = paper_stats.get("year", None)
        self.venue = paper_stats.get("venue", None)
        self.publisher = paper_stats.get("publisher", None)
        self.volume = paper_stats.get("volume", None)
        self.issue = paper_stats.get("issue", None)
        self.pages = paper_stats.get("pages", None)
        self.external_ids = paper_stats.get("externalIds", {})
        self.doi = self.external_ids.get("DOI", None)
        self.url = paper_stats.get("url", None)
        self.type = paper_stats.get("type", None)
        self.abstract = paper_stats.get("abstract", "unknown")
        self.citationCount = paper_stats.get("citationCount", 9999)
        self.referenceCount = paper_stats.get("referenceCount", 9999)
        self.kws = paper_stats.get("kws", None)

        self.ai_info = {}
        self.text = None
        self.paper_location = None
        self.info = {}
    
    def get_paper_location(self):
        self.paper_location = get_oa_pdf_url(self.doi, "claudio.ciano@dlr.de")
        return self.paper_location
    
    def get_paper_path(self, workspace: str):
        pdf_path = None
        if not self.paper_location:
            return pdf_path
        if self.abstract == "unknown":
            pdf_path = os.path.join(get_user_pdfs_path(workspace), f"{self.title}.pdf")
        else:
            pdf_path = os.path.join(get_pdfs_path(workspace), f"{self.id}.pdf")
        return pdf_path
    
    def has_paper(self):
        return self.paper_location is not None
    
    def has_text(self):
        return self.text is not None

    def set_ai_info(self, ai_info):
        self.ai_info = ai_info
    
    def is_overview(self):
        overview_kws = [
            "survey",
            "review",
            "overview",
            "state of the art",
            "systematic literature review",
            "systematic review",
            "mapping study",
            "systematic mapping",
            "tertiary study",
            "meta-analysis",
            "meta analysis",
        ]
        for kw in overview_kws:
            if kw in self.title or kw in self.abstract:
                return True
        return False
    
    def __str__(self):
        wrapped_abstract = textwrap.fill(self.abstract, width=140, initial_indent='\t', subsequent_indent='\t')
        return f"Title: {self.title}\n{wrapped_abstract}"


class Papers(list[SimplePaper]):
    paper_loc_map: dict = {}
    failed_pdf_retrieval: dict = {}
    saved_responses: dict = {}
    user_pdf_map: dict = {}
    simple_scrape_results: list = []
    workspace = "none"

    def __init__(self, workspace: str, papers=None, queries=None):
        self.workspace = workspace
        
        simple_scrape_results_path = os.path.join(get_raw_paper_headers(workspace), "userPapers.json")
        if not os.path.exists(simple_scrape_results_path):
            with open(simple_scrape_results_path, "w", encoding='utf8') as file:
                json.dump([], file)
        with open(simple_scrape_results_path, "r", encoding='utf8') as file:
            self.simple_scrape_results = json.load(file)
        with open(get_user_pdf_map(self.workspace), "r", encoding='utf8') as file:
            self.user_pdf_map = json.load(file) 
        for document, doc_name in {
                PAPER_LOCATION_MAP_PATH: "paper_loc_map",
                FAILED_PDF_RETRIEVAL_PATH: "failed_pdf_retrieval",
                SAVED_RESPONSES_PATH: "saved_responses"
                }.items():
            if not os.path.exists(document):
                with open(document, "w", encoding='utf8') as file:
                    json.dump({}, file, indent=2)
            with open(document, "r", encoding='utf8') as file:
                setattr(self, doc_name, json.load(file))
        if queries:
            scrape(queries, self.workspace)
        if papers is None:
            papers = self.load_papers()
            self.save_user_pdf_map()
            self.save_paper_location_map()
        self.extend(papers)
   
    def filter_by_doi(self):
        new_papers = Papers(self.workspace, papers=[p for p in self if p.doi])
        print(f"{len(self)} papers filtered by DOI -> new count: {len(new_papers)}")
        return new_papers
   
    def filter_by_pdf(self):
        new_papers = Papers(self.workspace, papers=[p for p in self if p.has_paper()])
        print(f"{len(self)} papers filtered by PDF -> new count: {len(new_papers)}")
        return new_papers
   
    def save_paper_location_map(self):
        with open(PAPER_LOCATION_MAP_PATH, "w", encoding='utf8') as file:
            json.dump(self.paper_loc_map, file, indent=2)
   
    def save_failed_pdf_retrieval(self):
        with open(FAILED_PDF_RETRIEVAL_PATH, "w", encoding='utf8') as file:
            json.dump(self.failed_pdf_retrieval, file, indent=2)
   
    def save_responses(self):
        with open(SAVED_RESPONSES_PATH, "w", encoding='utf8') as file:
            json.dump(self.saved_responses, file, indent=2)
   
    def save_user_pdf_map(self):
        with open(os.path.join(get_raw_paper_headers(self.workspace), "userPapers.json"), "w", encoding='utf8') as file:
            json.dump(self.simple_scrape_results, file, indent=2)
        with open(get_user_pdf_map(self.workspace), "w", encoding='utf8') as file:
            json.dump(self.user_pdf_map, file, indent=2)
    
    def get_custom_text(self, name):
        custom_text_path = os.path.join(CUSTOM_TEXT_PATH_TEMPLATE.replace("WORKSPACE_NAME", self.workspace))
        if not os.path.exists(custom_text_path):
            with open(custom_text_path, "w") as f:
                f.write()
        custom_text_module = importlib.import_module(f"workspaces.{self.workspace}.custom_text")
        return custom_text_module.__dict__[name]
    
    def resolve_references(self, custom_text, prop="id"):
        titles = [x.title for x in self]
        pattern = r'"([^"]{1,150})"'
        matches = re.findall(pattern, custom_text)
        for m in matches:
            matches = difflib.get_close_matches(m, titles, n=1, cutoff=0.9)
            if len(matches):
                p = [p for p in self if p.title == matches[0]][0]
                resolved = '\\ref{' + getattr(p, prop) + '}'
                custom_text = custom_text.replace(f'"{m}"', resolved)
        return custom_text

    def get_all_references(self, custom_text, prop="id"):
        matches = re.findall(r'\{([^}]{1,150})\}', custom_text)
        referenced_papers = set()
        for m in matches:
            matching_papers = [p for p in self if p.id == m]
            if len(matching_papers):
                p = [p for p in self if p.id == m][0]
                referenced_papers.add(p)
            else:
                print(f"Paper's ID '{m}' not matching")
        return Papers(workspace=self.workspace, papers=referenced_papers)
    
    def expand(self):
        user_papers = [x.replace(".pdf", "") for x in os.listdir(get_user_pdfs_path(self.workspace))]
        request = SCOPE_QUERY_GENERATOR_TITLES.replace(CONTENT_TAG, str(user_papers))
        hash_id = query_to_hash(request.replace(" ", "").replace("\n", ""))
        if not hash_id in self.saved_responses:
            options = {
                "model": "gemini-3-flash-preview",
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 5000,
                    "thinking_config": {
                        "include_thoughts": True,
                        "thinking_budget": 2500
                    }
                }
            }
            response = execute_simple_request("simple_requests", options, request, instant=True)
            self.saved_responses[hash_id] = response
            self.save_responses()
        queries = [x.replace("'", '"') for x in json.loads(self.get_stored_response(hash_id))["semantic_search_queries"]]
        return Papers(workspace=self.workspace, queries=queries)
   
    def get_paper_location(self):
        chunks = [self[i:i + 10] for i in range(0, len(self), 10)]
        p_located = 0
        for papers in chunks:
            change = False
            for p in papers:
                if p.id not in self.paper_loc_map:
                    change = True
                    self.paper_loc_map[p.id] = p.get_paper_location()
                else:
                    p.paper_location = self.paper_loc_map[p.id]
                if p.paper_location is not None:
                    p_located += 1
            if change:
                self.save_paper_location_map()
        print(f"{p_located}/{len(self)} papers located")
    
    def download_papers(self):
        all_pdfs = [x.replace(".pdf", "") for x in os.listdir(get_pdfs_path(self.workspace))]
        all_texts = [x.replace(".txt", "") for x in os.listdir(get_extracted_path(self.workspace))]
        chunks = [self[i:i + 10] for i in range(0, len(self), 10)]
        for papers in chunks:
            change = False
            for p in papers:
                if  (p.abstract == "unknown" and p.id not in all_texts) or \
                    (p.paper_location and p.id not in self.failed_pdf_retrieval and (p.id not in all_pdfs or p.id not in all_texts)):
                    
                    output_file = os.path.join(get_pdfs_path(self.workspace), f"{p.id}.pdf")
                    text_to_be_extracted = True
                    try:
                        if p.id not in all_pdfs and p.abstract != "unknown":
                            response = requests.get(p.paper_location, stream=True, timeout=(5, 15))
                            response.raise_for_status()
                            with open(output_file, "wb") as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                            print(f"Paper {p.id} downloaded")
                    except:
                        self.failed_pdf_retrieval[p.id] = p.id
                        text_to_be_extracted = False
                    change = True
                    if text_to_be_extracted:
                        if p.abstract == "unknown":
                            output_file = os.path.join(get_user_pdfs_path(self.workspace), f"{p.title}.pdf")
                        text_extracted_output = os.path.join(get_extracted_path(self.workspace), f"{p.id}.txt")
                        try:
                            text = extract_text(output_file)
                            with open(text_extracted_output, "w", encoding="utf-8") as f:
                                f.write(text)
                            print(f"Paper {p.id} text extracted")
                        except:
                            self.failed_pdf_retrieval[p.id] = p.id
            if change:
                self.save_failed_pdf_retrieval()
        all_texts = [x.replace(".txt", "") for x in os.listdir(get_extracted_path(self.workspace))]
        for p in self:
            if p.id in all_texts:
                text_extracted_output = os.path.join(get_extracted_path(self.workspace), f"{p.id}.txt")
                with open(text_extracted_output, "r", encoding="utf-8") as f:
                    p.text = f.read()
    
    def where(self, predicate):
        papers = [x for x in self if predicate(x)]
        new_papers = Papers(workspace=self.workspace, papers=papers)
        try:
            src = inspect.getsource(predicate).strip()
            match = re.search(r'lambda.*', src)
            if match:
                lambda_function = match.group()
            else:
                lambda_function = src
        except Exception:
            lambda_function = "unknown"
        print(f"{len(self)} papers filtered by query '{lambda_function}' -> new count: {len(new_papers)}")
        return new_papers

    def perform_ai_task(self, task_name, preview=False, instant=False, force_faulty=False):
        ai_task = [x for x in AI_TASKS if x == task_name]
        if not len(ai_task):
            raise Exception(f"No task called {task_name} found.")
        ai_task = ai_task[0]
        ai_module = importlib.import_module(f"ai_tasks.{task_name}")
        options = ai_module.OPTIONS
        options["task"] = task_name
        options["prompt_structure"] = ai_module.STRUCTURE.strip()

        execute_ai(self.workspace, self, ai_module.OPTIONS, ai_module.shape_content, instant)
        add_ai_md(self.workspace, [x for x in self])
        all_responses = set()
        failed_extractions = []
        for p in self:
            content = p.ai_info.get(task_name, None)
            if content:
                response_str = content["response"]["candidates"][0]["parts"][0]
                extracted_dict = ai_module.extract(response_str)
                all_responses.add(response_str)
                if extracted_dict is None:
                    failed_extractions.append(p)
                else:
                    p.info = {**p.info, **extracted_dict}

        if len(failed_extractions) and force_faulty:
            faulty_papers = Papers(workspace=self.workspace, papers=failed_extractions)
            execute_ai(self.workspace, faulty_papers, ai_module.OPTIONS, ai_module.shape_content, instant, force=True)
            add_ai_md(self.workspace, [x for x in self])
            all_responses = set()
            for p in self:
                content = p.ai_info.get(task_name, None)
                response_str = content["response"]["candidates"][0]["parts"][0]
                extracted_dict = ai_module.extract(response_str)
                all_responses.add(response_str)
                if content:
                    p.info = {**p.info, **extracted_dict}


        if preview:
            # print(f"AI-Task \"{task_name}\" -> responses enumeration:")
            # for r in all_responses:
            #     print(f"- {r}")
            sys.exit(0)
        return self
    
    def get_stored_response(self, hash):
        return self.saved_responses[hash][0]["responses"][0]["response"]["candidates"][0]["parts"][0]
    
    def ai_joint(self, request: str, included_info: list[str]):
        content = ""
        for p in self:
            dict_ = json.loads(json.dumps({k: v for k, v in p.info.items() if k in included_info}))
            dict_ = {"title": p.title, **dict_}
            content += f"{json.dumps(dict_, indent=2)}\n\n"
        request = request.replace(CONTENT_TAG, content)
        hash_id = query_to_hash(request.replace(" ", "").replace("\n", ""))
        if not hash_id in self.saved_responses:
            options = {
                "model": "gemini-3-flash-preview",
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 5000,
                    "thinking_config": {
                        "include_thoughts": True,
                        "thinking_budget": 1500
                    }
                }
            }
            response = execute_simple_request("simple_requests", options, request, instant=True)
            self.saved_responses[hash_id] = response
            self.save_responses()
        return self.get_stored_response(hash_id)
   
    def get_source_papers(self):
        new_papers = Papers(self.workspace, papers=[x for x in self if not x.is_overview()])
        print(f"{len(new_papers)} source papers found")
        return new_papers
   
    def get_overview_papers(self):
        new_papers = Papers(self.workspace, papers=[x for x in self if x.is_overview()])
        print(f"{len(new_papers)} source papers found")
        return new_papers

    def preview_papers(self, first=10):
        for p in self[:-first:-1][::-1]:
            print(f"cit. {p.citationCount}\t{p}\n------------------")
    
    def save_pdfs(self, folder_title: str):
        folder_title = clean_pdf_name(folder_title)
        folder_path = os.path.join(get_saved_pdfs_path(self.workspace), folder_title)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
        cur_saved = os.listdir(folder_path)
        cur_titles = [x.replace(".pdf", "") for x in cur_saved]
        for p in self:
            clean_title = clean_pdf_name(p.title)
            if p.has_paper() and clean_title not in cur_titles:
                from_path = p.get_paper_path(self.workspace)
                to_path = os.path.join(folder_path, clean_title + ".pdf")
                try:
                    shutil.copy2(from_path, to_path)
                except:
                    print(p.title)

    def load_papers(self, ids=None):
        paper_dict: dict[str, SimplePaper] = {}
        raw_path = get_raw_paper_headers(self.workspace)

        for json_name in (x for x in os.listdir(raw_path) if 'query_' in x):
            json_path = os.path.join(raw_path, json_name)
            clean_name = decode_name(json_name, self.workspace)
            with open(json_path, "r", encoding="utf8") as file:
                pps = json.load(file)

            for p in pps:
                pid = p["paperId"]
                if ids is not None and pid not in ids:
                    continue
                if pid not in paper_dict:
                    p["kws"] = {clean_name}
                    paper_dict[pid] = SimplePaper(p_id=pid, **p)
                else:
                    paper_dict[pid].kws.add(clean_name)
        
        folder_path = get_user_pdfs_path(self.workspace)
        for pdf in [x for x in os.listdir(folder_path) if ".pdf" in x]:
            title = pdf.replace(".pdf", "")
            if not title in self.user_pdf_map:
                results = simple_scrape(title)
                for p in results:
                    pid = p["paperId"]
                    self.simple_scrape_results.append(p)
                    self.paper_loc_map[pid] = "local"
            pid = query_to_hash(title)
            self.user_pdf_map[title] = pid
            self.simple_scrape_results.append({"paperId": pid, "title": title, "externalIds": {"DOI": "local"}})

        for p in self.simple_scrape_results:
            pid = p["paperId"]
            if ids is not None and pid not in ids:
                continue
            paper_dict[pid] = SimplePaper(p_id=pid, **p)
        
        papers: list[SimplePaper] = sorted(paper_dict.values(), key=lambda p: p.citationCount)
        add_ai_md(self.workspace, papers)
        print(f"{len(self)} papers loaded.")
        return papers


def add_ai_md(workspace: str, papers: list[SimplePaper]):
    ai_info = {}
    all_responses_fp = [os.path.join(get_responses_path(workspace), x) for x in os.listdir(get_responses_path(workspace))]
    for filepath in all_responses_fp:
        with open(filepath, "r", encoding='utf8') as f:
            info = json.load(f)
            if info["options"]["task"] in AI_TASKS:
                for r in info["contents"]:
                    req_id = r["request"]["req_id"]
                    if req_id not in ai_info:                
                        ai_info[req_id] = {}
                    ai_info[req_id][info["options"]["task"]] = r

    for p in papers:
        p.set_ai_info(ai_info.get(p.id, {}))


def get_oa_pdf_url(doi, email):
    url = f"https://api.unpaywall.org/v2/{doi}"
    params = {"email": email}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("is_oa") and data.get("best_oa_location"):
            pdf_url = data["best_oa_location"].get("url_for_pdf")
            if pdf_url:
                return pdf_url
        return None
    
    except requests.RequestException as e:
        print(f"Error fetching DOI {doi}: {e}")
        return None


if __name__ == "__main__":
    pass
