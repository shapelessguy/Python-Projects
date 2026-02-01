from ai_queries import execute_simple_request


REQUEST = """
Tell me a joke
"""


options = {
    "model": "gemini-2.5-flash-lite",
    "generationConfig": {
        "temperature": 0.0,
        "maxOutputTokens": 30,
        "thinking_config": {
            "include_thoughts": False,
            "thinking_budget": 0
        }
    }
}


execute_simple_request("simple_requests", options, REQUEST, instant=True)
