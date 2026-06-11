from deepresearch.prompts.evidence import build_evidence_prompt
from deepresearch.state import ExtractedSource


def test_evidence_prompt_requires_evidence_cards():
    source = ExtractedSource(
        subquestion_id="q1",
        url="https://example.com/a",
        title="Source A",
        raw_content="RAG remains important for AI search.",
    )

    prompt = build_evidence_prompt("AI search", [source])

    assert "EvidenceCard" in prompt
    assert "supporting_snippet" in prompt
    assert "Do not create claims not supported by the source text" in prompt
    assert "copy the supplied `url` value into EvidenceCard `source_url`" in prompt
    assert "https://example.com/a" in prompt


def test_evidence_prompt_includes_cross_validation_instructions():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="RAG remains important.",
        ),
        ExtractedSource(
            subquestion_id="q1",
            url="https://other.example/b",
            title="Source B",
            raw_content="RAG is still important for search.",
        ),
    ]

    prompt = build_evidence_prompt("AI search", sources)

    assert "corroboration_level" in prompt
    assert "single_source" in prompt
    assert "weakly_corroborated" in prompt
    assert "strongly_corroborated" in prompt
    assert "different domain" in prompt.lower() or "DIFFERENT domain" in prompt
    assert "corroborating_sources" in prompt


def test_evidence_prompt_reflects_content_type():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="Summary only",
        ),
    ]

    prompt = build_evidence_prompt("AI search", sources)

    assert "content_type" in prompt
    assert "search_content" in prompt
    assert "extracted_content" in prompt
