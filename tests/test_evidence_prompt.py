from deepresearch.prompts.evidence import build_validation_prompt
from deepresearch.state import ExtractedClaim, ExtractedSource


def test_validation_prompt_scoped_to_single_subquestion():
    claims = [
        ExtractedClaim(
            id="e1", subquestion_id="q1",
            claim="RAG remains important.",
            source_url="https://example.com/a", source_title="A",
            supporting_snippet="RAG remains important.", content_type="extracted_content", confidence="high",
        ),
    ]
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://example.com/a", title="A", raw_content="RAG remains important."),
        ExtractedSource(subquestion_id="q1", url="https://other.example/b", title="B", raw_content="RAG is key."),
    ]

    prompt = build_validation_prompt(
        sq_id="q1", sq_question="What is AI search?",
        claims=claims, sources=sources,
    )

    assert "q1" in prompt
    assert "What is AI search?" in prompt
    assert "corroboration_level" in prompt
    assert "strongly_corroborated" in prompt


def test_validation_prompt_includes_corroboration_rules():
    claims = [
        ExtractedClaim(
            id="e1", subquestion_id="q1", claim="Claim.",
            source_url="https://a.example/x", source_title="X",
            supporting_snippet="Claim.", content_type="extracted_content",
            confidence="high",
        ),
    ]
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://a.example/x", title="X", raw_content="Claim."),
        ExtractedSource(subquestion_id="q1", url="https://b.example/y", title="Y", raw_content="Claim too."),
    ]

    prompt = build_validation_prompt("q1", "Test?", claims, sources)

    assert "different domain" in prompt.lower()
    assert "single_source" in prompt
    assert "weakly_corroborated" in prompt
    assert "corroborating_sources" in prompt


def test_validation_prompt_does_not_ask_to_extract_new_claims():
    claims = [
        ExtractedClaim(
            id="e1", subquestion_id="q1", claim="Claim.",
            source_url="https://a.example/x", source_title="X",
            supporting_snippet="Claim.", content_type="extracted_content",
            confidence="high",
        ),
    ]
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://a.example/x", title="X", raw_content="Claim."),
    ]

    prompt = build_validation_prompt("q1", "Test?", claims, sources)

    assert "do not create new claims" in prompt.lower() or "do not extract" in prompt.lower()
