"""1+1 evidence pipeline: Phase 1 extraction (separate) + merged Phase 2 validation.

Unlike the fully merged 1-dai-1+N approach (which failed: sr +0.14, cognitive load +0.30),
this prompt does ONLY cross-validation — it receives pre-extracted claims and checks
corroboration across all sources in one call.  Cognitive load is lower because:

- Extraction is handled by Phase 1 (separate call, dedicated attention)
- Validation only checks "claim X → supported by source Y?" (focused task)
- N per-subquestion validation calls → 1 global validation call

Input: all extracted claims + all sources (grouped by subquestion).
Output: evidence_cards with corroboration_level + corroborating_snippets.
"""

from deepresearch.state import ExtractedClaim, ExtractedSource, SubQuestion


def build_1plus1_validation_prompt(
    question: str,
    claims: list[ExtractedClaim],
    sources: list[ExtractedSource],
    subquestions: list[SubQuestion],
) -> str:
    """Build a prompt that cross-validates ALL claims against ALL sources in one call.

    Claims are already extracted (Phase 1).  This prompt only does corroboration.
    """
    sq_map: dict[str, str] = {sq.id: sq.question for sq in subquestions}

    # Group sources by subquestion
    src_groups: dict[str, list[ExtractedSource]] = {}
    for src in sources:
        src_groups.setdefault(src.subquestion_id, []).append(src)

    # Build source catalog with global numbering
    source_lines = []
    source_num = 0
    for sq_id, group_srcs in src_groups.items():
        sq_question = sq_map.get(sq_id, sq_id)
        source_lines.append(f"--- {sq_id}: {sq_question} ---")
        for src in group_srcs:
            source_num += 1
            domain = src.url.split("/")[2] if "//" in src.url else src.url
            source_lines.append(f"[Source #{source_num}] Domain: {domain}")
            source_lines.append(f"URL: {src.url} | Title: {src.title}")
            source_lines.append(f"{src.raw_content[:3000]}")
            source_lines.append("")

    # Build claims list grouped by subquestion
    claim_lines = []
    claim_groups: dict[str, list[ExtractedClaim]] = {}
    for c in claims:
        claim_groups.setdefault(c.subquestion_id, []).append(c)

    for sq_id, sq_claims in claim_groups.items():
        sq_question = sq_map.get(sq_id, sq_id)
        claim_lines.append(f"--- {sq_id}: {sq_question} ---")
        for c in sq_claims:
            claim_lines.append(f"Claim [{c.id}]: {c.claim}")
            claim_lines.append(f"  Primary source: {c.source_url}")
            claim_lines.append(f"  Supporting snippet: {c.supporting_snippet[:200]}")
        claim_lines.append("")

    return f"""You are a cross-validation specialist. Your only task: check whether each claim below is independently supported by OTHER sources.

## Research Question
{question}

## Claims to Validate (grouped by subquestion)
{chr(10).join(claim_lines)}

## Available Sources (grouped by subquestion)
{chr(10).join(source_lines)}

## Task

For each claim, determine its corroboration level by checking OTHER sources from DIFFERENT domains:

- "strongly_corroborated": ≥2 OTHER sources from different domains independently state the same fact. Provide corroborating_snippets with the EXACT text.
- "weakly_corroborated": 1 OTHER source from a different domain independently states the same fact. Provide corroborating snippet.
- "single_source": No other source independently states this fact. corroborating_sources is empty.

## Rules

- Same domain does NOT count as independent. Two articles from nature.com = 1 source.
- "Same fact" means the same substantive conclusion with consistent numbers/timeframes.
- If you cannot find specific text that matches → mark single_source. Conservative is correct.
- Do not change the claim text, source_url, or confidence from the input.

## Output JSON

{{
  "evidence_cards": [
    {{
      "id": "{claims[0].id if claims else 'e1'}",
      "subquestion_id": "q1",
      "claim": "original claim text (unchanged)",
      "source_url": "original source URL",
      "source_title": "original source title",
      "supporting_snippet": "original snippet",
      "content_type": "extracted_content",
      "corroboration_level": "strongly_corroborated",
      "corroborating_sources": [
        {{"url": "https://other-source", "snippet": "exact supporting text"}}
      ],
      "confidence": "original confidence"
    }}
  ]
}}

Return ONLY the JSON. Preserve each claim's original id, source_url, and confidence.
""".strip()
