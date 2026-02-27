from gen_ai.batch_manager import BatchManager, Request
from gen_ai import models
from bson import ObjectId
import time
import dotenv
import os
import json


try:
    bm = BatchManager(
        ip="localhost",
        port=8001,
        db_name="AiRequests",
        username="mongodb",
        password="mongodb",
        space="ai_test"
    )
    bm.set_api_keys({
        models.gemini: dotenv.get_key(".env", "GEMINI"),
        models.deepseek: dotenv.get_key(".env", "DEEPSEEK"),
        models.openai: dotenv.get_key(".env", "OPENAI"),
    })
    print(bm.get_active_api_keys())

    def on_complete(request: Request):
        print(request)

    def on_stream(request_id, text):
        print(request_id, text)

    bm.register_on_complete_callback(on_complete)
    bm.register_on_stream_callback(on_stream)

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
        task_id=ObjectId("c075d7eda2fa9b0b6dc83376"),
        prompt_structure="Tell me something about me: My name is {{NAME}} I am {{YEARS}} years old and I live in {{LOCATION}}",
        text_variables=[
            # "Ciao tell me something"
        ],
        chat=True,
        stream=False,
        batch=False,
        update=False,
    )

    # request.get_directives(bm)
    # print(json.dumps(request.estimate_costs(100), indent=2))

    # req, msg = request.send_request()

    chat_request = Request(
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
        task_id=ObjectId("c075d7eda2fa9b0b6dc83376"),
        chat=True,
        stream=True,
    )
    # chat_request.get_directives(bm)
    # chat_request.send_request()
    req, msg = bm.send_chat(task_id=ObjectId("c075d7eda2fa9b0b6dc83376"), content_vars="Try to gues it", stream=True)
    print(req, msg)

    # time.sleep(5)

    # result = bm.cancel_request(ObjectId("69a1db6325dabc073b1ad036"))
    # print(result)

    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
except:
    import traceback
    print(traceback.format_exc())
bm.close()