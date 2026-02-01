import json
from json_repair import repair_json
from paper_analysis import SimplePaper
from ai_queries import CONTENT_TAG


STRUCTURE = f"""
You are an expert in Requirements Engineering (RE) and Natural Language Processing (NLP).

You will be given a full scientific paper that is assumed to be an OVERVIEW paper 
(e.g., survey, systematic review, mapping study, or guideline).

Your task is to extract and organize the text of the paper into a structured JSON, capturing **every section and paragraph** of the paper. 
**Use the paper's own words exactly as they appear. Do NOT paraphrase, summarize, or rewrite.**

Requirements:

1. Include standard sections such as:
   - Abstract
   - Introduction
   - Background / Related Work
   - Discussion
   - Conclusions

2. Include any non-standard or custom sections as they appear in the paper. Each should become its own JSON key using the section title (lowercase, underscores for spaces). For example, "Methodology" → "methodology", "Future Work" → "future_work".

3. All text must remain exactly as in the original paper. Preserve paragraphs, lists, tables, and formatting as plain text.

4. If a section is missing, the corresponding JSON field should be an empty string "".

5. Output MUST be valid JSON and contain ONLY keys corresponding to section titles.

Paper content:
{CONTENT_TAG}

Output format rules (MANDATORY):

- JSON keys: 
    - "abstract"
    - "introduction"
    - "background" (even in case of related work)
    - "discussion" 
    - "conclusions" 
    - plus any other non-standard sections present in the paper (converted to lowercase with underscores)
- Values: full text of each section as it appears in the paper
- Do NOT include explanations, markdown, or extra text
- Do not modify or shorten the text

Example output format:

{{
  "abstract": "<exact abstract text>",
  "introduction": "<exact introduction text>",
  "background": "<exact background text>",
  "discussion": "<exact discussion text>",
  "conclusions": "<exact conclusions text>",
  "methodology": "<exact methodology text if present>",
  "taxonomy": "<exact taxonomy text if present>",
  "future_work": "<exact future work text if present>"
}}

Now produce the JSON output.
"""


def shape_content(paper: SimplePaper):
    return f"Paper's full text: \n{paper.text}"


def extract(ai_reply: str):
    dict_ = json.loads(repair_json(ai_reply))
    final_dict = {"parts": dict_}
    for part in ["abstract", "introduction", "background", "discussion", "conclusions"]:
        if part in dict_:
            final_dict[part] = dict_[part]
            del dict_[part]
    return final_dict


OPTIONS = {
    "model": "gemini-3-flash-preview",
    "generationConfig": {
        "temperature": 0.0,
        "maxOutputTokens": 30000,
        "thinking_config": {
            "include_thoughts": False,
            "thinking_budget": 0
        }
    }
}
