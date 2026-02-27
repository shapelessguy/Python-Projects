import os
import json
from openai import OpenAI
from gen_ai.model import Model, JobStatus, RequestStatus, ErrorMsg, ErrorType
from gen_ai.utils import count_tokens, construct_prompt


client = None


class DeepSeekFamily(Model):
    model_info = {
        "batches": False,
        "control_thoughts": True,
        "control_reasoning_temp": True,
        "control_thoughts_tokens": False
    }

    def __init__(self, api_key):
        global client
        super().__init__(api_key)
        self.init_err = None
        try:
            client_ = OpenAI(api_key=api_key, base_url="https://api.deepseek.com") if client is None else client
            client_.models.list()
            client = client_
        except Exception as e:
            self.init_err = e
    
    def is_initialized(self):
        return client is not None
    
    def send_batch(self, request):
        return RequestStatus.FAILED, ErrorMsg(ErrorType.NOT_SUPPORTED)
    
    def cancel_batch(self, request, text_list):
        return RequestStatus.FAILED, ErrorMsg(ErrorType.NOT_SUPPORTED)
    
    def fetch_batch_results(self, request):
        return JobStatus.JOB_STATE_FAILED, {}, ErrorMsg(ErrorType.NOT_SUPPORTED)
    
    def send_simple_request(self, request, text):
        if not self.is_initialized():
            return RequestStatus.FAILED, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)

        try:
            messages=[
                {"role": "system", "content": request.generationConfig.get("systemPrompt", "")},
                {"role": "user", "content": text},
            ]
            response = client.chat.completions.create(
                model=request.model.name,
                messages=messages,
                max_tokens=request.generationConfig.get("maxOutputTokens", 999999),
                temperature=request.generationConfig.get("temperature", 0),
                extra_body={
                    "thinking": {
                        "type": "enabled" if request.generationConfig.get("thinking_config", {"include_thoughts": False})["include_thoughts"] else "disabled"
                    }
                }
            )
        except Exception as e:
            return RequestStatus.FAILED, {}, ErrorMsg(ErrorType.SIMPLE_REQUEST, e)

        usage = response.usage
        prompt_tokens = usage.prompt_tokens
        candidates_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens
        response_text = ""
        reasoning = ""
        for choice in response.choices:
            if hasattr(choice.message, "reasoning_content"):
                reasoning += choice.message.reasoning_content
            response_text += choice.message.content or ""
        thoughts_tokens = count_tokens(reasoning)

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


class deepseek_reasoner(DeepSeekFamily):
    name = "deepseek-reasoner"
    pricing = {
        "input": 0.28,
        "output": 0.42
    }


class deepseek_chat(DeepSeekFamily):
    name = "deepseek-chat"
    pricing = {
        "input": 0.28,
        "output": 0.42
    }
