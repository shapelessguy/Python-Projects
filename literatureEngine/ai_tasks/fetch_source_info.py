import json
from paper_analysis import SimplePaper
from ai_queries import CONTENT_TAG


STRUCTURE = f"""
You are an expert in Requirements Engineering (RE) and Natural Language Processing (NLP).

You will be given a SINGLE PRIMARY research paper (not a survey or overview).
The paper may propose a method, framework, experiment, tool, or case study.

Your task is to extract how THIS paper contributes to, supports, refines,
or contradicts the current research landscape on:

"Large Language Models (LLMs) in Requirements Engineering (RE)."

Paper content:
{CONTENT_TAG}

Context:
A prior systematic review of overview papers identified the following
well-established themes in LLMs for Requirements Engineering.

COMMON SIMILARITIES:
- S1: Mandatory human-in-the-loop (HITL) validation
- S2: Dominance of GPT-style, decoder-only proprietary models
- S3: Prompt engineering as the main performance driver
- S4: Effectiveness under data scarcity / cold-start conditions
- S5: Shift of RE role from author to reviewer/orchestrator
- S6: Use of LLMs primarily as decision-support tools

DIVERGENT APPROACHES:
- D1: Large proprietary LLMs vs small/local language models
- D2: Decoder-only generation vs encoder-only analysis models
- D3: Formal RE vs informal/creative RE focus
- D4: End-to-end generative pipelines vs modular tool support
- D5: Automatic metrics vs expert-driven evaluation
- D6: Single-agent prompting vs multi-agent systems

OPEN PROBLEMS AND GAPS:
- G1: Hallucinations and plausibility traps
- G2: Lack of industrial-scale validation
- G3: Privacy, security, and IP concerns
- G4: Context window limitations for large SRS
- G5: Lack of domain-specific tacit knowledge
- G6: Explainability and traceability deficits
- G7: Limited support for non-functional requirements
- G8: Prompt fragility and reproducibility issues


Instructions:

1. Determine whether the paper is ACTUALLY about Requirements Engineering.
   - Mark false only if RE is not a meaningful focus.

2. Identify the paper's MAIN CONTRIBUTION in 1-2 precise sentences,
   focusing on what is novel or distinctive compared to prior work.

3. For EACH category in the RE taxonomy:
   - Indicate whether the paper makes a contribution.
   - If yes, explain HOW it contributes and WHAT it adds beyond existing knowledge.
   - Do NOT restate generic capabilities; be specific to the paper.

4. Identify which of the previously observed:
   - Similarities
   - Divergent approaches
   - Problems or research gaps
   this paper explicitly addresses, mitigates, exposes, or reinforces.
   - If the paper introduces a NEW issue not covered before, include it.

5. Assess the paper's OVERALL ATTITUDE toward the use of LLMs in RE.
   - Use a score from 1 to 10:
     - 1-3: mostly critical or negative
     - 4-6: mixed / cautious
     - 7-10: mostly positive or optimistic

6. Provide:
   - A concise SUMMARY of the paper (3-4 sentences).
   - A list of NON-TRIVIAL, PAPER-SPECIFIC TAKE-AWAYS about LLM usage in RE.
     - Maximum 15 sentences
     - Sentences may be detailed
     - Each sentence must reflect evidence, design choices, empirical findings,
       limitations, or implications introduced by THIS paper
     - Avoid restating high-level trends unless the paper adds nuance or evidence

Output format rules (MANDATORY):
- Output MUST be valid JSON
- Output MUST contain ONLY the keys defined below
- Output MUST NOT include explanations, markdown, or extra text

JSON schema:
{{
  "about_requirements_engineering": true or false,
  "main_contribution": "<string>",
  "taxonomy_contributions": {{
    "requirement_generation": "<none | brief description>",
    "requirement_analysis": "<none | brief description>",
    "requirement_translation": "<none | brief description>",
    "requirement_quality_assessment": "<none | brief description>",
    "design_derivation_and_traceability": "<none | brief description>"
  }},
  "relations_to_existing_landscape": {{
    "reinforces_existing_findings": ["<point>", "..."],
    "diverges_from_existing_approaches": ["<point>", "..."],
    "addresses_known_gaps": ["<gap>", "..."],
    "introduces_new_issues": ["<issue>", "..."]
  }},
  "llm_positivity_score": <integer from 1 to 10>,
  "paper_summary": "<string>",
  "paper_specific_takeaways": [
    "<sentence 1>",
    "<sentence 2>",
    "... up to 15 sentences"
  ]
}}

Now produce the JSON output.
"""



def shape_content(paper: SimplePaper):
    return f"{paper.text}"


def extract(ai_reply: str):
    dict_ = json.loads(ai_reply)
    assert "about_requirements_engineering" in dict_
    assert "main_contribution" in dict_
    assert "taxonomy_contributions" in dict_
    assert "llm_positivity_score" in dict_
    assert "paper_summary" in dict_
    assert "paper_specific_takeaways" in dict_
    return dict_


OPTIONS = {
    "model": "gemini-3-flash-preview",
    "generationConfig": {
        "temperature": 0.0,
        "maxOutputTokens": 3000,
        "thinking_config": {
            "include_thoughts": False,
            "thinking_budget": 0
        }
    }
}
