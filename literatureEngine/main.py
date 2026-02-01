from ai_queries import CONTENT_TAG
from paper_analysis import Papers


QUERIES = [
    # Core: LLMs / Generative AI + Requirements Engineering
    '''(LLM | "large language model" | "foundation model" | "generative AI" | "transformer model")
        +("requirements engineering" | "requirement engineering" | requirements | specification | "software requirements")''',

    # Specific LLM families (captures GPT/BERT-style papers)
    '''(GPT | BERT | T5 | LLaMA | PaLM | FLAN)
        +("requirements engineering" | requirements)''',

    # General AI / ML applied to Requirements Engineering (broad recall)
    '''("artificial intelligence" | AI | "machine learning" | "deep learning")
        +("requirements engineering" | requirements | specification)''',

    # NLP-based approaches to Requirements Engineering
    '''("natural language processing" | NLP)
        +("requirements engineering" | requirements)''',

    # Requirements elicitation supported by AI/LLMs
    '''(AI | LLM | NLP)
        +("requirements elicitation" | elicitation)''',

    # Requirements analysis using AI
    '''(AI | LLM | NLP)
        +("requirements analysis")''',

    # Validation and verification of requirements using AI
    '''(AI | LLM | NLP)
        +("requirements validation" | "requirements verification")''',

    # Quality, ambiguity, and inconsistency detection in requirements
    '''(AI | LLM | NLP)
        +("requirements quality" | ambiguity | inconsistency)''',

    # Automation and AI-assisted requirements engineering
    '''(AI | LLM | "generative AI")
        +("requirements automation" | "automated requirements" | "AI-assisted requirements")''',

    # Chatbots and conversational agents for requirements engineering
    '''(chatbot | assistant)
        +("requirements engineering" | requirements)''',

    # Prompt engineering applied to requirements tasks
    '''("prompt engineering")
        +(requirements | "requirements engineering")''',

    # Text mining and semantic analysis of requirements documents
    '''("text mining" | "information extraction" | "semantic analysis")
        +("requirements documents" | "requirements specification")''',

    # Requirements mining and extraction using AI
    '''("requirements mining" | "requirements extraction")
        +(AI | NLP | LLM)''',

    # Requirements traceability supported by AI
    '''(AI | LLM | NLP)
        +("requirements traceability")''',

    # Change impact analysis and requirements evolution
    '''(AI | LLM)
        +("change impact analysis" | "requirements evolution")''',

    # Requirements prioritization using AI techniques
    '''(AI | LLM)
        +("requirements prioritization")''',

    # Software engineering + AI + requirements (captures non-RE-labeled papers)
    '''("software engineering")
        +(AI | "machine learning" | LLM | NLP)
        +(requirements)''',

    # Surveys and systematic literature reviews
    '''(survey | review | "systematic literature review" | SLR)
        +(AI | LLM)
        +(requirements)''',

    # Empirical and industrial case studies
    '''("empirical study" | "case study")
        +(AI | LLM)
        +("requirements engineering")''',

    # Pre-LLM AI foundations in requirements engineering
    '''("knowledge-based systems" | "expert systems")
        +("requirements engineering")''',

    # Ontology- and rule-based approaches to requirements
    '''("rule-based" | "ontology-based")
        +(requirements)''',

    # Ultra-broad net: AI + requirements (use once, then filter heavily)
    '''(AI | "artificial intelligence" | "machine learning" | "natural language processing" | LLM | "generative AI")
        +(requirements | "requirements engineering" | specification)'''

    # RE artifacts and representations
    '''(AI | LLM | NLP)
        +("user stories" | "agile requirements")''',

    '''(AI | LLM | NLP)
        +("use cases" | scenarios)''',

    '''(AI | LLM | NLP)
        +("functional requirements" | "non-functional requirements" | NFRs)''',

    '''(AI | LLM | NLP)
        +("quality attributes" | performance | security | usability)
        +(requirements)''',

    # LLM-era language / generation
    '''(LLM | "large language model" | "generative AI")
        +("requirements generation" | "generate requirements" | "requirements synthesis")''',

    '''(LLM | NLP)
        +("natural language requirements" | "structured requirements")''',

    '''(LLM | chatbot | assistant)
        +("requirements elicitation" | stakeholders | interviews)''',

    # Traceability and alignment
    '''(AI | LLM | NLP)
        +("traceability link" | "link recovery")''',

    '''(AI | LLM)
        +("requirements to code" | "requirements to test" | alignment)''',

    '''(AI | LLM | NLP)
        +("cross-artifact consistency" | "artifact alignment")
        +(requirements)''',

    # Change, evolution, maintenance
    '''(AI | LLM | NLP)
        +("requirements change" | "change management")''',

    '''(AI | LLM)
        +("requirements evolution" | "requirements maintenance")''',

    # Explainability and human factors
    '''("explainable AI" | XAI)
        +("requirements engineering" | requirements)''',

    '''("human-in-the-loop")
        +(AI | LLM)
        +(requirements)''',

    '''(trust | reliability | risk | bias)
        +(AI | LLM)
        +(requirements)''',

    # Industry and practice
    '''(industry | industrial | practice)
        +(AI | LLM)
        +(requirements)''',

    '''(tool | framework | platform)
        +(AI | LLM)
        +(requirements)''',

    # Evaluation, datasets
    '''(evaluation | benchmark)
        +(AI | LLM)
        +(requirements)''',

    '''(dataset | corpus)
        +(requirements)
        +(AI | NLP | LLM)''',

    # Ethics, governance, safety
    '''(ethics | governance | compliance)
        +(AI | LLM)
        +(requirements)''',

    '''("safety-critical systems")
        +(AI | LLM)
        +(requirements)''',

    # Meta-level / research questions
    '''("research challenges" | "open challenges" | "future directions")
        +(AI | LLM)
        +(requirements)''',

    '''(taxonomy | classification | framework)
        +(AI | LLM)
        +(requirements)'''
]


fetched_papers = Papers(workspace="LLM in RE", queries=QUERIES)

doi_papers = fetched_papers.filter_by_doi()
doi_papers.perform_ai_task("full_relevance")
relevant_papers = doi_papers.where(lambda p: p.info["relevance"] >= 6)

relevant_papers.get_paper_location()
relevant_papers.download_papers()
downloaded_papers = relevant_papers.where(lambda p: p.has_text())

overview_papers = downloaded_papers.where(lambda p: p.info["is_overview"])
source_papers = downloaded_papers.where(lambda p: not p.info["is_overview"])

    
fetch_references = fetched_papers.get_custom_text("fetch_references")
referenced_papers = fetched_papers.get_all_references(fetch_references)
overview_papers.save_pdfs("overview_papers")
source_papers.save_pdfs("source_papers")

overview_papers.perform_ai_task("fetch_summary_info")
overview_papers = overview_papers.where(lambda p: p.info["about_requirements_engineering"])
overview_papers.perform_ai_task("fetch_summary_parts")

backgrounds = overview_papers.where(lambda p: "background" in p.info)
source_papers.perform_ai_task("fetch_source_info")
source_papers = source_papers.where(lambda p: p.info["about_requirements_engineering"])


request = f"""
You are an expert in Requirements Engineering (RE) and in analyzing research literature.

You will be given a list of OVERVIEW papers (e.g., surveys, systematic literature reviews, mapping studies, or guidelines), along with structured metadata for each paper:
{CONTENT_TAG}

Your task is to produce a **cohesive, well-written background section**, approximately 3 pages long, synthesizing the relevant information from all provided papers.

Instructions:

1. Focus only on the **background/context** of the research area. Do NOT include detailed results or discussion from individual papers — those belong elsewhere.
2. Extract the most important, **non-redundant, and high-confidence information** from the papers. Prefer insights that are shared across multiple sources.
3. Structure the background clearly:
   - Introduce the research area and its importance.
   - Summarize relevant prior work.
   - Highlight key challenges, trends, and gaps in the literature.
   - Present any commonly used concepts, definitions, or taxonomies mentioned across the papers.
4. Preserve academic tone and clarity. Do not invent facts or make unsupported claims.
5. If information is contradictory across papers, present it accurately and neutrally.
6. Use your own words to synthesize the information. Avoid copying entire sentences verbatim, except for exact definitions or terminology where necessary.
7. Output should be a single, cohesive text, suitable for inclusion as the **Background** section of a research paper (~3 pages in length).
8. Tend to cite the full title of each paper you are referring to. This is very important!

Additional metadata hints: You may use fields such as:
- relevance, is_overview, about_requirements_engineering
- main_contribution, taxonomy_coverage_percent
- llm_positivity_score, paper_summary, key_takeaways, background

Output Format Rules (MANDATORY):
- Return ONLY the text of the synthesized background.
- Do NOT include JSON, markdown, explanations, or section titles.

"""
included_info=['relevance', 'is_overview', 'about_requirements_engineering', 'main_contribution',
               'taxonomy_coverage_percent', 'llm_positivity_score', 'paper_summary', 'key_takeaways', 'background']
background_summary = backgrounds.ai_joint(request, included_info)
introduction_txt = fetched_papers.get_custom_text("introduction")
background_txt = fetched_papers.get_custom_text("background")
discussion_txt = fetched_papers.get_custom_text("discussion")

introduction_txt = fetched_papers.resolve_references(introduction_txt, prop="id")
discussion_txt = fetched_papers.resolve_references(discussion_txt, prop="id")

request = f"""
Given this summary of several overview papers, please give me a taxonomy of the current state of LLMs in RE.
Tell me what are the similarities between these studies, dissimilarities, problems. I want a full report on the current
state. It can be long as much as you want but don't invent anything by yourself: every sentence or almost, should
be justified by what you got from the papers (better if you also tell which one).

{CONTENT_TAG}
"""
included_info=['relevance', 'is_overview', 'about_requirements_engineering', 'main_contribution',
               'taxonomy_coverage_percent', 'llm_positivity_score', 'paper_summary', 'key_takeaways']
summary_response = overview_papers.ai_joint(request, included_info)

overview_papers.perform_ai_task("fetch_overview_methodologies")
source_papers.perform_ai_task("fetch_source_methodologies")

overview_papers = overview_papers.where(lambda p: "taxonomy_overview" in p.info)
source_papers = source_papers.where(lambda p: "paper_contributions" in p.info)


source_papers = source_papers.where(lambda p: "taxonomy_contributions" in p.info)
source_papers.perform_ai_task("fetch_statistics", instant=True)
source_papers.perform_ai_task("fetch_statistics2", instant=True)

normalized_keys = ['generation', 'analysis', 'translation', 'quality_assessment', 'design_derivation']
overall = {k: {"n": 0, "conc": 0, "method": 0, "implem": 0, "text": 0, "struct": 0, "formal": 0} for k in normalized_keys}
overall = {**overall, "conc_p": 0, "method_p": 0, "implem_p": 0, "text_p": 0, "struct_p": 0, "formal_p": 0}

for p in overview_papers:
    print(p.info["key_takeaways"])
#     if "stats" in p.info:
#         for k, v in p.info["stats"].items():
#             overall[k]["n"] += 1
#             if v["maturity"]["Label"] == "Conceptual":
#                 overall[k]["conc"] += 1
#             if v["maturity"]["Label"] == "Methodological":
#                 overall[k]["method"] += 1
#             if v["maturity"]["Label"] == "Implemented":
#                 overall[k]["implem"] += 1
#             if v["formality"]["Label"] == "Structured":
#                 overall[k]["struct"] += 1
#             if v["formality"]["Label"] == "Text":
#                 overall[k]["text"] += 1
#             if v["formality"]["Label"] == "Formal/Exec":
#                 overall[k]["formal"] += 1

# for p in source_papers:
#     if "stats" in p.info:
#         for k, v in p.info["stats"].items():
#             overall[k]["conc_p"] =   int(100 * overall[k]["conc"] / (overall[k]["conc"] + overall[k]["method"] + overall[k]["implem"]))
#             overall[k]["method_p"] = int(100 * overall[k]["method"] / (overall[k]["conc"] + overall[k]["method"] + overall[k]["implem"]))
#             overall[k]["implem_p"] = int(100 * overall[k]["implem"] / (overall[k]["conc"] + overall[k]["method"] + overall[k]["implem"]))
#             overall[k]["text_p"] =   int(100 * overall[k]["text"] / (overall[k]["text"] + overall[k]["struct"] + overall[k]["formal"]))
#             overall[k]["struct_p"] = int(100 * overall[k]["struct"] / (overall[k]["text"] + overall[k]["struct"] + overall[k]["formal"]))
#             overall[k]["formal_p"] = int(100 * overall[k]["formal"] / (overall[k]["text"] + overall[k]["struct"] + overall[k]["formal"]))

# for k, v in overall.items():
#     print(k, v)
raise

def get_stats(data):
    mat_conc = data["mat_conc"]
    mat_met = data["mat_met"]
    mat_impl = data["mat_impl"]
    tool = data["Tooling_Explicit"]
    haf_structured = data["haf_structured"] if (mat_impl) else 0
    haf_text = data["haf_text"] if (mat_impl) else 0
    haf_formal = data["haf_formal"] if (mat_impl) else 0
    return (mat_conc, mat_met, mat_impl, tool, haf_structured, haf_text, haf_formal)

all_stats = {k: [0, 0, 0, 0, 0, 0, 0] for k in normalized_keys}
for p in source_papers:
    if "stats" in p.info:
        for k in p.info["stats"]:
            stats = get_stats(p.info["stats"][k])
            for i in range(len(all_stats[k])):
                all_stats[k][i] += stats[i]
for k, v in all_stats.items():
    tot_mat = sum(v[0:3])
    tot_haf = sum(v[-3:])
    # for i in range(4, 7):
    #     all_stats[k][i] = 0 if tot_haf == 0 else int(100 * all_stats[k][i] / tot_haf)
    # for i in range(0, 3):
    #     all_stats[k][i] = 0 if tot_mat == 0 else int(100 * all_stats[k][i] / tot_mat)
# print(all_stats)
# {'generation': [38, 36, 33, 39, 59, 34, 6], 'analysis': [71, 66, 59, 69, 67, 25, 6], 'translation': [20, 20, 18, 20, 41, 17, 41], 'quality_assessment': [37, 26, 20, 29, 25, 65, 10], 'design_and_traceability': [42, 34, 29, 32, 58, 0, 41]}
# 'generation': [51, 46, 41, 48, 56, 36, 7], 'analysis': [75, 68, 61, 70, 73, 18, 8], 'translation': [32, 28, 27, 30, 30, 11, 57], 'quality_assessment': [55, 40, 37, 44, 27, 63, 8], 'design_and_traceability': [59, 47, 44, 44, 62, 2, 34]

    # print(p.info.keys())
    # if "taxonomy_contributions" in p.info:
    #     import json
    #     print(json.dumps({k: v for k, v in p.info["taxonomy_contributions"].items() if len(v) > 20}, indent=2))

raise

responses = {}
for task in ["Requirement Generation", "Requirement Analysis", "Requirement Translation", "Requirement Quality Assessment", "Design Derivation"]:
    request = f"""
    Given this summary of several overview papers, please provide me a report of the current state of the '{task}' task.
    Ignore all the other parts of the taxonomy. They will be processed in other queries.
    Tell me what are the similarities between primary studies about this task and dissimilarities. Optionally tell me how many studies you found about this task.
    I want a full report on the current state. It can be long as much as you want but don't invent anything by yourself: every sentence or almost, should
    be justified by what you got from the papers (better if you also mention their full-title as they can be referenced later on).

    {CONTENT_TAG}
    """
    included_info=['relevance', 'is_overview', 'about_requirements_engineering', 'main_contribution',
                'taxonomy_coverage_percent', 'llm_positivity_score', 'paper_summary', 'key_takeaways', 'taxonomy_overview']
    responses[task] = {"summarization": overview_papers.ai_joint(request, included_info), "text": ""}

    request = f"""
    Given this summary of several overview papers, please provide me a report of the current state of the '{task}' task.
    This will be part of a dedicated section into a meta-analysis around the concept of '{task}', so be descriptive and be as most as possible
    anchored to the source.

    {CONTENT_TAG}

    A previous summarization of key points:
    {responses[task]['summarization']}

    Now generate me a nice paragraph about the task: {task}. Don't create paragraph by your own. I need a full text in which trends and
    sources are highlighted. Common methodologies and technologies also have to transpire.
    """
    included_info=['relevance', 'is_overview', 'about_requirements_engineering', 'main_contribution',
                'taxonomy_coverage_percent', 'llm_positivity_score', 'paper_summary', 'key_takeaways', 'taxonomy_overview']
    responses[task]["text"] = overview_papers.ai_joint(request, included_info)
    # print(responses[task]["text"] + "\n -------------\n")


# summarization = "\n\n".join([responses[task]['summarization'] for task in responses])
# request = f"""
# Content: \n{CONTENT_TAG}

# Partial summarization: \n{summarization}

# Instructions:

# 1. Produce a detailed comparative synthesis of the overview papers in above.
# 2. Organize the output into the following sections:
# a. Common themes and methodologies (similarities)
# b. Divergent approaches or findings (dissimilarities)
# c. Technological trends (architectures, models, prompting strategies)
# d. Input and output formats
# e. Evaluation strategies
# f. Domain-specific considerations
# g. Notable gaps or limitations
# 3. For each point, cite explicitly the source(s) from {CONTENT_TAG}.
# 4. Prefer **bullet points or tables** to allow later summarization.
# 5. Include quantitative information if reported (percentages, counts), but do not invent numbers.
# 6. Ensure the text is factual and strictly anchored in the sources.
# 7. Produce enough detail that the resulting output can span **3+ pages** when formatted in a paper.
# """
# included_info=['relevance', 'is_overview', 'about_requirements_engineering', 'main_contribution',
#             'taxonomy_coverage_percent', 'llm_positivity_score', 'paper_summary', 'key_takeaways', 'taxonomy_overview']
# overview_papers.ai_joint(request, included_info)


request = f"""
Content: \n{CONTENT_TAG}

Introduction: {introduction_txt}
Background: {background_txt}
Discussion: {discussion_txt}

Given these overview papers's takeaways and the Introduction-background-discussion (taxonomy omitted) of my meta-analysis paper,
please provide me with a detailed 1-2 pages conclusions that fit as a finale of the paper

"""
included_info=['relevance', 'is_overview', 'about_requirements_engineering', 'main_contribution',
            'taxonomy_coverage_percent', 'llm_positivity_score', 'paper_summary', 'key_takeaways', 'taxonomy_overview']
overview_papers.ai_joint(request, included_info)


# textual_responses = [f'\n ------ TASK: {task} \n{text}' for task, text in responses.items()]
# request = f"""
# Given this summary of several overview papers, please provide me a report of each single.
# Ignore all the other parts of the taxonomy. They will be processed in other queries.
# Tell me what are the similarities between primary studies about this task and dissimilarities. Optionally tell me how many studies you found about this task.
# I want a full report on the current state. It can be long as much as you want but don't invent anything by yourself: every sentence or almost, should
# be justified by what you got from the papers (better if you also mention their full-title as they can be referenced later on).

# {CONTENT_TAG}

# {"".join(textual_responses)}
# """
# included_info=['relevance', 'is_overview', 'about_requirements_engineering', 'main_contribution',
#             'taxonomy_coverage_percent', 'llm_positivity_score', 'paper_summary', 'key_takeaways', 'taxonomy_overview']
# responses.append(overview_papers.ai_joint(request, included_info))


# for p in source_papers:
#     for e in p.info["paper_contributions"]:
#         print(e["taxonomy_category"])

# import json
# for p in overview_papers[1:]:
#     dict_ = json.loads(json.dumps(p.info))
#     dict_ = {"title": p.title, **dict_}
#     print(f"{json.dumps(dict_, indent=2)}")
#     raise



