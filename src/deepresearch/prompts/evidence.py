from deepresearch.state import ExtractedSource


def build_evidence_prompt(question: str, sources: list[ExtractedSource]) -> str:
    return f"""
You extract EvidenceCard objects from source text for a research report.
Do not create claims not supported by the source text.
Every claim must be grounded in a supporting_snippet copied or closely paraphrased from the source text.
Each EvidenceCard must copy the supplied `url` value into EvidenceCard `source_url`.
If the source text is weak, thin, or only a search snippet, use low confidence.

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

Sources:
{[source.model_dump() for source in sources]}
""".strip()
