import json
import os
from gen_ai.utils import count_tokens, construct_prompt, CACHE_FOLDER_PATH
from openai import OpenAI
from google import genai
from google.genai import types
from gen_ai.model import Model, JobStatus, RequestStatus, ErrorMsg, ErrorType


google_client = None
client = None


class GeminiFamily(Model):
    model_info = {
        "batches": True,
        "control_thoughts": True,
        "control_reasoning_temp": True,
        "control_thoughts_tokens": True
    }

    def __init__(self, api_key):
        global google_client, client
        super().__init__(api_key)
        self.init_err = None
        try:
            client_ = genai.Client(api_key=api_key) if google_client is None else google_client
            client_.models.list()
            google_client = client_
            client_ = OpenAI(api_key=api_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
            client_.models.list()
            client = client_
        except Exception as e:
            self.init_err = e
    
    def is_initialized(self):
        return google_client is not None and client is not None
    
    def send_batch(self, request):
        if not self.is_initialized():
            return RequestStatus.FAILED, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        
        requests = [{
            "key": req_id,
            "request": {"contents": [{"parts": [{"text": text}]}]},
            "generationConfig": request.generationConfig
        } for req_id, text in request.get_full_requests().items()]
        
        try:
            tmp_path = os.path.join(CACHE_FOLDER_PATH, f"{request.req_id}.jsonl")
            with open(tmp_path, "w+") as file:
                for req in requests:
                    file.write(json.dumps(req) + "\n")
            uploaded_file = google_client.files.upload(
                file=open(tmp_path, "rb"),
                config=types.UploadFileConfig(mime_type="jsonl")
            )
            print(f"Uploaded file: {uploaded_file.name}")
        except Exception as e:
            return RequestStatus.FAILED, ErrorMsg(ErrorType.BATCH_REQUEST, e)

        try:
            batch_job = google_client.batches.create(
                model=request.model.name,
                src=uploaded_file.name
            )
            print(f"Batch created: {batch_job.name}")
            super().send_batch(request)
            return RequestStatus.SUCCEEDED, {"uploadedFileName": uploaded_file.name, "uploadedBatchName": batch_job.name}
        except Exception as e:
            return RequestStatus.FAILED, ErrorMsg(ErrorType.BATCH_REQUEST, e)
    
    def cancel_batch(self, request):
        if not self.is_initialized():
            return RequestStatus.FAILED, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        try:
            google_client.batches.cancel(name=request.operational["uploadedBatchName"])
            print(f"Cancel requested for batch: {request.operational['uploadedBatchName']}")
            super().cancel_batch(request)
        except Exception as e:
            return RequestStatus.FAILED, ErrorMsg(ErrorType.BATCH_CANCEL, e)
        return RequestStatus.SUCCEEDED, None
    
    def fetch_batch_results(self, request):
        prev_job_status = request.status
        if not self.is_initialized():
            return prev_job_status, [], ErrorMsg(ErrorType.INITIALIZATION, self.init_err)

        responses = {}
        batch_name = request.operational["uploadedBatchName"]
        try:
            batch_job = google_client.batches.get(name=batch_name)
        except Exception as e:
            return prev_job_status, [], ErrorMsg(ErrorType.BATCH_REQUEST, f"Failed to retrieve batch: {e}")

        if batch_job.state.name == JobStatus.JOB_STATE_SUCCEEDED:
            try:
                file_content = google_client.files.download(file=batch_job.dest.file_name)
                text = file_content.decode('utf-8')
                for line in text.splitlines():
                    out_json = json.loads(line)
                    req_id = out_json["key"]
                    response_obj = out_json["response"]
                    usage = response_obj["usageMetadata"]
                    response_text = ""
                    prompt_tokens = usage["promptTokenCount"]
                    candidates_tokens = usage["candidatesTokenCount"]
                    thoughts_tokens = usage.get("thoughtsTokenCount", None)
                    total_tokens = usage["totalTokenCount"]
                    for candidate in response_obj["candidates"]:
                        for part in candidate["content"]["parts"]:
                            response_text += part["text"]
                    self.add_cost(request, prompt_tokens, total_tokens - prompt_tokens)
                    responses[req_id] = (response_text, prompt_tokens, candidates_tokens, thoughts_tokens, total_tokens)
                super().fetch_batch_results(request)
                return JobStatus.JOB_STATE_SUCCEEDED, {_id: self.format_response(*r) for _id, r in responses.items()}, None
            except Exception as e:
                return prev_job_status, [], ErrorMsg(ErrorType.BATCH_PARSING, e)
        return prev_job_status, [], ErrorMsg(ErrorType.BATCH_NOT_READY)
    
    def send_simple_request(self, request, text):
        if not self.is_initialized():
            return RequestStatus.FAILED, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)

        try:
            response_obj = google_client.models.generate_content(
                model=request.model.name,
                contents=text,
                config=types.GenerateContentConfig(
                    max_output_tokens=request.generationConfig.get("maxOutputTokens", 999999),
                    temperature=request.generationConfig.get("temperature", 0),
                    thinking_config=types.ThinkingConfig(thinking_budget=request.generationConfig.get("thinking_config",
                                                                                                      {"thinking_budget": {"include_thoughts": False}})["thinking_budget"])
                )
            )
        except Exception as e:
            return RequestStatus.FAILED, {}, ErrorMsg(ErrorType.SIMPLE_REQUEST, e)

        usage = response_obj.usage_metadata
        prompt_tokens = usage.prompt_token_count
        candidates_tokens = usage.candidates_token_count
        thoughts_tokens = usage.thoughts_token_count
        total_tokens = usage.total_token_count
        response_text = ""
        for candidate in (response_obj.candidates):
            for part in (candidate.content.parts):
                response_text += part.text
        self.add_cost(request, prompt_tokens, total_tokens - prompt_tokens)
        super().send_simple_request(request, text)
        return RequestStatus.SUCCEEDED, self.format_response(response_text, prompt_tokens, candidates_tokens, thoughts_tokens, total_tokens), None
    
    def stream_request(self, request, text, on_stream_cb):
        if not self.is_initialized():
            return RequestStatus.FAILED, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)

        try:
            messages=[
                {"role": "system", "content": request.generationConfig.get("systemPrompt", "")}
            ]
            for content in request.contents:
                if content["response"] != {}:
                    messages.append({"role": "user", "content": construct_prompt(request.prompt_structure, content["request"])})
                    messages.append({"role": "assistant", "content": content["response"]["text"]})
            messages.append({"role": "user", "content": text})
                
            response = client.chat.completions.create(
                model=request.model.name,
                messages=messages,
                stream=True
            )

            response_text = ""
            for chunk in response:
                segment = chunk.choices[0].delta.content
                if type(segment) is not str:
                    break
                if on_stream_cb:
                    try:
                        on_stream_cb(request.req_id, segment)
                    except:
                        pass
                response_text += segment
        except Exception as e:
            return RequestStatus.FAILED, {}, ErrorMsg(ErrorType.SIMPLE_REQUEST, e)
        
        prompt_tokens = count_tokens(json.dumps(messages))
        total_tokens = prompt_tokens + count_tokens(response_text)
        self.add_cost(request, prompt_tokens, total_tokens - prompt_tokens)
        super().stream_request(request, text, on_stream_cb)
        return RequestStatus.SUCCEEDED, self.format_response(response_text, prompt_tokens, total_tokens - prompt_tokens, 0, total_tokens), None


class gemini_3_pro_preview(GeminiFamily):
    name = "gemini-3-pro-preview"
    pricing = {
        "input": 2.00,
        "output": 9.00
    }

class gemini_2_5_pro(GeminiFamily):
    name = "gemini-2.5-pro"
    pricing = {
        "input": 1.25,
        "output": 7.50
    }


class gemini_3_flash_preview(GeminiFamily):
    name = "gemini-3-flash-preview"
    pricing = {
        "input": 0.25,
        "output": 1.50
    }


class gemini_2_5_flash(GeminiFamily):
    name = "gemini-2.5-flash"
    pricing = {
        "input": 0.15,
        "output": 1.25
    }


class gemini_2_5_flash_lite(GeminiFamily):
    name = "gemini-2.5-flash-lite"
    pricing = {
        "input": 0.05,
        "output": 0.20
    }


class gemini_2_5_flash_lite_preview_09_2025(GeminiFamily):
    name = "gemini-2.5-flash-lite-preview-09-2025"
    pricing = {
        "input": 0.05,
        "output": 0.20
    }