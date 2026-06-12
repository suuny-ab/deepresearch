from deepresearch.state import ExtractedClaim, ExtractedSource


def build_validation_prompt(
    sq_id: str,
    sq_question: str,
    claims: list[ExtractedClaim],
    sources: list[ExtractedSource],
) -> str:
    claim_lines = []
    for c in claims:
        claim_lines.append(f"- [{c.id}] {c.claim} (primary source: {c.source_url})")

    source_lines = []
    for s in sources:
        source_lines.append(f"  URL: {s.url} | Title: {s.title}")
        source_lines.append(f"  Content: {s.raw_content}")
        source_lines.append("")

    claims_text = "\n".join(claim_lines)
    sources_text = "\n".join(source_lines)

    return f"""
You are evaluating whether claims extracted from one source are
independently corroborated by OTHER sources within the same subquestion.

Subquestion [{sq_id}]: {sq_question}

Claims to validate (all from this subquestion):
{claims_text}

Sources for this subquestion (each from a different domain):
{sources_text}

For each claim:
1. Identify which source it came from (the primary source, by source_url)
2. Check the OTHER sources (different from the primary) for independent
   confirmation of the same fact or finding
3. A claim is corroborated only if another source independently states
   the same fact — not just mentions the same topic
4. Assign corroboration_level:
   - "strongly_corroborated": 2+ OTHER sources independently confirm
   - "weakly_corroborated": 1 OTHER source independently confirms
   - "single_source": no other source confirms
5. For corroborated claims, include the corroborating source URLs

IMPORTANT:
- Do NOT create new claims. Only validate the claims provided above.
- Sources in this subquestion are already from different domains —
  no need to check domain diversity.
- Preserve all fields from the input claims (id, claim, source_url,
  source_title, supporting_snippet, content_type, confidence)

Return only JSON:
{{"evidence_cards":[{{"id":"e1","subquestion_id":"q1","claim":"...","source_url":"https://...","source_title":"...","supporting_snippet":"...","content_type":"extracted_content","corroboration_level":"single_source|weakly_corroborated|strongly_corroborated","corroborating_sources":["https://other.example/..."],"confidence":"low|medium|high"}}]}}
""".strip()
