import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from gen_ai.batch_manager import BatchManager
from gen_ai import models
import json
import time
import dotenv


try:
    bm = BatchManager(
        ip="localhost",
        port=8001,
        db_name="AiRequests",
        username="mongodb",
        password="mongodb",
        space="chat_test",
        api_keys={
            models.gemini: dotenv.get_key(os.path.join(os.path.dirname(__file__), ".env"), "GEMINI"),
            models.deepseek: dotenv.get_key(os.path.join(os.path.dirname(__file__), ".env"), "DEEPSEEK"),
            models.openai: dotenv.get_key(os.path.join(os.path.dirname(__file__), ".env"), "OPENAI"),
        },
        cb_on_complete=lambda request: print(request),
        cb_on_stream=lambda req_id, text: print(text, end="", flush=True)
    )

    # Create an empty chat with basic configuration
    req, error = bm.create_chat(
        model=models.openai.gpt_4_1_mini,
        gen_config={
            "systemPrompt": "You are a clever and concise investigator.",
            "temperature": 0.0,
            "maxOutputTokens": 60,
            "thinking_config": {
                "include_thoughts": False,
                "thinking_budget": 0
            }
        },
        task_id="casual_chat"
    )

    # Create the first message
    chat_request, error = bm.create_chat_message(
        task_id="casual_chat",
        message="Don't you think I am a bit suspicious?",
        stream=True
    )

    # Print cost estimation (eventually, user's prompts is required)
    print(json.dumps(chat_request.estimate_costs(100), indent=2))

    if not error:
        req, error = chat_request.send_request()

    time.sleep(2)

    # Create the second message
    chat_request, error = bm.create_chat_message(
        task_id="casual_chat",
        message="But I know I am not the bad guy!"
    )
    if not error:
        req, error = chat_request.send_request()

    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
except:
    import traceback
    print(traceback.format_exc())
bm.close()