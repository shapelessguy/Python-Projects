import dotenv
import os
from openai import OpenAI
from gen_ai.model import Model, JobStatus, ErrorMsg, ErrorType
from gen_ai.utils import count_tokens


API_KEY = dotenv.get_key(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"), "DEEPSEEK")
client = None


class DeepSeekFamily(Model):
    model_info = {
        "batches": False,
        "control_thoughts": True,
        "control_reasoning_temp": True,
        "control_thoughts_tokens": False
    }

    def __init__(self):
        global client
        super().__init__()
        self.init_err = None
        try:
            client_ = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com") if client is None else client
            client_.list_models()
            client = client_
        except Exception as e:
            self.init_err = e
    
    def is_initialized(self):
        return client is not None
    
    def send_batch(self, request, text_list):
        return JobStatus.JOB_STATE_FAILED, ErrorMsg(ErrorType.NOT_SUPPORTED)
    
    def cancel_batch(self, request, text_list):
        return JobStatus.JOB_STATE_FAILED, ErrorMsg(ErrorType.NOT_SUPPORTED)
    
    def fetch_batch_results(self, request):
        return JobStatus.JOB_STATE_FAILED, [], ErrorMsg(ErrorType.NOT_SUPPORTED)
    
    def send_simple_request(self, request, text):
        status = JobStatus.JOB_STATE_FAILED
        if not self.is_initialized():
            return status, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)

        try:
            response = client.chat.completions.create(
                model=request.model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": text},
                ],
                max_tokens=request.generationConfig["maxOutputTokens"],
                temperature=request.generationConfig["temperature"],
                extra_body={
                    "thinking": {
                        "type": "enabled" if request.generationConfig["thinking_config"]["include_thoughts"] else "disabled"
                    }
                }
            )
        except Exception as e:
            return JobStatus.JOB_STATE_FAILED, {}, ErrorMsg(ErrorType.SIMPLE_REQUEST, e)

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
        return JobStatus.JOB_STATE_SUCCEEDED, self.format_response(response_text, prompt_tokens, candidates_tokens, thoughts_tokens, total_tokens), None


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
