from paper_analysis import SimplePaper
from ai_queries import CONTENT_TAG


STRUCTURE = f"""
You are an expert in Requirements Engineering.

You will be given ONLY the title and abstract of a scientific paper.
Your task is to assess its relevance for an overview/survey paper about:

"Current state of Requirement Engineering. Challenges and lessons learned"

Paper content:
{CONTENT_TAG}

Instructions:
- Consider the paper RELEVANT only if it explicitly concerns Requirements Engineering.
- If unsure, be conservative and mark it as low relevance.
- A paper is an OVERVIEW only if it is a survey, review, systematic study, or guideline.

Output format rules (MANDATORY):
- Output MUST be valid JSON
- Output MUST contain ONLY the following keys
- Output MUST NOT contain explanations, markdown, or extra text

JSON schema:
{{
  "relevance": <integer from 1 to 10>,
  "is_overview": "YES" or "NO"
}}

Scoring guidelines for "relevance":
- 1-2: Completely unrelated
- 3-4: Mentions to RE but irrelevant for the topic
- 5-6: Indirect or partial relevance to RE
- 7-8: Clearly relevant to RE
- 9-10: Central focus on Requirements Engineering challenges

Now produce the JSON output.
"""


def shape_content(paper: SimplePaper):
    return f"Paper's title: {paper.title.strip()}\n\nAbstract: {paper.abstract.strip()}"


def extract(ai_reply: str):
    lines = ai_reply.split("\n")
    relevance, overview = 0, False
    for line in lines:
        if "relevance" in line:
            relevance = int(line.split('"relevance": ')[1].replace(",", "").strip())
        if "overview" in line:
            overview = "yes" in line.lower()
    return {"relevance": relevance, "is_overview": overview}


OPTIONS = {
    "model": "gemini-3-flash-preview",
    "generationConfig": {
        "temperature": 0.0,
        "maxOutputTokens": 30,
        "thinking_config": {
            "include_thoughts": False,
            "thinking_budget": 0
        }
    }
}
