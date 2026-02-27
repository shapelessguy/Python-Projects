from gen_ai.model import Model, JobStatus, RequestStatus, ErrorMsg, ErrorType


class LocalFamily(Model):
    model_info = {
        "batches": False,
        "control_thoughts": False,
        "control_reasoning_temp": False,
        "control_thoughts_tokens": False
    }

    def __init__(self, api_key):
        super().__init__(api_key)
        self.init_err = None
    
    def is_initialized(self):
        return True
    
    def send_batch(self, request):
        if not self.is_initialized():
            return RequestStatus.FAILED, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        super().send_batch(request)
        return RequestStatus.SUCCEEDED, {}
    
    def cancel_batch(self, request):
        return RequestStatus.FAILED, ErrorMsg(ErrorType.BATCH_CANCEL)
    
    def fetch_batch_results(self, request):
        job_status = JobStatus.JOB_STATE_FAILED
        if not self.is_initialized():
            return job_status, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        super().fetch_batch_results(request)

        job_status = JobStatus.JOB_STATE_SUCCEEDED
        responses = [f"OK{i}" for i in range(len(request.contents))]
        prompt_tokens = 0
        total_tokens = 0
        self.add_cost(request, prompt_tokens, total_tokens - prompt_tokens)
        return job_status, [self.format_response(r, 0, 0, 0, 0) for r in responses]
    
    def send_simple_request(self, request, text):
        if not self.is_initialized():
            return RequestStatus.FAILED, {}, ErrorMsg(ErrorType.INITIALIZATION, self.init_err)
        super().send_simple_request(request, text)
        response_text = "Ok it works"
        prompt_tokens = 0
        total_tokens = 0
        self.add_cost(request, prompt_tokens, total_tokens - prompt_tokens)
        return RequestStatus.SUCCEEDED, self.format_response(response_text, 0, 0, 0, 0), None
    
    def stream_request(self, request, text, on_stream_cb):
        return RequestStatus.FAILED, {}, ErrorMsg(ErrorType.NOT_SUPPORTED)


class gemma3(LocalFamily):
    name = "gemma3"
