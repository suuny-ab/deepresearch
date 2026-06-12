from deepresearch.state import ExtractedSource, SubQuestion


def build_evidence_prompt(
    question: str,
    sources: list[ExtractedSource],
    subquestions: list[SubQuestion],
) -> str:
    sq_map: dict[str, str] = {
        sq.id: sq.question for sq in subquestions
    }

    groups: dict[str, list[ExtractedSource]] = {}
    for source in sources:
        key = source.subquestion_id
        groups.setdefault(key, []).append(source)

    subquestion_lines = []
    if subquestions:
        subquestion_lines.append("Research subquestions:")
        for sq in subquestions:
            subquestion_lines.append(f"- [{sq.id}] {sq.question}")
        subquestion_lines.append("")

    source_lines = []
    source_lines.append("Sources (grouped by subquestion):")
    for sq_id, group_sources in groups.items():
        sq_question = sq_map.get(sq_id, sq_id)
        source_lines.append(f"--- {sq_id}: {sq_question} ---")
        for source in group_sources:
            source_lines.append(f"  URL: {source.url}")
            source_lines.append(f"  Title: {source.title}")
            source_lines.append(f"  Content ({source.format}): {source.raw_content}")
            source_lines.append("")
    source_lines.append("---")

    grouped_sources = "\n".join(source_lines)
    subquestion_overview = "\n".join(subquestion_lines)

    return f"""
You extract EvidenceCard objects from source text for a research report.
Do not create claims not supported by the source text.
Every claim must be grounded in a supporting_snippet copied or closely paraphrased from the source text.
Each EvidenceCard must copy the supplied `url` value into EvidenceCard `source_url`.
If the source text is weak, thin, or only a search snippet, use low confidence.

The sources below are organized by subquestion. Each source was retrieved
to answer a specific subquestion, shown in the group header.
Use this structure to understand the research intent behind each source
when deciding whether two sources from DIFFERENT subquestions are truly
corroborating the same claim, or merely discussing related topics from
different angles.

{subquestion_overview}

For each claim you extract, also check ALL other supplied sources
(even those from different subquestions that cover related topics)
to determine whether independent sources corroborate the same claim.

corroboration_level rules:
- "single_source"      Only this one source mentions this claim
- "weakly_corroborated"      One OTHER independent source (different domain) supports this claim
- "strongly_corroborated"    2+ OTHER independent sources (different domains) support this claim

CRITICAL: Two pages from the SAME domain (e.g., two openai.com pages)
do NOT count as independent corroboration. Only DIFFERENT domain
agreement constitutes meaningful cross-validation.

When asserting corroboration, you MUST:
1. Quote the supporting snippet from the corroborating source
2. Verify the corroborating source's domain is different from the primary source
3. Include corroborating source URLs in corroborating_sources

Each source is marked with content_type:
- "extracted_content" — full webpage text was available
- "search_content"   — only a search snippet was available (extract failed)

When assessing corroboration strength:
- Two full-text sources independently stating the same fact → strong signal
- One full text + one snippet → weaker but still valid
- Two snippets → treat as weakly_corroborated at best
- Label the strength honestly; do not inflate weak signals

Return only JSON in this exact shape:
{{"evidence_cards":[{{"id":"e1","subquestion_id":"q1","claim":"...","source_url":"https://...","source_title":"...","supporting_snippet":"...","content_type":"extracted_content","corroboration_level":"single_source|weakly_corroborated|strongly_corroborated","corroborating_sources":["https://other-domain.com/..."],"confidence":"low|medium|high"}}]}}

Original question:
{question}

{grouped_sources}
""".strip()
