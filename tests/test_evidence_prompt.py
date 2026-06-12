from deepresearch.prompts.evidence import build_evidence_prompt
from deepresearch.state import ExtractedSource, SubQuestion


def test_evidence_prompt_requires_evidence_cards():
    source = ExtractedSource(
        subquestion_id="q1",
        url="https://example.com/a",
        title="Source A",
        raw_content="RAG remains important for AI search.",
    )
    subquestions = [
        SubQuestion(id="q1", question="What is AI search?", search_query="q", search_queries=["q"], rationale="r"),
    ]

    prompt = build_evidence_prompt("AI search", [source], subquestions)

    assert "EvidenceCard" in prompt
    assert "supporting_snippet" in prompt
    assert "Do not create claims not supported by the source text" in prompt
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
    subquestions = [
        SubQuestion(id="q1", question="What is AI search?", search_query="q", search_queries=["q"], rationale="r"),
    ]

    prompt = build_evidence_prompt("AI search", sources, subquestions)

    assert "corroboration_level" in prompt
    assert "single_source" in prompt
    assert "weakly_corroborated" in prompt
    assert "strongly_corroborated" in prompt
    assert "different domain" in prompt.lower() or "DIFFERENT domain" in prompt
    assert "corroborating_sources" in prompt


def test_evidence_prompt_groups_sources_by_subquestion():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="RAG is important.",
        ),
        ExtractedSource(
            subquestion_id="q2",
            url="https://other.example/b",
            title="Source B",
            raw_content="AI search market growing.",
        ),
    ]
    subquestions = [
        SubQuestion(id="q1", question="Core tech trends?", search_query="q1", search_queries=["q1"], rationale="tech"),
        SubQuestion(id="q2", question="Market competition?", search_query="q2", search_queries=["q2"], rationale="market"),
    ]

    prompt = build_evidence_prompt("AI search", sources, subquestions)

    assert "Core tech trends?" in prompt
    assert "Market competition?" in prompt
    assert "q1:" in prompt
    assert "q2:" in prompt
    assert "https://example.com/a" in prompt
    assert "https://other.example/b" in prompt


def test_evidence_prompt_backward_compatible_with_no_subquestions():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="Content.",
        ),
    ]

    prompt = build_evidence_prompt("AI search", sources, subquestions=[])

    assert "https://example.com/a" in prompt
    assert "EvidenceCard" in prompt
