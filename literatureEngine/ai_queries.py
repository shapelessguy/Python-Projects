import dotenv
import time
import json
import os
import random
import re
import hashlib
import string
import tempfile
import sys
import threading
from datetime import datetime
from utils import get_queries_path, get_responses_path, WORKSPACES_PATH
from ai_billing import get_costs
from pathlib import Path
from google import genai
from google.genai import types


API_KEY = dotenv.get_key(".env", "GEMINI")
client = genai.Client(api_key=API_KEY)
CONTENT_TAG = "__X__"


def create_query(id: str, text: str):
    return {"req_id": id, "request": {"contents": [{"parts": [{"text": text}]}]}}


def generate_text_extract_req(paper, content_shape):
    text = content_shape(paper)
    return create_query(paper.id, text)


def execute_simple_request(workspace, options, text, instant=False):
    options["prompt_structure"] = CONTENT_TAG
    options["task"] = "simple_request"
    return send_batch(workspace, options["task"], [create_query("", text)], options, instant=instant)


def execute_ai(workspace, papers, options, content_shape, instant=False, force=False):
    task_name = options["task"]
    requests = [
        generate_text_extract_req(p, content_shape) for p in [x for x in papers
                                                              if not x.ai_info.get(task_name, False) or force]
    ]
    if len(requests) > 0:
        send_batch(workspace, options["task"], requests, options, instant=instant, force=force)


def get_global_req_ids(workspace: str):
    all_ids = []

    all_queries_fp = [os.path.join(get_queries_path(workspace), x) for x in os.listdir(get_queries_path(workspace))]
    all_responses_fp = [os.path.join(get_responses_path(workspace), x) for x in os.listdir(get_responses_path(workspace))]
    for filepath in all_queries_fp + all_responses_fp:
        with open(filepath, "r", encoding='utf8') as f:
            info = json.load(f)
            context_hash = hashlib.sha256(info["options"]["prompt_structure"].encode("utf-8")).hexdigest()
            contents = info["requests"] if "requests" in info else info["contents"]
            for r in contents:
                req_id = r["request"]["req_id"]
                all_ids.append(context_hash + req_id)
    return set(all_ids)


def rm_response_req_ids(workspace: str, name: str, ids: list[str]):
    all_responses_fp = [os.path.join(get_responses_path(workspace), x) for x in os.listdir(get_responses_path(workspace))]
    for filepath in all_responses_fp:
        new_contents = []
        info = {}
        with open(filepath, "r", encoding='utf8') as f:
            info = json.load(f)
            if name != info["options"]["task"]:
                continue
            contents = info["requests"] if "requests" in info else info["contents"]
            for content in contents:
                req_id = content["request"]["req_id"]
                if req_id not in ids:
                    new_contents.append(content)
        if len(new_contents) != len(contents):
            info["contents"] = new_contents
            with open(filepath, "w", encoding='utf8') as f:
                json.dump(info, f)
            print(f"Entries removed from {filepath}")


def merge_responses(workspace, input_info, file_name, responses_json):
    if not input_info:
        with open(os.path.join(get_queries_path(workspace), file_name), "r", encoding='utf8') as f:
            input_info = json.load(f)

    final_responses = {**{k: v for k, v in input_info.items() if k != "requests"}, "contents": []}
    n_responses = 0
    for response in responses_json["responses"]:
        key = response["key"]
        matched_response = response["response"]
        matched_request = None
        for request in input_info["requests"]:
            if key == request["key"]:
                matched_request = request["request"]
                break
        if matched_request:
            n_responses += 1
            final_responses["contents"].append({
                "request": matched_request,
                "response": matched_response,
            })
    with open(os.path.join(get_responses_path(workspace), file_name), "w", encoding='utf8') as f:
        json.dump(final_responses, f, indent=2)
    print(f"\tResults for batch {file_name} retrieved. WS: {workspace}")

    if n_responses == 1:
        print(f'\n{final_responses["contents"][0]["response"]["candidates"][0]["parts"][0]}')
    
    if os.path.exists(os.path.join(get_queries_path(workspace), file_name)):
        os.remove(os.path.join(get_queries_path(workspace), file_name))


def execute_instant(requests, options):
    responses = {"responses": []}

    print(f"Instant batch of {len(requests)} elements sent")

    for i, request in enumerate(requests, start=1):
        text = request["request"]["contents"][0]["parts"][0]["text"]
        res_exhausted = False
        while True:
            try:
                response = client.models.generate_content(
                    model=options["model"],
                    contents=text,
                    config=types.GenerateContentConfig(
                        max_output_tokens=options["generationConfig"]["maxOutputTokens"],
                        temperature=options["generationConfig"]["temperature"],
                        thinking_config=types.ThinkingConfig(thinking_budget=options["generationConfig"]["thinking_config"]["thinking_budget"])
                    )
                )
                if res_exhausted:
                    print("Resources released.")
                    res_exhausted = False
            except Exception as e:
                if "RESOURCE_EXHAUSTED" in str(e):
                    if not res_exhausted:
                        print("Resources exhausted. Waiting for their release.")
                        res_exhausted = True
                    time.sleep(10)
                    continue
                raise Exception(e)
            break
        response_info = generate_response_info(response)
        response_dict = {"key": f"request-{i}", "response": response_info}
        responses["responses"].append(response_dict)
    return responses


def execute_batch(requests, options):
    tmp = tempfile.NamedTemporaryFile(mode="w+", suffix=".jsonl", delete=False)
    try:
        for req in requests:
            tmp.write(json.dumps(req) + "\n")
        tmp.close()

        uploaded_file = client.files.upload(
            file=tmp.name,
            config=types.UploadFileConfig(mime_type="jsonl")
        )
        print(f"Uploaded file: {uploaded_file.name}")

    finally:
        os.remove(tmp.name)

    batch_job = client.batches.create(
        model=options["model"],
        src=uploaded_file.name
    )
    print(f"Batch created: {batch_job.name}")
    return uploaded_file.name, batch_job.name


def chunk_batch(lst, size):
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def estimate_tokens(requests, options, batch):
    token_count_per_req = 0
    for r in requests:
        for content in r["request"]["contents"]:
            for part in content["parts"]:
                token_count_per_req += len(part["text"])
    token_count_per_req /= (4 * len(requests))
    max_output_tokens = options["generationConfig"]["maxOutputTokens"]
    if options["generationConfig"]["thinking_config"]["include_thoughts"]:
        max_output_tokens += options["generationConfig"]["thinking_config"]["thinking_budget"]
    info = {"input_token_count": token_count_per_req, "max_output_token_count": max_output_tokens}
    costs = get_costs(options["model"], token_count_per_req, max_output_tokens, len(requests), batch=batch)
    stats = f"Billing estimation for the current batch of requests:\n"
    stats += f"\n\tModel: {costs['model']}\n"
    stats += f"\t  Number of requests: {costs['n_requests']}\n"
    stats += f"\t  Prompt tokens per request ~ {int(costs['input_tokens'])}\n"
    stats += f"\t  Max generable tokens: {costs['output_tokens']}\n"
    stats += f"\t  Price: {costs['price']}€ (max)\n"
    print(stats)
    return info


def send_batch(workspace: str, name: str, raw_requests: list[dict], options: dict, req_hash="", instant=False, force=False):
    global_req_ids = get_global_req_ids(workspace)
    name = validate_name(name)
    os.makedirs(os.path.dirname(get_queries_path(workspace)), exist_ok=True)
    os.makedirs(os.path.dirname(get_responses_path(workspace)), exist_ok=True)
    if req_hash != "":
        name_id = req_hash
    else:
        name_id = ''.join(random.choices(string.ascii_letters + string.digits, k=12))

    context_hash = hashlib.sha256(options["prompt_structure"].encode("utf-8")).hexdigest()
    if not force:
        new_requests = [x for x in raw_requests if instant or (context_hash + x["req_id"]) not in global_req_ids]
    else:
        new_requests = raw_requests
        rm_response_req_ids(workspace, name, [x["req_id"] for x in raw_requests])
    if len(new_requests) != len(raw_requests):
        print(f"{len(raw_requests) - len(new_requests)}/{len(raw_requests)} requests have been already processed.")
    else:
        estimate_tokens(raw_requests, options, batch=not instant)
        sure = input(f"Sending AI queries. Are you sure you want to continue? (yes/n) ").lower().strip() == "yes"
        if not sure:
            sys.exit(0)

    chunks = chunk_batch(new_requests, 1000 if not instant else 50)
    chunk_responses = []
    for chunk_i, chunk_requests in enumerate(chunks, start=1):
        namepart = f"-part{chunk_i}" if len(chunks) > 1 else ""
        file_name = f"{name}-{name_id}{namepart}.json"
        if os.path.exists(os.path.join(get_queries_path(workspace), file_name)):
            continue

        requests = [{"key": f"request-{i}", "request": json.loads(json.dumps(x))["request"]} for i, x in enumerate(chunk_requests, start=1)]
        for r in requests:
            r["request"]["generationConfig"] = options["generationConfig"]
            for content in r["request"]["contents"]:
                for part in content["parts"]:
                    part["text"] = options["prompt_structure"].replace(CONTENT_TAG, part["text"])
        requests = json.loads(json.dumps(requests))
        
        responses_json = None
        uploaded_file_name = None
        uploaded_batch_name = None
        if instant:
            responses_json = execute_instant(requests, options)
        else:
            uploaded_file_name, uploaded_batch_name = execute_batch(requests, options)

        req_md = [{"key": f"request-{i}", "request": {"date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "req_id": x["req_id"], **x["request"]}}
                  for i, x in enumerate(chunk_requests, start=1)]
        info = {
            "uploadedFileName": uploaded_file_name,
            "uploadedBatchName": uploaded_batch_name,
            "options": options,
            "requests": req_md
        }

        if responses_json:
            merge_responses(workspace, info, file_name, responses_json)
            chunk_responses.append(responses_json)
        else:
            with open(os.path.join(get_queries_path(workspace), file_name), "w", encoding='utf8') as f:
                json.dump(info, f, indent=2)

    if not instant:
        retrieve_responses(workspace)
    else:
        return chunk_responses


def generate_response_info(response_obj, type="object"):
    response_info = {}
    usage = response_obj.usage_metadata if type == "object" else response_obj["usageMetadata"]
    response_info["model_version"] = response_obj.model_version if type == "object" else response_obj["modelVersion"]
    response_info["prompt_tokens"] = usage.prompt_token_count if type == "object" else usage["promptTokenCount"]
    response_info["candidates_tokens"] = usage.candidates_token_count if type == "object" else usage["candidatesTokenCount"]
    response_info["thoughts_tokens"] = usage.thoughts_token_count if type == "object" else usage.get("thoughtsTokenCount", None)
    response_info["total_tokens"] = usage.total_token_count if type == "object" else usage["totalTokenCount"]
    response_info["candidates"] = []

    for candidate in (response_obj.candidates if type == "object" else response_obj["candidates"]):
        parts = []
        candidate_ = {"role": (candidate.content.role if type == "object" else candidate["content"]["role"]), "parts": parts}
        response_info["candidates"].append(candidate_)
        for part in (candidate.content.parts if type == "object" else candidate["content"]["parts"]):
            parts.append(part.text if type == "object" else part["text"])
    return response_info


def retrieve_responses(workspace: str, signal={"kill": False}):
    print(f"Fetching results for {workspace}...")
    all_queries = os.listdir(get_queries_path(workspace))
    all_responses = os.listdir(get_responses_path(workspace))
    pending_queries = [x for x in all_queries if x not in all_responses]
    pending_batch_ids = {}
    
    if not len(pending_queries):
        print(f"Responses for {workspace} already fetched.")
        return
    
    pending_names = []
    for fp in [os.path.join(get_queries_path(workspace), x) for x in pending_queries]:
        with open(fp, "r", encoding='utf8') as file:
            batch_name = json.load(file)["uploadedBatchName"]
            if batch_name:
                pending_names.append(Path(fp).stem.split("-")[0])
                pending_batch_ids[batch_name] = fp
    
    completed_ids = []
    adv_num_completed = -1
    loop_end = False
    while not loop_end:
        if adv_num_completed != len(completed_ids):
            print(f"{len(pending_batch_ids) - len(completed_ids)} batches for {workspace} to fetch")
            adv_num_completed = len(completed_ids)
        for batch_name, query_fp in pending_batch_ids.items():
            if len(completed_ids) == len(pending_batch_ids):
                loop_end = True
                break
            if batch_name not in completed_ids:
                responses = {"responses": []}
                batch_job = client.batches.get(name=batch_name)

                if batch_job.state.name in ('JOB_STATE_SUCCEEDED', 'JOB_STATE_FAILED', 'JOB_STATE_CANCELLED', 'JOB_STATE_EXPIRED'):
                    if batch_job.state.name == 'JOB_STATE_CANCELLED':
                        print(f"Batch job cancelled for {workspace}: {batch_name}")
                    elif batch_job.dest.inlined_responses is not None:
                        for i, inline_response in enumerate(batch_job.dest.inlined_responses, start=1):
                            response_info = generate_response_info(inline_response.response)
                            response = {"key": f"request-{i}", "response": response_info}
                            responses["responses"].append(response)
                    elif batch_job.dest.file_name is not None:
                        result_file_name = batch_job.dest.file_name
                        file_content = client.files.download(file=result_file_name)
                        text = file_content.decode('utf-8')
                        for i, line in enumerate(text.splitlines(), start=1):
                            try:
                                response_info = generate_response_info(json.loads(line)["response"], type="json")
                                response = {"key": f"request-{i}", "response": response_info}
                                responses["responses"].append(response)
                            except:
                                print(f"Error on fetching results for {workspace}: \n{json.loads(line)}")
                        
                    merge_responses(workspace, input_info=None, file_name=Path(query_fp).stem + ".json", responses_json=responses)
                    completed_ids.append(batch_name)
                elif batch_job.state.name == "JOB_STATE_RUNNING":
                    pass
                else:
                    print(f"Unknown state: {batch_job.state.name}")
        if len(pending_batch_ids) == len(completed_ids):
            break
        if not loop_end:
            for _ in range(30):
                time.sleep(1)
                if signal["kill"]:
                    return


def validate_name(name: str):
    if not name or name.strip() == "":
        raise Exception("Folder name cannot be empty or just whitespace.")
    name = name.strip()
    forbidden_chars = r'[-<>:"/\\|?*\0]'
    if re.search(forbidden_chars, name):
        raise Exception(f"Folder name contains forbidden characters ({forbidden_chars}): {name}")
    if name[-1] in {" ", "."}:
        raise Exception(f"Folder name cannot end with space or dot: {name}")
    return name.strip()


def generate(workspace: str, name='test', requests=None, options=None, instant=False):
    if requests is None:
        requests = [
            {"req_id": "", "request": {"contents": [{"parts": [{"text": "How old is the Earth?"}]}]}}
        ]
    if options is None:
        prompt_structure = f"{CONTENT_TAG}"
        options = {
            "model": "gemini-3-flash-preview",
            "prompt_structure": prompt_structure,
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 512,
                "thinking_config": {
                    "include_thoughts": False,
                    "thinking_budget": 0
                }
            }
        }
    send_batch(workspace, name, requests, options, instant)


SCOPE_QUERY_GENERATOR_TITLES = f"""
You are an expert in academic research, literature search, and query generation.

You will be given a **list of paper titles only**. 
Your task is to **understand the likely research scope, topics, and objectives** represented by these titles, and then generate a **comprehensive list of search queries** suitable for use in academic search engines such as Semantic Scholar, Google Scholar, or Scopus.

Instructions:

1. Analyze the paper titles to infer the user's research focus, key topics, methods, and related areas. Consider recurring concepts, keywords, and patterns in the titles.

2. Generate a **long and diverse list of search queries** (at least 20-50, ideally more) that cover:
   - Key concepts and their synonyms
   - Possible related methods or approaches implied by the titles
   - Subtopics or peripheral areas suggested by recurring keywords
   - Variations in phrasing, alternative terms, and co-occurring concepts

3. Strict Query Formatting Rules:

- Use **+ for AND**. The + must be attached to the next term **without spaces**.
- Use **| for OR** inside parentheses only.
- Use parentheses to group alternatives where needed.
- Use **single quotes ('') for exact phrases inside the queries**.
- **Do NOT** use the words AND or OR anywhere.
- Each query should be syntactically correct and ready to paste into Semantic Scholar.
- Example of correct formatting:
   ('research challenges' | 'open challenges' | 'future directions') +('AI' | 'LLM') +('requirements')

4. Prioritize **high recall**, even if some queries are broad. Include variations that capture the same concept with slightly different terminology.

5. Avoid inventing topics unrelated to the papers. Only propose queries consistent with the titles' content and themes.

6. Output must be **valid JSON** with the following structure:
{{
"semantic_search_queries": [
    "<query 1>",
    "<query 2>",
    "... up to 50 or more queries"
]
}}

Paper titles:
{CONTENT_TAG}

Output Format Rules (MANDATORY):
1. Output MUST be valid JSON.
2. Output MUST contain ONLY the keys defined in the schema.
3. Do NOT include markdown, code fences (```), or any other formatting.
4. Do NOT add any explanation, comments, or text outside the JSON object.
"""



if __name__ == "__main__":
    batches_to_cancel = [
        "batches/lsgsyabepg4zfqyobvp630adzizs1u7ma1lf"#  -> example
    ]
    for b in batches_to_cancel:
        client.batches.cancel(name=b)
    # generate(instant=True)

    signal = {'kill': False}
    all_workspaces = [x for x in os.listdir(WORKSPACES_PATH) if os.path.isdir(os.path.join(WORKSPACES_PATH, x))]
    threads: list[threading.Thread] = []

    for ws in all_workspaces:
        t = threading.Thread(target=retrieve_responses, args=(ws, signal))
        threads.append(t)
        t.start()

    try:
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(timeout=0.5)
    except KeyboardInterrupt:
        signal['kill'] = True
        for t in threads:
            t.join()
