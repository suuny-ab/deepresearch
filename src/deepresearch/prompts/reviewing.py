from deepresearch.state import SearchResult


def build_reviewing_prompt(question: str, report_markdown: str, results: list[SearchResult]) -> str:
    urls = sorted({item.url for item in results})
    return f"""
Review this Markdown research report for relevance, completeness, source support, structure, and unsupported claims.
Return only JSON in this exact shape:
{{"passed":true,"score":88,"issues":["..."],"suggestions":["..."]}}
Score must be an integer from 0 to 100.

Original question:
{question}

Allowed source URLs:
{urls}

Report:
{report_markdown}
""".strip()
