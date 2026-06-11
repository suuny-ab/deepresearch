from deepresearch.prompts.evidence import build_evidence_prompt
from deepresearch.state import ExtractedSource


def test_evidence_prompt_requires_evidence_cards():
    source = ExtractedSource(
        subquestion_id="q1",
        url="https://example.com/a",
        title="Source A",
        raw_content="RAG remains important for AI search.",
        source_type="industry_report",
        source_quality_score=85,
        source_quality_reason="Report-like source",
    )

    prompt = build_evidence_prompt("AI search", [source])

    assert "EvidenceCard" in prompt
    assert "supporting_snippet" in prompt
    assert "Do not create claims not supported by the source text" in prompt
    assert "copy the supplied `url` value into EvidenceCard `source_url`" in prompt
    assert "https://example.com/a" in prompt
