from deepresearch.state import SearchResult, SubQuestion


def build_synthesizing_prompt(question: str, subquestions: list[SubQuestion], results: list[SearchResult]) -> str:
    return f"""
You are a careful research analyst. Use only the supplied search results.
Extract key findings for each subquestion. Every finding must be traceable to one of the supplied URLs.
Return only JSON in this exact shape:
{{"notes":[{{"subquestion_id":"q1","key_findings":["..."],"source_urls":["https://..."],"confidence":"low|medium|high"}}]}}

Original question:
{question}

Subquestions:
{[item.model_dump() for item in subquestions]}

Search results:
{[item.model_dump() for item in results]}
""".strip()
