from deepresearch.state import ResearchNote, SearchResult, SubQuestion


def build_writing_prompt(
    question: str,
    subquestions: list[SubQuestion],
    notes: list[ResearchNote],
    results: list[SearchResult],
) -> str:
    allowed_urls = sorted({item.url for item in results})
    return f"""
Write a structured Markdown deep research report in Chinese unless the user's question is in another language.
Use only the supplied notes and source URLs. Do not invent URLs.
Every key conclusion should include a source URL or footnote.

Required sections:
# <title>
## 摘要
## 关键结论
## 背景与问题拆解
## 深度分析
## 风险、不确定性与不同观点
## 结论
## Sources

Original question:
{question}

Subquestions:
{[item.model_dump() for item in subquestions]}

Research notes:
{[item.model_dump() for item in notes]}

Allowed source URLs:
{allowed_urls}
""".strip()
