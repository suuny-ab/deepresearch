from deepresearch.state import ExtractedSource, SubQuestion


def build_extraction_prompt(
    question: str,
    sources: list[ExtractedSource],
    subquestions: list[SubQuestion],
) -> str:
    sq_map: dict[str, str] = {sq.id: sq.question for sq in subquestions}

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
You are extracting claims from source texts for a research report.

A claim is a specific factual assertion, finding, or argument that can be
traced to a particular passage in a source text. Extract every distinct,
citable claim from every source. There is no minimum or maximum —
extract as many as each source genuinely contains.

Rules:
- Each claim MUST include a supporting_snippet from the source text
- Prefer specific, verifiable claims over vague generalizations
- Do NOT check other sources for corroboration — that is a separate step
- Do NOT assign any reliability or corroboration level
- Assign a confidence to each claim based on the source text quality:
  - "high": well-supported with specific evidence
  - "medium": reasonably supported
  - "low": weakly supported or thin

The sources below are organized by subquestion. Each source was retrieved
to answer a specific subquestion, shown in the group header.

{subquestion_overview}

Return only JSON in this exact shape:
{{"claims":[{{"id":"e1","subquestion_id":"q1","claim":"...","source_url":"https://...","source_title":"...","supporting_snippet":"...","content_type":"extracted_content","confidence":"low|medium|high"}}]}}

Original question:
{question}

{grouped_sources}
""".strip()
