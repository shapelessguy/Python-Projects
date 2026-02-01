import json
from json_repair import repair_json
from paper_analysis import SimplePaper
from ai_queries import CONTENT_TAG


STRUCTURE = f"""
You are an expert researcher in Requirements Engineering and AI-based software engineering that replies only via structured json.

You are given the full text (or structured summary) of ONE OVERVIEW paper
(e.g., survey, systematic review, mapping study, or guideline).

Your task is to EXTRACT how this overview paper REPORTS, ORGANIZES, or DISCUSSES
the literature with respect to the FIXED LLM-based Requirements Engineering taxonomy below.

You must NOT invent results.
You must NOT infer coverage that is not explicitly stated.
If the paper does not mention a category or subtask, leave the corresponding fields empty or null.

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
FOR EACH TAXONOMY CATEGORY
────────────────────────────────────────

Check whether the overview paper explicitly does any of the following:
- Reports the number or proportion of primary studies
- Discusses trends, maturity, or evolution
- Identifies challenges, limitations, or open problems
- Compares techniques or approaches
- Expresses qualitative judgments (e.g., promising, immature, underexplored)

If a category is NOT discussed, report it with empty fields.

Do NOT reinterpret the taxonomy.
Do NOT force alignment if the paper uses different labels.
Only map content when the correspondence is explicit.

────────────────────────────────────────
OUTPUT FORMAT (STRICT — NO EXCEPTIONS)
────────────────────────────────────────

- Output MUST be valid JSON
- Output MUST contain EXACTLY ONE top-level key: "taxonomy_overview"
- Output MUST contain ALL FIVE taxonomy categories
- Do NOT add explanations or text outside the JSON

JSON SCHEMA:

{{
  "taxonomy_overview": {{
    "Requirement Generation": {{
      "mentioned": <true | false>,
      "number_of_papers": <integer or null>,
      "covered_subtasks": ["<subtask name>", "..."],
      "reported_techniques": ["<technique>", "..."],
      "reported_models": ["<model name>", "..."],
      "key_observations": "<summary of what the overview paper states>",
      "reported_challenges_or_gaps": "<as stated in the paper>"
    }},
    "Requirement Analysis": {{
      "mentioned": <true | false>,
      "number_of_papers": <integer or null>,
      "covered_subtasks": [],
      "reported_techniques": [],
      "reported_models": [],
      "key_observations": "",
      "reported_challenges_or_gaps": ""
    }},
    "Requirement Translation": {{
      "mentioned": <true | false>,
      "number_of_papers": <integer or null>,
      "covered_subtasks": [],
      "reported_techniques": [],
      "reported_models": [],
      "key_observations": "",
      "reported_challenges_or_gaps": ""
    }},
    "Requirement Quality Assessment": {{
      "mentioned": <true | false>,
      "number_of_papers": <integer or null>,
      "covered_subtasks": [],
      "reported_techniques": [],
      "reported_models": [],
      "key_observations": "",
      "reported_challenges_or_gaps": ""
    }},
    "Design Derivation": {{
      "mentioned": <true | false>,
      "number_of_papers": <integer or null>,
      "covered_subtasks": [],
      "reported_techniques": [],
      "reported_models": [],
      "key_observations": "",
      "reported_challenges_or_gaps": ""
    }}
  }}
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
      if type(dict_) != dict:
         raise
    except:
       return None
    return dict_


OPTIONS = {
    "model": "gemini-3-flash-preview",
    "generationConfig": {
        "temperature": 0.0,
        "maxOutputTokens": 10000,
        "thinking_config": {
            "include_thoughts": True,
            "thinking_budget": 1500
        }
    }
}
