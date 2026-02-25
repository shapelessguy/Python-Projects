from gen_ai.batch_manager import BatchManager, Request
from gen_ai import models

bm = BatchManager(ip="localhost", port=8001, username="mongodb", password="mongodb", db_name="AiRequests", collection_name="ai_test")

request = Request(
    model=models.gemini.gemini_2_5_flash,
    generationConfig={
        "temperature": 0.0,
        "maxOutputTokens": 10,
        "thinking_config": {
            "include_thoughts": False,
            "thinking_budget": 0
        }
    },
    task_id="fetch_overview_methodologiesssss",
    prompt_structure="You are an expert researcher and you have to answers: __X__",
    req_content_list=[f"Who am I??? {i}" for i in range(20)],
    batch=False,
    update=True,
)
import time
import json


# Prompt user to some actions here
directives = bm.get_directives(request)
expected_request_info = directives.estimate_costs(expected_output_tokens_per_request=10)
print(json.dumps(expected_request_info, indent=2))
msg = bm.send_request(directives)

# time.sleep(1)
# bm.cancel_instant_requests()


try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
except:
    import traceback
    print(traceback.format_exc())
print("Closing")
bm.close()