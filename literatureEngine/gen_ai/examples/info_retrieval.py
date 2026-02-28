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
        models.gemini: dotenv.get_key(os.path.join(os.path.dirname(__file__), ".env"), "GEMINI"),
        models.deepseek: dotenv.get_key(os.path.join(os.path.dirname(__file__), ".env"), "DEEPSEEK"),
        models.openai: dotenv.get_key(os.path.join(os.path.dirname(__file__), ".env"), "OPENAI"),
    })

    active_keys = bm.get_active_api_keys()
    print(active_keys)

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