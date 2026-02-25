import dotenv
import time
import json
import os
import tempfile
from google import genai
from google.genai import types
from gen_ai.model import Model, JobStatus, ErrorMsg, ErrorType


API_KEY = dotenv.get_key(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"), "GEMINI")
client = None


class GeminiFamily(Model):
    model_info = {
        "batches": True,
        "control_thoughts": True,
        "control_reasoning_temp": True,
        "control_thoughts_tokens": True
    }

    def __init__(self):
        global client
        super().__init__()
        self.init_err = None
        try:
            client_ = genai.Client(api_key=API_KEY) if client is None else client
            client_.models.list()
            client = client_
        except Exception as e:
            self.init_err = e
    
    def is_initialized(self):
        return client is not None
    
    def send_batch(self, request, text_list):
        status = JobStatus.JOB_STATE_FAILED
        if not self.is_initialized():
            return status, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        
        requests = [{
            "request": {"contents": [{"parts": [{"text": text}]}]},
            "generationConfig": request.generationConfig
        } for text in text_list]
        
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
        except Exception as e:
            return status, ErrorMsg(ErrorType.BATCH_REQUEST, e)
        finally:
            os.remove(tmp.name)

        try:
            batch_job = client.batches.create(
                model=request.model.name,
                src=uploaded_file.name
            )
            print(f"Batch created: {batch_job.name}")
            super().send_batch(request, text_list)
            status = JobStatus.JOB_STATE_SUCCEEDED
            return status, {"uploadedFileName": uploaded_file.name, "uploadedBatchName": batch_job.name}
        except Exception as e:
            return status, ErrorMsg(ErrorType.BATCH_REQUEST, e)
    
    def cancel_batch(self, request):
        if not self.is_initialized():
            return JobStatus.JOB_STATE_FAILED, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        try:
            client.batches.cancel(name=request.operational["uploadedBatchName"])
            print(f"Cancel requested for batch: {request.operational['uploadedBatchName']}")
            super().cancel_batch(request)
        except Exception as e:
            return JobStatus.JOB_STATE_FAILED, ErrorMsg(ErrorType.BATCH_CANCEL, e)
        return JobStatus.JOB_STATE_SUCCEEDED, None
    
    def fetch_batch_results(self, request):
        status = JobStatus.JOB_STATE_FAILED
        if not self.is_initialized():
            return status, [], ErrorMsg(ErrorType.INITIALIZATION, self.init_err)

        responses = []
        batch_name = request.operational["uploadedBatchName"]
        batch_job = client.batches.get(name=batch_name)

        if batch_job.state.name in JobStatus.get_all_states():
            status = batch_job.state.name
            if batch_job.state.name == JobStatus.JOB_STATE_SUCCEEDED:
                status = JobStatus.JOB_STATE_RUNNING
                try:
                    file_content = client.files.download(file=batch_job.dest.file_name)
                    text = file_content.decode('utf-8')
                    for line in text.splitlines():
                        response_obj = json.loads(line)["response"]
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
                        responses.append(response_text, prompt_tokens, candidates_tokens, thoughts_tokens, total_tokens)
                    super().fetch_batch_results(request)
                except Exception as e:
                    return status, [], ErrorMsg(ErrorType.BATCH_PARSING, e)
                return status, [self.format_response(*r) for r in responses], None

        return status, [], ErrorMsg(ErrorType.BATCH_NOT_READY)
    
    def send_simple_request(self, request, text):
        status = JobStatus.JOB_STATE_FAILED
        if not self.is_initialized():
            return status, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)

        try:
            response_obj = client.models.generate_content(
                model=request.model.name,
                contents=text,
                config=types.GenerateContentConfig(
                    max_output_tokens=request.generationConfig["maxOutputTokens"],
                    temperature=request.generationConfig["temperature"],
                    thinking_config=types.ThinkingConfig(thinking_budget=request.generationConfig["thinking_config"]["thinking_budget"])
                )
            )
        except Exception as e:
            return JobStatus.JOB_STATE_FAILED, {}, ErrorMsg(ErrorType.SIMPLE_REQUEST, e)

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
        return JobStatus.JOB_STATE_SUCCEEDED, self.format_response(response_text, prompt_tokens, candidates_tokens, thoughts_tokens, total_tokens), None


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