import json
from paper_analysis import SimplePaper
from ai_queries import CONTENT_TAG


STRUCTURE = f"""
You are an expert in Requirements Engineering (RE).

You will be given a full scientific paper that is assumed to be an OVERVIEW paper
(e.g., survey, systematic review, mapping study, or guideline).

Your task is to extract structured information for an overview paper on:

"Current issues on requirement engineering tasks"

Paper content:
{CONTENT_TAG}

Instructions:

1. Identify and list the most relevant challenges in Requirements Engineering as reported by the research community.
   - Each challenge must be explicitly grounded in the paper content.
   - Focus on challenges that are recognized as open, persistent, or insufficiently solved.
   - Avoid restating general background; prioritize issues discussed as limitations, gaps, or research directions.

   
Output format rules (MANDATORY):
- Output MUST be valid JSON
- Output MUST contain ONLY the keys defined below
- Output MUST NOT include explanations, markdown, or extra text

JSON schema:
{{
  "about_requirements_engineering": true or false,
  "main_contribution": "<string>",
  "relevant_challenges": [
    <list of relevant challenges here>
  ]
}}

Now produce the JSON output.
"""


def shape_content(paper: SimplePaper):
    return f"Paper's full text: \n{paper.text}"


def extract(ai_reply: str):
    dict_ = json.loads(ai_reply)
    assert "relevant_challenges" in dict_
    return dict_


OPTIONS = {
    "model": "gemini-3-flash-preview",
    "generationConfig": {
        "temperature": 0.0,
        "maxOutputTokens": 1700,
        "thinking_config": {
            "include_thoughts": False,
            "thinking_budget": 0
        }
    }
}
