from gen_ai.batch_manager import BatchManager, Request
from gen_ai import models
from bson import ObjectId
import time
import dotenv
import os
import json


bm = BatchManager(
    ip="localhost",
    port=8001,
    db_name="AiRequests",
    username="mongodb",
    password="mongodb",
    # space="ai_test"
)
bm.set_api_keys({
    models.gemini: dotenv.get_key(".env", "GEMINI"),
    models.deepseek: dotenv.get_key(".env", "DEEPSEEK"),
    models.openai: dotenv.get_key(".env", "OPENAI"),
})
bm.set_space("ai_test")


request = Request(
    model=models.gemini.gemini_2_5_flash_lite,
    # model=models.openai.gpt_4_1_mini,
    # model=models.openai.gpt_4_1_nano,
    generationConfig={
        "systemPrompt": "You are an expert and you have to answers concisely.",
        "temperature": 0.0,
        "maxOutputTokens": 25,
        "thinking_config": {
            "include_thoughts": False,
            "thinking_budget": 0
        }
    },
    task_id=ObjectId("c075d7eda2fa9d0b6dc83376"),
    prompt_structure="Tell me something about me: My name is {{NAME}} I am {{YEARS}} years old and I live in {{LOCATION}}",
    text_variables=[
        {"NAME": "Clauddifdof", "YEARS": "32", "LOCATION": "Braunschweig"},
        {"NAME": "Marddaf", "YEARS": "30", "LOCATION": "Braunschweig"},
        {"NAME": "ShitddtfyPupphy", "YEARS": "2", "LOCATION": "FUCKland"},
        {"NAME": "ShitdtyfPdupphy", "YEARS": "2", "LOCATION": "FUCKland"},
    ],
    chat=False,
    stream=False,
    batch=True,
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
# request, msg = request.send_chat(task_id=request.task_id, content_vars={"NAME": "Claudio", "YEARS": "32", "LOCATION": "Braunschweig"}, stream=True)
print(msg)

# bm.send_batch_cancellation(ObjectId("699f3e179087600c0630e1b0"))


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