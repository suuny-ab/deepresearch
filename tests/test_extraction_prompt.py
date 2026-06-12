from deepresearch.prompts.extraction import build_extraction_prompt
from deepresearch.state import ExtractedSource, SubQuestion


def test_extraction_prompt_contains_no_corroboration_instructions():
    sources = [
        ExtractedSource(
            subquestion_id="q1", url="https://example.com/a",
            title="Source A", raw_content="RAG remains important for AI search.",
        ),
    ]
    subquestions = [
        SubQuestion(id="q1", question="What is AI search?", search_query="q", search_queries=["q"], rationale="r"),
    ]

    prompt = build_extraction_prompt("AI search", sources, subquestions)

    assert "corroboration" not in prompt.lower()
    assert "cross-valid" not in prompt.lower()
    assert "claim" in prompt.lower()
    assert "supporting_snippet" in prompt
    assert "https://example.com/a" in prompt


def test_extraction_prompt_encourages_max_claims():
    sources = [
        ExtractedSource(
            subquestion_id="q1", url="https://example.com/a",
            title="Source A", raw_content="RAG is important. Vector search is trending.",
        ),
    ]
    subquestions = [
        SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r"),
    ]

    prompt = build_extraction_prompt("AI search", sources, subquestions)

    assert "as many" in prompt.lower() or "every" in prompt.lower() or "all" in prompt.lower()


def test_extraction_prompt_has_quantity_guideline():
    sources = [
        ExtractedSource(
            subquestion_id="q1", url="https://example.com/a",
            title="Source A", raw_content="RAG is important for AI search.",
        ),
    ]
    subquestions = [
        SubQuestion(id="q1", question="What is AI search?", search_query="q", search_queries=["q"], rationale="r"),
    ]

    prompt = build_extraction_prompt("AI search", sources, subquestions)

    assert "at least 2-4 claims per source" in prompt


def test_extraction_prompt_groups_sources_by_subquestion():
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://example.com/a", title="A", raw_content="Content A."),
        ExtractedSource(subquestion_id="q2", url="https://other.example/b", title="B", raw_content="Content B."),
    ]
    subquestions = [
        SubQuestion(id="q1", question="Tech trends?", search_query="q1", search_queries=["q1"], rationale="tech"),
        SubQuestion(id="q2", question="Market?", search_query="q2", search_queries=["q2"], rationale="market"),
    ]

    prompt = build_extraction_prompt("AI search", sources, subquestions)

    assert "Tech trends?" in prompt
    assert "Market?" in prompt
