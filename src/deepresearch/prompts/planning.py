def build_planning_prompt(question: str, max_subquestions: int) -> str:
    return f"""
You are a research planner. Decompose the user's research question into 3 to {max_subquestions} non-overlapping subquestions.
For each subquestion, provide search_query and search_queries suitable for Tavily.
search_queries must contain 2-3 different-angle queries: a 中文 query, an English query, and when useful a report/research query.
Return only JSON in this exact shape:
{{"subquestions":[{{"id":"q1","question":"...","search_query":"...","search_queries":["中文 query","English query","report research query"],"rationale":"..."}}]}}

Research question:
{question}
""".strip()
