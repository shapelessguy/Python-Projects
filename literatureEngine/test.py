from gen_ai.batch_manager import BatchManager, Request
from gen_ai.models import ModelClass


bm = BatchManager("localhost", 8001, "mongodb", "mongodb", "LiteratureReview", "ai_test")

request = Request(
    model_class=ModelClass.GEMINI,
    model_name="gemini-3-flash-preview",
    generationConfig={
        "temperature": 0.0,
        "maxOutputTokens": 10000,
        "thinking_config": {
            "include_thoughts": True,
            "thinking_budget": 1500
        }
    },
    task_id="fetch_overview_methodologies",
    prompt_structure="You are an expert researcher and you have to answer: __X__",
    req_content_list=["Who am I?", "How old are you?"],
    instant=True
)


# Prompt user to some actions here
directives = bm.get_directives(request)
print(directives)

# Show user a preview of the request
adj_request = bm.request_preview(directives, update=True)

bm.send_request(directives, adj_request)