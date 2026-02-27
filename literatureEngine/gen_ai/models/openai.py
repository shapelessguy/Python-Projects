import dotenv
import os
import tempfile
import json
from openai import OpenAI
from gen_ai.utils import count_tokens, construct_prompt
from gen_ai.model import Model, JobStatus, RequestStatus, ErrorMsg, ErrorType


API_KEY = dotenv.get_key(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"), "OPENAI")
client = None


class OpenAiFamily(Model):
    model_info = {
        "batches": True,
        "control_thoughts": False,
        "control_reasoning_temp": False,
        "control_thoughts_tokens": False
    }

    def __init__(self):
        global client
        super().__init__()
        self.init_err = None
        try:
            client_ = OpenAI(api_key=API_KEY) if client is None else client
            client_.models.list()
            client = client_
        except Exception as e:
            self.init_err = e
    
    def is_initialized(self):
        return client is not None
    
    def send_batch(self, request):
        req_status = RequestStatus.FAILED
        if not self.is_initialized():
            return req_status, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
    
        requests = []
        for req_id, text in request.get_full_requests().items():
            body = {
                "model": request.model.name,
                "messages": [
                    {"role": "system", "content": request.generationConfig.get("systemPrompt", "")},
                    {"role": "user", "content": text},
                ],
                "max_completion_tokens": request.generationConfig.get("maxOutputTokens", 999999)
            }
            is_reasoning_model = any(prefix in request.model.name.lower() for prefix in ["o1", "o3", "o4", "gpt-5", "reasoning"])
            if not is_reasoning_model:
                body["temperature"] = request.generationConfig.get("temperature", 0)

            batch_line = {
                "custom_id": req_id,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": body
            }
            requests.append(batch_line)

        batch_job = None
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = os.path.join(tmp_dir, "batch_requests.jsonl")
                try:
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        for req in requests:
                            f.write(json.dumps(req) + "\n")

                    uploaded_file = client.files.create(
                        file=open(tmp_path, "rb"),
                        purpose="batch"
                    )
                    print(f"Uploaded file: {uploaded_file.id} ({uploaded_file.filename})")
                except Exception as e:
                    return req_status, ErrorMsg(ErrorType.BATCH_REQUEST, e)

                try:
                    batch_job = client.batches.create(
                        input_file_id=uploaded_file.id,
                        endpoint="/v1/chat/completions",
                        completion_window="24h",
                    )
                    print(f"Batch created: {batch_job.id}")
                    req_status = RequestStatus.SUCCEEDED
                    super().send_batch(request)
                    return req_status, {"uploadedFileId": uploaded_file.id, "batchJobId": batch_job.id}
                except Exception as e:
                    return req_status, ErrorMsg(ErrorType.BATCH_REQUEST, e)
        except:
            pass
        if batch_job:
            return req_status, {"uploadedFileId": uploaded_file.id, "batchJobId": batch_job.id}
        return req_status, ErrorMsg(ErrorType.BATCH_REQUEST, e)
    
    def cancel_batch(self, request):
        if not self.is_initialized():
            return RequestStatus.FAILED, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        try:
            client.batches.cancel(name=request.operational["batchJobId"])
            print(f"Cancel requested for batch: {request.operational['batchJobId']}")
            super().cancel_batch(request)
        except Exception as e:
            return RequestStatus.FAILED, ErrorMsg(ErrorType.BATCH_CANCEL, e)
        return RequestStatus.SUCCEEDED, None
    
    def fetch_batch_results(self, request):
        status_map = {
            "failed": JobStatus.JOB_STATE_FAILED,
            "cancelled": JobStatus.JOB_STATE_CANCELLED,
            "expired": JobStatus.JOB_STATE_EXPIRED,
            "completed": JobStatus.JOB_STATE_SUCCEEDED,
            "in_progress": JobStatus.JOB_STATE_RUNNING,
            "validating": JobStatus.JOB_STATE_PENDING,
        }
        job_status = status_map.get(batch_job.status, request.status)

        if not self.is_initialized():
            return job_status, [], ErrorMsg(ErrorType.INITIALIZATION, self.init_err)

        responses = {}
        batch_id = request.operational["batchJobId"]

        try:
            batch_job = client.batches.retrieve(batch_id)
        except Exception as e:
            return job_status, [], ErrorMsg(ErrorType.BATCH_REQUEST, f"Failed to retrieve batch: {e}")
        
        if job_status == JobStatus.JOB_STATE_SUCCEEDED:
            if not batch_job.output_file_id:
                return JobStatus.JOB_STATE_FAILED, [], ErrorMsg(ErrorType.BATCH_PARSING, "Completed but no output_file_id")
            try:
                file_response = client.files.content(batch_job.output_file_id)
                output_text = file_response.text


                for line in output_text.splitlines():
                    if not line.strip():
                        continue
                    try:
                        result = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    body = result["response"]["body"]
                    req_id = result["custom_id"]
                    usage = body.get("usage", {})
                    choices = body.get("choices", [])
                    response_text = ""
                    for choice in choices:
                        message = choice.get("message", {})
                        content = message.get("content", "")
                        response_text += content

                    prompt_tokens = usage.get("prompt_tokens", 0)
                    candidates_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", 0)
                    thoughts_tokens = 0
                    if "completion_tokens_details" in usage:
                        thoughts_tokens = usage["completion_tokens_details"].get("reasoning_tokens", 0)
                    self.add_cost(request, prompt_tokens, total_tokens - prompt_tokens)
                    responses[req_id] = (response_text, prompt_tokens, candidates_tokens, thoughts_tokens, total_tokens)

                super().fetch_batch_results(request)
                job_status = JobStatus.JOB_STATE_SUCCEEDED
                return job_status, {_id: self.format_response(*r) for _id, r in responses.items()}, None

            except Exception as e:
                return request.status, [], ErrorMsg(ErrorType.BATCH_PARSING, f"Failed to parse output: {e}")
        return job_status, [], ErrorMsg(ErrorType.BATCH_NOT_READY)
    
    def send_simple_request(self, request, text):
        req_status = RequestStatus.FAILED
        if not self.is_initialized():
            return req_status, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)

        try:
            api_params = {
                "model": request.model.name,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": text},
                ],
                "max_completion_tokens": request.generationConfig.get("maxOutputTokens", 999999)
            }
            is_reasoning_model = any(prefix in request.model.name.lower() for prefix in ["o1", "o3", "o4", "gpt-5", "reasoning"])
            if not is_reasoning_model:
                api_params["temperature"] = request.generationConfig.get("temperature", 0)
            response = client.chat.completions.create(**api_params)
        except Exception as e:
            return RequestStatus.FAILED, {}, ErrorMsg(ErrorType.SIMPLE_REQUEST, e)

        usage = response.usage
        prompt_tokens = usage.prompt_tokens
        candidates_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens
        thoughts_tokens = 0

        if hasattr(usage, "completion_tokens_details") and hasattr(usage.completion_tokens_details, "reasoning_tokens"):
            thoughts_tokens = usage.completion_tokens_details.reasoning_tokens
        response_text = "".join(choice.message.content or "" for choice in response.choices)
        
        self.add_cost(request, prompt_tokens, total_tokens - prompt_tokens)
        super().send_simple_request(request, text)
        return RequestStatus.SUCCEEDED, self.format_response(response_text, prompt_tokens, candidates_tokens, thoughts_tokens, total_tokens), None
    
    def stream_request(self, request, text, on_stream_cb):
        req_status = RequestStatus.FAILED
        if not self.is_initialized():
            return req_status, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)

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


class gpt_5_2(OpenAiFamily):
    name = "gpt-5.2"
    pricing = {
        "input": 1.75,
        "output": 14.00
    }


class gpt_5_1(OpenAiFamily):
    name = "gpt-5.1"
    pricing = {
        "input": 1.25,
        "output": 10.00
    }


class gpt_5(OpenAiFamily):
    name = "gpt-5"
    pricing = {
        "input": 1.25,
        "output": 10.00
    }


class gpt_5_mini(OpenAiFamily):
    name = "gpt-5-mini"
    pricing = {
        "input": 0.25,
        "output": 2.00
    }


class gpt_5_nano(OpenAiFamily):
    name = "gpt-5-nano"
    pricing = {
        "input": 0.05,
        "output": 0.40
    }


class gpt_5_2_pro(OpenAiFamily):
    name = "gpt-5.2-pro"
    pricing = {
        "input": 21.00,
        "output": 168.00
    }


class gpt_5_pro(OpenAiFamily):
    name = "gpt-5-pro"
    pricing = {
        "input": 15.00,
        "output": 120.00
    }


class gpt_4_1(OpenAiFamily):
    name = "gpt-4.1"
    pricing = {
        "input": 2.00,
        "output": 8.00
    }


class gpt_4_1_mini(OpenAiFamily):
    name = "gpt-4.1-mini"
    pricing = {
        "input": 0.40,
        "output": 1.60
    }


class gpt_4_1_nano(OpenAiFamily):
    name = "gpt-4.1-nano"
    pricing = {
        "input": 0.10,
        "output": 0.40
    }


class gpt_4o(OpenAiFamily):
    name = "gpt-4o"
    pricing = {
        "input": 2.50,
        "output": 10.00
    }


class gpt_4o_2024_05_13(OpenAiFamily):
    name = "gpt-4o-2024-05-13"
    pricing = {
        "input": 5.00,
        "output": 15.00
    }


class gpt_4o_mini(OpenAiFamily):
    name = "gpt-4o-mini"
    pricing = {
        "input": 0.15,
        "output": 0.60
    }


class o1(OpenAiFamily):
    name = "o1"
    pricing = {
        "input": 15.00,
        "output": 60.00
    }


class o1_pro(OpenAiFamily):
    name = "o1-pro"
    pricing = {
        "input": 150.00,
        "output": 600.00
    }


class o3_pro(OpenAiFamily):
    name = "o3-pro"
    pricing = {
        "input": 20.00,
        "output": 80.00
    }


class o3(OpenAiFamily):
    name = "o3"
    pricing = {
        "input": 2.00,
        "output": 8.00
    }


class o3_deep_research(OpenAiFamily):
    name = "o3-deep-research"
    pricing = {
        "input": 10.00,
        "output": 40.00
    }


class o4_mini(OpenAiFamily):
    name = "o4-mini"
    pricing = {
        "input": 1.10,
        "output": 4.40
    }


class o4_mini_deep_research(OpenAiFamily):
    name = "o4-mini-deep-research"
    pricing = {
        "input": 2.00,
        "output": 8.00
    }


class o3_mini(OpenAiFamily):
    name = "o3-mini"
    pricing = {
        "input": 1.10,
        "output": 4.40
    }


class o1_mini(OpenAiFamily):
    name = "o1-mini"
    pricing = {
        "input": 1.10,
        "output": 4.40
    }
