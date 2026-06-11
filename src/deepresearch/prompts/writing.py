from deepresearch.state import EvidenceCard, ResearchNote, SearchResult, SubQuestion


def build_writing_prompt(
    question: str,
    subquestions: list[SubQuestion],
    notes: list[ResearchNote],
    results: list[SearchResult],
    evidence_cards: list[EvidenceCard] | None = None,
    allowed_source_urls: set[str] | None = None,
) -> str:
    if allowed_source_urls is not None:
        allowed_urls = sorted(allowed_source_urls)
    elif evidence_cards:
        allowed_urls = sorted({card.source_url for card in evidence_cards})
    else:
        allowed_urls = sorted({item.url for item in results})
    return f"""
请使用中文撰写结构化 Markdown 深度研究报告，除非用户问题使用其他语言。

引用规则必须严格遵守：
1. 正文中的每个关键论点必须使用编号引用，例如 [1]、[2]。
2. 正文中不要出现裸 URL。
3. 所有 URL 只能出现在 ## Sources 部分。
4. ## Sources 中必须用 [1]、[2] 映射到 allowed source URLs。
5. 正文中使用的每个编号都必须在 ## Sources 中定义。
6. ## Sources 中列出的每个编号都必须在正文中出现。
7. 只能使用 Allowed source URLs 列表中的 URL。

Citation rules:
- Use numbered citations in the body: [1], [2], [3].
- Do not put raw URLs in the body.
- URLs may only appear in the ## Sources section.
- Every citation number used in the body must be defined in ## Sources.
- Every source listed in ## Sources must be cited in the body.
- Only use URLs from the allowed source URL list.

Required sections:
# <title>
## 摘要
## 关键结论
## 背景与问题拆解
## 深度分析
## 风险、不确定性与不同观点
## 结论
## Sources

Sources format:
[1] https://example.com/source-a
[2] https://example.com/source-b

Original question:
{question}

Subquestions:
{[item.model_dump() for item in subquestions]}

Research notes:
{[item.model_dump() for item in notes]}

Allowed source URLs:
{allowed_urls}
""".strip()
