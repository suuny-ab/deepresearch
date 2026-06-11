from deepresearch.state import ExtractedSource


def build_evidence_prompt(question: str, sources: list[ExtractedSource]) -> str:
    return f"""
You extract EvidenceCard objects from source text for a research report.
Do not create claims not supported by the source text.
Every claim must be grounded in a supporting_snippet copied or closely paraphrased from the source text.
Each EvidenceCard must include the source URL from the supplied source_url values.
If the source text is weak, thin, or only a search snippet, use low evidence_reliability.
Do not infer facts, numbers, dates, or conclusions that are not explicitly supported by the source text.

Return only JSON in this exact shape:
{{"evidence_cards":[{{"id":"e1","subquestion_id":"q1","claim":"...","source_url":"https://...","source_title":"...","supporting_snippet":"...","content_type":"extracted_content","source_type":"industry_report","source_quality_score":85,"evidence_reliability":"low|medium|high","confidence":"low|medium|high"}}]}}

Original question:
{question}

Sources:
{[source.model_dump() for source in sources]}
""".strip()
