import json
from paper_analysis import SimplePaper
from ai_queries import CONTENT_TAG


STRUCTURE = f"""
You are analyzing a single academic paper about the use of LLMs in Requirement Engineering. 
The paper may contribute to multiple RE categories (requirement_generation, requirement_analysis, requirement_ranslation, quality_assessment, design_and_traceability).

Paper content:
{CONTENT_TAG}


This is the current taxonomy you should look at:

Requirement Generation: producing new requirement artifacts or refining informal inputs; subtasks include generating from stakeholder descriptions, reformulating vague statements, creating user stories, acceptance criteria, or test cases, with a few studies reporting interactive elicitation via structured dialogues. Most studies employ decoder-only LLMs in prompt-driven pipelines, while iterative refinement or multi-agent strategies appear less frequently. Outputs are generally human-readable and aligned with agile practices.
Requirement Analysis: extracting, structuring, and interpreting information from existing requirements; subtasks include classification, traceability link recovery, impact analysis, knowledge extraction, and semantic clustering, with some studies analyzing informal sources such as user feedback or regulatory documents. Both encoder-only and decoder-only models are reported, often combined with RAG and HITL validation to ensure accuracy and completeness. Outputs commonly include categorized requirements, traceability matrices, or knowledge representations.
Requirement Quality Assessment: detecting errors, inconsistencies, or gaps in requirements; subtasks include identifying ambiguity, incompleteness, conflicts, or regulatory non-compliance. Decoder-only LLMs handle reasoning-intensive tasks, while encoder-only models address classification-oriented analyses. Zero/few-shot prompting, iterative refinement, HITL, and RAG are commonly used to ensure reliable outputs. Outputs are often aligned with standards such as INVEST or ISO 29148.
Requirement Translation: converting requirements between representations or languages while preserving their original intent and scope; subtasks include translating natural language to controlled language or formal requirement-level specifications (e.g., structured templates, LTL, or requirement-focused UML/SysML views) and normalizing phrasing. Decoder-only models are predominant, though encoder-decoder architectures are used for sequence-to-sequence transformations. Compliance and correctness are often supported via prompt engineering, iterative refinement, or external verification tools.
Design Derivation: unlike translation, which preserves requirements within the problem space, design derivation moves into the solution space by introducing explicit design decisions; subtasks include deriving component structures, interaction behaviors, data models, or architectural configurations that operationalize requirements and support downstream implementation. Although UML or SysML notations may be used, the generated artifacts go beyond requirement-level representations by encoding design commitments (e.g., component boundaries, control flows, interfaces, or deployment assumptions). Studies predominantly report decoder-only LLMs, often using few-shot or iterative prompting, with occasional multi-agent frameworks to decompose requirements into structural and behavioral elements. HITL validation is commonly employed to ensure correctness, structural validity, and alignment with engineering constraints, while retrieval-augmented or multimodal inputs are sometimes used to handle complex or multi-source specifications.

Remember that this taxonomy is related to the usage of LLMs on these domains. If the paper talks about for example about NLP or Doors we don't care.
We care only if it is about LLMs.
For each specified RE category, answer the following questions. Only base your answers on **explicit or clearly implied information** in the paper. Do not guess or hallucinate.

Instructions:

1. Maturity:
    - 'Conceptual' if the paper explicitly discusses ideas, theories, or concepts for this category without proposing concrete methods;
    - 'Methodological' if the paper explicitly proposes a structured workflow, pipeline, or framework for this category;
    - 'Implemented' if the paper explicitly reports a working tool, prototype, or system for this category;
    - For each category, also provide a 2–3 sentence explanation of why you selected this maturity label based on the paper content.

2. Highest_Artifact_Formality:
    - Choose only one of Text, Structured, or Formal/Exec. This should represent the highest level of artifact actually produced or reported for this category;
    - For each category, also provide a 2–3 sentence explanation of why you chose this artifact formality level.

Return the results in **JSON format** exactly as follows, with one object per RE category:

{{
  "<category_name>": {{
    "Maturity": {{
        "Label": "Conceptual / Methodological / Implemented",
        "Explanation": "3–4 sentence explanation of why this label was chosen"
    }},
    "Highest_Artifact_Formality": {{
        "Label": "Text / Structured / Formal/Exec",
        "Explanation": "3–4 sentence explanation of why this level was chosen"
    }}
  }}
}}

You should include 1 category per paper, maximum 2 BUT ONLY if the paper really focuses on multiple points.
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
normalized_keys = ['generation', 'analysis', 'translation', 'quality_assessment', 'design_derivation']
all_stats = {k: [0, 0, 0, 0, 0, 0, 0] for k in normalized_keys}
def extract(ai_reply: str):
    dict_ = json.loads(ai_reply)
    output = {}
    for k in list(dict_.keys()):
        if k not in normalized_keys:
            value = dict_[k]
            del dict_[k]
            k = k.replace("&", "and").replace(" ", "_").lower().replace("requirement_", "")
            dict_[k] = value
    
    for k in normalized_keys:
        if k in dict_:
            maturity = dict_[k]["Maturity"]
            formality = dict_[k]["Highest_Artifact_Formality"]
            for el in [maturity, formality]:
                if "Label_Explanation" in el:
                    el["Explanation"] = el["Label_Explanation"]
                    del el["Label_Explanation"]
            output[k] = {"maturity": maturity, "formality": formality}
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
