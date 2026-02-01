import json
from paper_analysis import SimplePaper
from ai_queries import CONTENT_TAG


STRUCTURE = f"""
You are analyzing a single academic paper about the use of LLMs in Requirement Engineering. 
The paper may contribute to multiple RE categories (requirement_generation, requirement_analysis, requirement_ranslation, quality_assessment, design_and_traceability).

Paper content:
{CONTENT_TAG}

For each specified RE category, answer the following questions. Only base your answers on **explicit or clearly implied information** in the paper. Do not guess or hallucinate.

Instructions (one per key):

1. Maturity:
    - 'Conceptual' if the paper explicitly discusses ideas, theories, or concepts for this category without proposing concrete methods;
    - 'Methodological' if the paper explicitly proposes a structured workflow, pipeline, or framework for this category;
    - 'Implemented' if the paper explicitly reports a working tool, prototype, or system for this category;

4. Highest_Artifact_Formality: Choose only one of Text, Structured, or Formal/Exec. This should represent the highest level of artifact actually produced or reported for this category. If none is reported, choose Text.

5. Tooling_Explicit: YES if the paper explicitly mentions concrete tools, platforms, or models used for this category (e.g., GPT-4, BERT, Neo4j, PlantUML, Selenium); otherwise NO.

Return the results in **JSON format** exactly as follows, with one object per RE category:

{{
  "<category_name>": {{
    "Maturity": "Conceptual / Methodological / Implemented"
    "Highest_Artifact_Formality": "Text / Structured / Formal/Exec",
    "Tooling_Explicit": "YES/NO"
  }}
}}

You should include 1 category per paper, maybe more BUT ONLY if the paper really focuses on multiple points.
It is totally fine to leave categories out.
Only include the categories you are explicitly asked to evaluate. Do not add extra text or explanations.


Output format rules (MANDATORY):
- Output MUST be valid JSON
- Output MUST contain ONLY the keys defined above
- Output MUST NOT include explanations, markdown, or extra text

Now produce the JSON output.
"""


def shape_content(paper: SimplePaper):
    return f"Paper's full text: \n{paper.text}\n\nTaxonomy contributions previously gathered:\n{paper.info['taxonomy_contributions']}"


haf = {'Structured', 'Text', 'Formal/Exec'}
mat = {'Conceptual', 'Methodological', 'Implemented'}
normalized_keys = ['generation', 'analysis', 'translation', 'quality_assessment', 'design_and_traceability']
all_stats = {k: [0, 0, 0, 0, 0, 0, 0] for k in normalized_keys}
def extract(ai_reply: str):
    dict_ = json.loads(ai_reply)
    output = {}
    for k in list(dict_.keys()):
        if k not in normalized_keys:
            value = dict_[k]
            del dict_[k]
            k = k.replace("&", "and").replace(" ", "_").lower().replace("design_derivation", "design").replace("requirement_", "")
            dict_[k] = value
    
    props = ['Maturity', 'Tooling_Explicit', 'Highest_Artifact_Formality']
    for k, v in dict_.items():
        if type(v) is dict:
            dict_[k] = {k_: v_ for k_, v_ in v.items() if k_ in props}
            for k1 in list(dict_[k].keys()):
                v1 = dict_[k][k1]
                if v1.lower() == "yes":
                    dict_[k][k1] = 1
                elif v1.lower() == "no":
                    dict_[k][k1] = 0
                elif k1 == "Highest_Artifact_Formality":
                    dict_[k]["haf_structured"] = 1 if (v1 == "Structured") else 0
                    dict_[k]["haf_text"] = 1 if (v1 == "Text") else 0
                    dict_[k]["haf_formal"] = 1 if (v1 == "Formal/Exec") else 0
                    del dict_[k][k1]
                elif k1 == "Maturity":
                    dict_[k]["mat_conc"] = 1 if (v1 == "Conceptual") else 0
                    dict_[k]["mat_met"] = 1 if (v1 == "Methodological") else 0
                    dict_[k]["mat_impl"] = 1 if (v1 == "Implemented") else 0
                    del dict_[k][k1]
            if "haf_structured" not in dict_[k]:
                dict_[k]["haf_structured"] = 0
                dict_[k]["haf_text"] = 0
                dict_[k]["haf_formal"] = 0
            if "mat_conc" not in dict_[k]:
                dict_[k]["mat_conc"] = 0
                dict_[k]["mat_met"] = 0
                dict_[k]["mat_impl"] = 0
            output[k] = dict_[k]
    return {"stats": output}


OPTIONS = {
    "model": "gemini-3-flash-preview",
    "generationConfig": {
        "temperature": 0.0,
        "maxOutputTokens": 1000,
        "thinking_config": {
            "include_thoughts": False,
            "thinking_budget": 0
        }
    }
}
