def build_planning_prompt(question: str, max_subquestions: int) -> str:
    return f"""
You are a research planner. Decompose the user's research question into up to {max_subquestions} non-overlapping subquestions.
For each subquestion, provide search_query and search_queries suitable for Tavily.
search_queries must contain 2 different-angle queries: a 中文 query and an English query.
Return only JSON in this exact shape:
{{"subquestions":[{{"id":"q1","question":"...","search_query":"...","search_queries":["中文 query","English query"],"rationale":"..."}}]}}

Research question:
{question}
""".strip()
