from ai_queries import CONTENT_TAG
from paper_analysis import Papers


fetched_papers = Papers(workspace="RE", queries=[])
# fetched_papers = fetched_papers.expand()

doi_papers = fetched_papers.filter_by_doi()
doi_papers.perform_ai_task("full_relevance_to_RE", instant=True)
relevant_papers = doi_papers.where(lambda p: p.info["relevance"] >= 6)

relevant_papers.get_paper_location()
relevant_papers.download_papers()
downloaded_papers = relevant_papers.where(lambda p: p.has_text())


overview_papers = downloaded_papers.where(lambda p: p.is_overview() and p.info["is_overview"])
source_papers = downloaded_papers.where(lambda p: not p.is_overview() or not p.info["is_overview"])

overview_papers.save_pdfs("overview_papers")
source_papers.save_pdfs("source_papers")

overview_papers.perform_ai_task("fetch_summary_info", instant=True)
overview_papers = overview_papers.where(lambda p: p.info["about_requirements_engineering"])

overview_papers.perform_ai_task("fetch_summary_challenges_overview", instant=True)

# source_papers.perform_ai_task("fetch_source_info")
# source_papers = source_papers.where(lambda p: p.info["about_requirements_engineering"])


p_titles = "\n".join([x.title for x in overview_papers])
request = f"""
You are an expert researcher in Requirements Engineering that replies only via structured json.

You will be given a summary of several overview papers.

Your task:

- Write 1-2 detailed pages discussing Requirements Engineering and its challenges.
- Every claim or statement **must be linked to one or more of the EXACT titles** from the provided list.
- Do not make up any references or titles.
- Use the EXACT title string from the list in double quotes whenever citing a source.

{CONTENT_TAG}

This are the exact titles of the papers:
{p_titles}
"""
included_info=['main_contribution', 'key_takeaways', 'relevant_challenges']
summary_response = overview_papers.ai_joint(request, included_info)

introduction_txt = overview_papers.get_custom_text("introduction")
introduction_txt = overview_papers.resolve_references(introduction_txt, prop="title")

fetch_references = fetched_papers.get_custom_text("introduction")
referenced_papers = fetched_papers.get_all_references(fetch_references)
referenced_papers.save_pdfs("refs")
d = {}
for p in referenced_papers:
    d[p.title] = p.id
    if p.year is None:
        title = p.title.replace(" ", "+")
        while "++" in p.title:
            title = title.replace("++", "+")
import json
print(json.dumps(d, indent=2))

# import json
# for p in overview_papers[1:]:
#     dict_ = json.loads(json.dumps(p.info))
#     dict_ = {"title": p.title, **dict_}
#     print(f"{json.dumps(dict_["main_contribution"], indent=2)}")



