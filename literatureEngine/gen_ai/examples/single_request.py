import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from gen_ai.batch_manager import BatchManager
from gen_ai import models
import time
import dotenv
import json


try:

    # Setup the manager with static information
    bm = BatchManager(
        # Database related settings
        ip="localhost",
        port=8001,
        db_name="AiRequests",
        username="mongodb",
        password="mongodb",
        space="chat_test",

        # Responses's interaction related settings
        api_keys={
            models.gemini: dotenv.get_key(os.path.join(os.path.dirname(__file__), ".env"), "GEMINI"),
            models.deepseek: dotenv.get_key(os.path.join(os.path.dirname(__file__), ".env"), "DEEPSEEK"),
            models.openai: dotenv.get_key(os.path.join(os.path.dirname(__file__), ".env"), "OPENAI"),
        },
        cb_on_complete=lambda request: print(request)
    )

    # Creation of the request's bucket
    request = bm.create_single_request(
        model=models.openai.gpt_4o_mini,
        gen_config={
            "temperature": 0.0,
            "maxOutputTokens": 60,
            "thinking_config": {
                "include_thoughts": False,
                "thinking_budget": 0
            }
        },
        task_id="single_request",  # Identifier of the requests' family. Multiple buckets can have the same 'task_id'

        # You can use a simple string, or a dictionary of values together with an adequate prompt_structure
        message="Hi, how are you?",

        update=False,   # True if profiles of the same task_id that have been previously computed under different configuration, must be updated
    )

    # Print cost estimation (eventually, user's prompts is required)
    print(json.dumps(request.estimate_costs(100), indent=2))

    # Register the request on the manager
    req, msg = request.send_request()

    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
except:
    import traceback
    print(traceback.format_exc())
bm.close()