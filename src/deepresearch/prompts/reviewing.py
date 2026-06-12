from deepresearch.state import EvidenceCard


def build_reviewing_prompt(
    question: str,
    report_markdown: str,
    evidence_cards: list[EvidenceCard],
) -> str:
    card_summaries = []
    for c in evidence_cards:
        card_summaries.append(
            f"- [{c.id}] {c.claim[:120]}"
            f"  (corroboration: {c.corroboration_level},"
            f"  source: {c.source_url})"
        )

    cards_text = "\n".join(card_summaries) if card_summaries else "- None"

    return f"""
Review this Markdown research report. Score it on five dimensions using the rubric below. First assign a score (0-100) for each dimension, then compute the weighted total.

Scoring Rubric:

1. Source Support (weight 30%)
   90-100: All key conclusions use numbered citations from EvidenceCards
   60-89:  Most key conclusions cite sources; a few unsupported claims
   30-59:  Many unsupported claims throughout
   0-29:   Few or no citations

2. Cross-Validation Coverage (weight 20%)
   90-100: Main conclusions backed by strongly/weakly corroborated cards
   60-89:  Some conclusions have cross-validation, some single-source
   30-59:  Most conclusions from single sources
   0-29:   No effective cross-validation

3. Completeness (weight 20%)
   90-100: Covers core arguments from all subquestions
   60-89:  Covers most subquestions, some angles missed
   30-59:  Important subquestions missing
   0-29:   Only covers a fraction of the question

4. Structure & Clarity (weight 15%)
   90-100: All required sections present, logical flow
   60-89:  Sections present but some sections thin
   30-59:  Required sections missing
   0-29:   Disorganized

5. Relevance & Focus (weight 15%)
   90-100: All content directly addresses the research question
   60-89:  Mostly relevant, occasional tangents
   30-59:  Significant off-topic content
   0-29:   Largely unrelated to the question

Compute: total = (source_support * 0.30) + (corroboration * 0.20) + (completeness * 0.20) + (structure * 0.15) + (relevance * 0.15)
Round to the nearest integer.

EvidenceCards used in this report (with corroboration status):
{cards_text}

Return only JSON in this exact shape:
{{"passed":true,"score":88,"issues":["..."],"suggestions":["..."]}}
Score must be an integer from 0 to 100.

Original question:
{question}

Report:
{report_markdown}
""".strip()
