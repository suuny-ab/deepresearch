def build_planning_prompt(question: str, max_subquestions: int) -> str:
    return f"""
You are a research planner. Decompose the user's research question into 3 to {max_subquestions} non-overlapping subquestions.
For each subquestion, provide one web search query suitable for Tavily.
Return only JSON in this exact shape:
{{"subquestions":[{{"id":"q1","question":"...","search_query":"...","rationale":"..."}}]}}

Research question:
{question}
""".strip()
