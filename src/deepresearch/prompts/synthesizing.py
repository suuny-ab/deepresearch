from deepresearch.state import EvidenceCard, SubQuestion


def build_synthesizing_prompt(question: str, subquestions: list[SubQuestion], evidence_cards: list[EvidenceCard]) -> str:
    strong = [card for card in evidence_cards if card.corroboration_level == "strongly_corroborated"]
    weak = [card for card in evidence_cards if card.corroboration_level == "weakly_corroborated"]
    single = [card for card in evidence_cards if card.corroboration_level == "single_source"]

    sections = []

    if strong:
        sections.append("Strongly corroborated claims (3+ independent sources agree):")
        for card in strong:
            sections.append(f"- [{card.id}] {card.claim} (supported by: {', '.join(card.corroborating_sources)})")
        sections.append("")

    if weak:
        sections.append("Weakly corroborated claims (2 independent sources agree):")
        for card in weak:
            sections.append(f"- [{card.id}] {card.claim} (supported by: {', '.join(card.corroborating_sources)})")
        sections.append("")

    if single:
        sections.append("Single-source claims (only one source mentions this):")
        for card in single:
            sections.append(f"- [{card.id}] {card.claim} (source: {card.source_url})")
        sections.append("")

    stratified = "\n".join(sections)

    return f"""
You are a careful research analyst. Use only the supplied EvidenceCards.
Only summarize claims present in EvidenceCards. Do not introduce facts not supported by EvidenceCards.
Low corroboration evidence cannot support high confidence findings.
Every finding must be traceable to one of the supplied EvidenceCard source_url values.

Guidelines:
- Strongly corroborated claims form the backbone of findings
- Single-source claims may be included but should be noted as lower confidence
- Never elevate a single-source claim to a key finding unless it is uniquely
  important and the source is a primary source for that specific fact

Return only JSON in this exact shape:
{{"notes":[{{"subquestion_id":"q1","key_findings":["..."],"source_urls":["https://..."],"confidence":"low|medium|high"}}]}}

Original question:
{question}

Subquestions:
{[item.model_dump() for item in subquestions]}

{stratified}
""".strip()
