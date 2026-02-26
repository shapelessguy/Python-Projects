from gen_ai.model import Model, JobStatus, ErrorMsg, ErrorType


class LocalFamily(Model):
    model_info = {
        "batches": False,
        "control_thoughts": False,
        "control_reasoning_temp": False,
        "control_thoughts_tokens": False
    }

    def __init__(self):
        super().__init__()
        self.init_err = None
    
    def is_initialized(self):
        return True
    
    def send_batch(self, request):
        status = JobStatus.JOB_STATE_FAILED
        if not self.is_initialized():
            return status, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        super().send_batch(request)

        status = JobStatus.JOB_STATE_SUCCEEDED
        return status, {}
    
    def cancel_batch(self, request):
        return JobStatus.JOB_STATE_FAILED, ErrorMsg(ErrorType.BATCH_CANCEL)
    
    def fetch_batch_results(self, request):
        status = JobStatus.JOB_STATE_FAILED
        if not self.is_initialized():
            return status, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        super().fetch_batch_results(request)

        status = JobStatus.JOB_STATE_SUCCEEDED
        responses = [f"OK{i}" for i in range(len(request.contents))]
        prompt_tokens = 0
        total_tokens = 0
        self.add_cost(request, prompt_tokens, total_tokens - prompt_tokens)
        return status, [self.format_response(r, 0, 0, 0, 0) for r in responses]
    
    def send_simple_request(self, request, text):
        status = JobStatus.JOB_STATE_FAILED
        if not self.is_initialized():
            return status, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        super().send_simple_request(request, text)

        status = JobStatus.JOB_STATE_SUCCEEDED
        response_text = "Ok it works"
        prompt_tokens = 0
        total_tokens = 0
        self.add_cost(request, prompt_tokens, total_tokens - prompt_tokens)
        return status, self.format_response(response_text, 0, 0, 0, 0), None
    
    def stream_request(self, request, text, on_stream_cb):
        return JobStatus.JOB_STATE_FAILED, {}, ErrorMsg(ErrorType.NOT_SUPPORTED)


class gemma3(LocalFamily):
    name = "gemma3"
