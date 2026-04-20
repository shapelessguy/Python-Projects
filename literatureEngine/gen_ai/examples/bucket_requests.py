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
    request = bm.create_bucket_requests(
        model=models.openai.gpt_4o_mini,
        gen_config={
            "temperature": 0.0,
            "maxOutputTokens": 60,
            "thinking_config": {
                "include_thoughts": False,
                "thinking_budget": 0
            }
        },
        task_id="bucket_requests3",  # Identifier of the requests' family. Multiple buckets can have the same 'task_id'

        # Prompt structure and profiles work together by generating different atomic requests
        prompt_structure="Tell me something about me: My name is {{NAME.first}} I am {{YEARS}} years old and I live in {{LOCATION}}.\n",
        profiles={
            "custom_tag":   {"NAME": {"first": "Claudio", "family": "Ciano"}, "YEARS": 32, "LOCATION": "Braunschweig"},
            2:              {"NAME": "Johnny Depp", "YEARS": 54, "LOCATION": "Las Vegas"},
            3:              {"NAME": "Joe Biden", "YEARS": 81, "LOCATION": "New York"}
        },

        batch=True,    # True if the processing is in batch (it might take from 30 minutes to 2-3 days depending on the provider but half price)
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