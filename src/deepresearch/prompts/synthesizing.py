from deepresearch.state import EvidenceCard, SubQuestion


def build_synthesizing_prompt(question: str, subquestions: list[SubQuestion], evidence_cards: list[EvidenceCard]) -> str:
    return f"""
You are a careful research analyst. Use only the supplied EvidenceCards.
Only summarize claims present in EvidenceCards. Do not introduce facts not supported by EvidenceCards.
Low reliability evidence cannot support high confidence findings.
Every finding must be traceable to one of the supplied EvidenceCard source_url values.
Return only JSON in this exact shape:
{{"notes":[{{"subquestion_id":"q1","key_findings":["..."],"source_urls":["https://..."],"confidence":"low|medium|high"}}]}}

Original question:
{question}

Subquestions:
{[item.model_dump() for item in subquestions]}

evidence_cards:
{[item.model_dump() for item in evidence_cards]}
""".strip()
