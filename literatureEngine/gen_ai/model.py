from datetime import datetime, timezone


class RequestStatus:
    FAILED =      'REQUEST_FAILED'
    SUCCEEDED =   'REQUEST_SUCCEEDED'


class JobStatus:
    JOB_STATE_FAILED =      'JOB_STATE_FAILED'
    JOB_STATE_CANCELLED =   'JOB_STATE_CANCELLED'
    JOB_STATE_EXPIRED =     'JOB_STATE_EXPIRED'

    JOB_STATE_SUCCEEDED =   'JOB_STATE_SUCCEEDED'
    JOB_STATE_RUNNING =     'JOB_STATE_RUNNING'
    JOB_STATE_PENDING =     'JOB_STATE_PENDING'
    JOB_STATE_CREATED =     'JOB_STATE_CREATED'

    @classmethod
    def get_all_states(self):
        return tuple(value for name, value in vars(self).items() if name.startswith('JOB_STATE_') and isinstance(value, str))


class ErrorType:
    NO_REQUEST =            "No request to be computed"
    CHAT_NOT_FOUND =        "No chat with requested task_id found"
    INITIALIZATION =        "Model client not initialized"
    BATCH_REQUEST =         "Error on batch request"
    BATCH_CANCEL =          "Error on batch cancellation"
    BATCH_PARSING =         "Error while parsing batch"
    BATCH_NOT_READY =       "Batch not ready yet"
    SIMPLE_REQUEST =        "Error on simple request"
    NOT_SUPPORTED =         "Operation not supported"
    UNKNOWN =               "Unknown error"


class ErrorMsg:
    def __init__(self, error_type: ErrorType, msg: Exception = None):
        self.error_type = error_type
        self.msg = msg

    def __str__(self):
        err_info = f": {type(self.msg).__name__}" if self.msg else ""
        output = f"{self.error_type} {err_info}"
        if self.msg:
            output += f"\n\t" + "\n\t".join(str(self.msg).split("\n"))
        return output


class Model:
    pricing = {"input": 0, "output": 0}

    def __init__(self):
        pass
    
    def is_initialized(self):
        pass
    
    def send_batch(self, request):
        # Returns a dictionary for operational variables that will be saved into the request
        print(f"Batch sent via model family {self.__class__.__name__}")
        pass

    def cancel_batch(self, request):
        print(f"Batch canceled via model family {self.__class__.__name__}")
        pass
    
    def fetch_batch_results(self, request):
        print(f"Batch fetched via model family {self.__class__.__name__}")
        pass
    
    def send_simple_request(self, request, text):
        print(f"Simple request sent via model family {self.__class__.__name__}")
        pass
    
    def stream_request(self, request, text, on_stream_cb):
        print(f"Stream request sent via model family {self.__class__.__name__}")
        pass
    
    def add_cost(self, request, input_tokens, output_tokens):
        req_usd_price = (input_tokens * self.pricing["input"] + output_tokens + self.pricing["output"]) / 10**6
        request.price_usd += req_usd_price
        request.price_eur += (req_usd_price / request.eur_usd_rate)
    
    def format_response(self, text, prompt_tokens, candidates_tokens, thoughts_tokens, total_tokens):
        return {
            "token_info": {
                "prompt_tokens": prompt_tokens,
                "candidates_tokens": candidates_tokens,
                "thoughts_tokens": thoughts_tokens,
                "total_tokens": total_tokens
            },
            "computed_on": datetime.now(timezone.utc),
            "text": text
        }
