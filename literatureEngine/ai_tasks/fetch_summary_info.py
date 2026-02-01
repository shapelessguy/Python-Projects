import json
from paper_analysis import SimplePaper
from ai_queries import CONTENT_TAG


STRUCTURE = f"""
You are an expert in Requirements Engineering (RE) and Natural Language Processing (NLP).

You will be given a full scientific paper that is assumed to be an OVERVIEW paper
(e.g., survey, systematic review, mapping study, or guideline).

Your task is to extract structured information for an overview paper on:

"Large Language Models (LLMs) in the context of Requirements Engineering (RE),
including tasks such as elicitation, analysis, validation, specification,
management, and traceability."

Paper content:
{CONTENT_TAG}

Instructions:

1. Determine whether the paper is ACTUALLY about Requirements Engineering.
   - Mark false only if RE is not a meaningful focus.

2. Identify the paper's MAIN CONTRIBUTION in 1-2 concise sentences.

3. Classify the paper's coverage across the following RE task taxonomy.
   - Assign a PERCENTAGE to each category.
   - Percentages MUST sum to 100.
   - Use 0 if the category is not covered.

Taxonomy:
- Requirement Generation
- Requirement Analysis
- Requirement Translation
- Requirement Quality Assessment
- Design Derivation

4. Assess the paper's OVERALL ATTITUDE toward the use of LLMs in RE.
   - Use a score from 1 to 10:
     - 1-3: mostly negative / skeptical
     - 4-6: mixed or cautious
     - 7-10: mostly positive / optimistic

5. Provide:
   - A concise SUMMARY of the paper (4-5 sentences).
   - A list of DETAILED, NON-TRIVIAL TAKE-AWAYS about the use of LLMs in
     Requirements Engineering, intended to support synthesis across multiple
     overview papers.
     - Maximum 25 sentences
     - Sentences may be long and detailed
     - Each sentence must express a concrete insight, observation, limitation,
       trend, challenge, opportunity, or research gap
     - Avoid generic or obvious statements (e.g., “LLMs are promising”,
       “LLMs can help RE”)
     - Focus explicitly on how, where, and under which conditions LLMs are used
       in RE tasks

Output format rules (MANDATORY):
- Output MUST be valid JSON
- Output MUST contain ONLY the keys defined below
- Output MUST NOT include explanations, markdown, or extra text

JSON schema:
{{
  "about_requirements_engineering": true or false,
  "main_contribution": "<string>",
  "taxonomy_coverage_percent": {{
    "requirement_generation": <integer>,
    "requirement_analysis": <integer>,
    "requirement_translation": <integer>,
    "requirement_quality_assessment": <integer>,
    "design_derivation": <integer>
  }},
  "llm_positivity_score": <integer from 1 to 10>,
  "paper_summary": "<string>",
  "key_takeaways": [
    "<sentence 1>",
    "<sentence 2>",
    "... up to 25 sentences"
  ]
}}

Now produce the JSON output.
"""


def shape_content(paper: SimplePaper):
    return f"Paper's full text: \n{paper.text}"


def extract(ai_reply: str):
    dict_ = json.loads(ai_reply)
    assert "about_requirements_engineering" in dict_
    assert "main_contribution" in dict_
    assert "taxonomy_coverage_percent" in dict_
    assert "llm_positivity_score" in dict_
    assert "paper_summary" in dict_
    assert "key_takeaways" in dict_
    assert type(dict_["llm_positivity_score"]) == int
    sum = 0
    for p in ["requirement_generation", "requirement_analysis", "requirement_translation",
              "requirement_quality_assessment", "design_derivation"]:
        assert p in dict_["taxonomy_coverage_percent"] and type(dict_["taxonomy_coverage_percent"][p]) == int
        sum += dict_["taxonomy_coverage_percent"][p]
    assert sum == 100 or sum == 0
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
