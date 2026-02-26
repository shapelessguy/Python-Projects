from gen_ai.batch_manager import BatchManager, Request
from gen_ai import models
from bson import ObjectId
import time
import json

bm = BatchManager(
    ip="localhost",
    port=8001,
    username="mongodb",
    password="mongodb",
    db_name="AiRequests",
    collection_name="ai_test"
)

print(json.dumps(bm.get_consumption(), indent=2))

request = Request(
    # model=models.gemini.gemini_2_5_flash_lite,
    # model=models.openai.gpt_4_1_mini,
    model=models.gemini.gemini_2_5_flash_lite,
    generationConfig={
        "systemPrompt": "You are an expert and you have to answers concisely.",
        "temperature": 0.0,
        "maxOutputTokens": 25,
        "thinking_config": {
            "include_thoughts": False,
            "thinking_budget": 0
        }
    },
    task_id=ObjectId("c075d8eda2fa9d0b4dc73376"),
    prompt_structure="Tell me something about me: My name is {{NAME}} I am {{YEARS}} years old and I live in {{LOCATION}}",
    text_variables=[
        {"NAME": "Claudio", "YEARS": "32", "LOCATION": "Braunschweig"},
        {"NAME": "Mara", "YEARS": "30", "LOCATION": "Braunschweig"},
        {"NAME": "ShittyPuppy", "YEARS": "2", "LOCATION": "FUCKland"},
    ],
    chat=False,
    stream=False,
    batch=False,
    update=False,
)

request.get_directives(bm)
expected_request_info = request.estimate_costs()
print(json.dumps(expected_request_info, indent=2))

def on_complete(request: Request):
    print(request)

def on_stream(request_id, text):
    print(request_id, text)

bm.register_on_complete_callback(on_complete)
bm.register_on_stream_callback(on_stream)
request, msg = request.send_request()

# bm.send_cancellation(ObjectId("699f3e179087600c0630e1b0"))


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