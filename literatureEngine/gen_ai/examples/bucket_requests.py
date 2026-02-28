import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from gen_ai.batch_manager import BatchManager, PROFILE_ID_TAG
from gen_ai import models
import time
import dotenv
import json


try:

    # Setup the manager with static information
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
        cb_on_stream=lambda req_id, text: print(req_id, text)
    )

    # Creation of the request's bucket
    request = bm.create_bucket_requests(
        model=models.gemini.gemini_2_5_flash_lite,
        gen_config={
            "temperature": 0.0,
            "maxOutputTokens": 60,
            "thinking_config": {
                "include_thoughts": False,
                "thinking_budget": 0
            }
        },
        task_id="bucket_requests",  # Identifier of the requests' family. Multiple buckets can have the same 'task_id'

        # Prompt structure and profiles work together by generating different atomic requests
        prompt_structure="Tell me something about me: My name is {{INFO.NAME}} I am {{INFO.YEARS}} years old and I live in {{INFO.LOCATION}}.\n",
        profiles=[
            {PROFILE_ID_TAG: 1, "INFO": {"NAME": "Claudio", "YEARS": 32, "LOCATION": "Braunschweig"}},
            {PROFILE_ID_TAG: 2, "INFO": {"NAME": "Johnny Depp", "YEARS": 54, "LOCATION": "Las Vegas"}},
            {PROFILE_ID_TAG: 3, "INFO": {"NAME": "Joe Biden", "YEARS": 81, "LOCATION": "New York"}}
        ],

        batch=False,    # True if the processing is in batch (it might take from 30 minutes to 2-3 days depending on the provider but half price)
        update=False,   # True if profiles of the same task_id that have been previously computed under different configuration, must be updated
    )

    # Print cost estimation (eventually, user's prompts is required)
    print(json.dumps(request.estimate_costs(100), indent=2))

    # Register the request on the manager and seat back on your chair
    req, msg = request.send_request()

    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
except:
    import traceback
    print(traceback.format_exc())
bm.close()