"""Merged Phase 1+2 prompt: extract + cross-validate in one LLM call.

Replaces the two-step 1+N pipeline (Phase 1 extraction + Phase 2 per-subquestion
cross-validation) with a single call that interleaves extraction and corroboration
assessment.

Design constraints (from D1 post-mortem):
- No hard numeric targets ("at least N claims") — injects variance, not quality
- Merge instruction: same fact, different wording → one claim
- Corroboration requires specific text evidence (corroborating_snippets)
- Conservative default: "unsure → single_source"
"""

from deepresearch.state import ExtractedSource, SubQuestion


def build_merged_evidence_prompt(
    question: str,
    sources: list[ExtractedSource],
    subquestions: list[SubQuestion],
) -> str:
    """Build a prompt that extracts claims AND cross-validates in one call.

    Input: all extracted sources grouped by subquestion, plus the original question.
    Output: evidence_cards with corroboration_level + corroborating_snippets.
    """
    sq_map: dict[str, str] = {sq.id: sq.question for sq in subquestions}

    # Group sources by subquestion
    groups: dict[str, list[ExtractedSource]] = {}
    for source in sources:
        key = source.subquestion_id
        groups.setdefault(key, []).append(source)

    # Build source text, numbering all sources globally for cross-reference
    source_num = 0
    source_lines = []
    source_map: dict[int, str] = {}  # source_num → domain
    for sq_id, group_sources in groups.items():
        sq_question = sq_map.get(sq_id, sq_id)
        source_lines.append(f"--- {sq_id}: {sq_question} ---")
        for source in group_sources:
            source_num += 1
            domain = source.url.split("/")[2] if "//" in source.url else source.url
            source_map[source_num] = domain
            source_lines.append(f"[Source #{source_num}] URL: {source.url} | Domain: {domain}")
            source_lines.append(f"Title: {source.title}")
            source_lines.append(f"Content ({source.format}): {source.raw_content}")
            source_lines.append("")
    source_lines.append("---")

    grouped_sources = "\n".join(source_lines)

    return f"""You are an evidence analyst. Extract claims from the provided sources AND assess their corroboration — in one pass.

## Research Question
{question}

## Sources
{grouped_sources}

You have {source_num} sources across {len(groups)} subquestions.

## Task

For each factual claim you extract, simultaneously check whether OTHER sources (different domain) independently state the same fact. Output evidence_cards with corroboration data.

### Corroboration Rules

- "strongly_corroborated": ≥2 OTHER sources from DIFFERENT domains independently state this same fact. For each corroborating source, you MUST provide the exact supporting text in corroborating_snippets.
- "weakly_corroborated": 1 OTHER source from a different domain independently states this fact. Provide the corroborating snippet.
- "single_source": Only the primary source contains this claim. corroborating_sources is empty.
- If you cannot find the specific text in another source → mark it single_source. Do not assume corroboration.

### Merging Rules

Two claims are the SAME fact (should be merged) if and only if:
- Their substantive conclusions are identical (not just related topic)
- Any numbers involved (time, quantity, percentage) are consistent within reasonable tolerance
  "2027" and "2027-2028" → mergeable (time ranges overlap)
  "500 Wh/kg" and "400-500 Wh/kg" → keep SEPARATE (definite value vs range — different claims)
- If unsure → keep separate, both marked single_source. Conservative is correct.

### Quantity

- One claim = one verifiable fact. Do NOT split the same fact into multiple claims with different wording.
- The number of claims depends on what the sources actually contain. There is no target number.
- Sources with rich content will naturally produce more claims; thin sources fewer.

### Output JSON

{{
  "evidence_cards": [
    {{
      "id": "e1",
      "subquestion_id": "q1",
      "claim": "factual claim in one sentence",
      "source_url": "https://...",
      "source_title": "Source Title",
      "supporting_snippet": "exact text from the primary source",
      "content_type": "extracted_content",
      "corroboration_level": "strongly_corroborated",
      "corroborating_sources": [
        {{"url": "https://other-source", "snippet": "exact supporting text from this source"}}
      ],
      "confidence": "high"
    }}
  ]
}}

corroboration_level must be one of: strongly_corroborated | weakly_corroborated | single_source
confidence must be one of: high | medium | low

Return ONLY the JSON. No explanation, no markdown wrappers.""".strip()
