import json
from json_repair import repair_json
from paper_analysis import SimplePaper
from ai_queries import CONTENT_TAG


STRUCTURE = f"""
You are an expert researcher in Requirements Engineering and AI-based software engineering that replies only via structured json.

You are given the full text (or structured summary) of ONE research paper.

Your task is to IDENTIFY whether this paper IMPLEMENTS and EVALUATES
any of the following FIXED subtasks.
You must be strict: if a subtask is not clearly implemented and evaluated,
it MUST NOT be reported.

Paper content:
{CONTENT_TAG}

────────────────────────────────────────
FIXED TAXONOMY AND SUBTASKS
────────────────────────────────────────

### 1. Requirement Generation
Subtasks:
- Generating requirements from stakeholder input, user reviews, or existing specifications
- Reformulating ambiguous or informal requirements into precise text
- Producing templates or reusable requirement patterns
- Creating scenarios, user stories, or acceptance criteria
- Generating test cases or code directly from requirements
- Interactive elicitation (guiding stakeholders to create new requirements)

### 2. Requirement Analysis
Subtasks:
- Requirement classification (categorization)
- Traceability and link detection (requirement ↔ requirement, requirement ↔ design/test)
- Impact analysis / change propagation
- Knowledge extraction (entities, relations, ontology population)
- Semantic clustering or dependency analysis
- Glossary or terminology extraction

### 3. Requirement Translation
Subtasks:
- Natural language ↔ controlled natural language
- Natural language ↔ formal specifications (e.g., LTL, UML/SysML, OCL)
- Cross-language translation (e.g., English ↔ French)
- Standardization or normalization of requirement phrasing

### 4. Requirement Quality Assessment
Subtasks:
- Ambiguity detection
- Completeness / coverage checking
- Redundancy detection
- Conflict or inconsistency detection
- Detection of non-testable or unverifiable requirements
- Compliance with templates, standards, or quality frameworks
- Semantic similarity detection for conflict or redundancy identification

### 5. Design Derivation
Subtasks:
- Generation of functional or component-level architecture
- Interface or interaction design generation
- Allocation of requirements to system components
- Generation of alternative design solutions or trade-off analysis
- Model-Based Systems Engineering (MBSE) artifact generation

────────────────────────────────────────
STEP 1 — SUBTASK SELECTION (INTERNAL)
────────────────────────────────────────

From the list above:
- Select AT MOST TWO (2) subtasks total
- Select ZERO (0) if no subtask is clearly implemented and evaluated
- Do NOT select subtasks mentioned only as motivation, discussion, or future work

If more than two subtasks seem applicable, select ONLY the TWO
that represent the paper's MAIN technical contributions.

────────────────────────────────────────
STEP 2 — CONTRIBUTION EXTRACTION
────────────────────────────────────────

For EACH selected subtask, extract ONLY factual information explicitly stated in the paper.
If any field is not specified in the paper, use "not specified" or null.

Do NOT infer missing details.
Do NOT generalize.
Do NOT merge subtasks.

────────────────────────────────────────
OUTPUT FORMAT (STRICT — NO EXCEPTIONS)
────────────────────────────────────────

- Output MUST be valid JSON
- Output MUST contain EXACTLY ONE top-level key: "paper_contributions"
- "paper_contributions" MUST be a JSON array
- Each array element MUST follow the schema below EXACTLY
- If NO subtasks are selected, return:

{{
  "paper_contributions": []
}}

SCHEMA FOR EACH CONTRIBUTION:

{{
  "taxonomy_category": "",
  "subtask": "",
  "contribution_summary": "",
  "technique": "",
  "model_used": "",
  "learning_paradigm": "",
  "prompting_strategy": "",
  "augmentation": "",
  "evaluation_method": "",
  "evaluation_metrics": [
    {{
      "metric_name": "",
      "metric_value": null
    }}
  ]
}}

Do NOT add, remove, or rename keys.
Do NOT output explanations or text outside the JSON.
Now produce the JSON output.
"""


def shape_content(paper: SimplePaper):
    return f"{paper.text}"


def extract(ai_reply: str):
    try:
      dict_ = json.loads(repair_json(ai_reply))
    except:
      print("Cannot parse this dictionary: invalid json")
      return None
    if type(dict_) == dict:
      if not "paper_contributions" in dict_:
        print("Cannot parse this dictionary: missing paper contributions key")
        return None
      for d in dict_["paper_contributions"]:
        assert "taxonomy_category" in d
        assert "subtask" in d
        assert "contribution_summary" in d
        assert "technique" in d
        assert "model_used" in d
        assert "learning_paradigm" in d
        assert "prompting_strategy" in d
        assert "evaluation_method" in d
        assert "evaluation_metrics" in d
    else:
        print("Cannot parse this dictionary: not a dictionary")
        return None
    return dict_


OPTIONS = {
    "model": "gemini-3-flash-preview",
    "generationConfig": {
        "temperature": 0.5,
        "maxOutputTokens": 4500,
        "thinking_config": {
            "include_thoughts": True,
            "thinking_budget": 1500
        }
    }
}
