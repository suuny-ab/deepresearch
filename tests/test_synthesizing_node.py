from tests.conftest import FakeLLMClient

from deepresearch.nodes.synthesizing import make_synthesize_notes_node
from deepresearch.state import SearchResult, SubQuestion


def test_synthesize_notes_parses_notes():
    llm = FakeLLMClient([
        '{"notes":[{"subquestion_id":"q1","key_findings":["AI search summarizes results"],"source_urls":["https://example.com"],"confidence":"high"}]}'
    ])
    node = make_synthesize_notes_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="AI search summarizes results")],
        "errors": [],
    })

    assert result["notes"][0].confidence == "high"


def test_synthesize_notes_falls_back_when_llm_invents_source_url():
    llm = FakeLLMClient([
        '{"notes":[{"subquestion_id":"q1","key_findings":["Invented source"],"source_urls":["https://invented.example"],"confidence":"high"}]}'
    ])
    node = make_synthesize_notes_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="AI search summarizes results")],
        "errors": [],
    })

    assert result["notes"][0].confidence == "low"
    assert result["notes"][0].source_urls == ["https://example.com"]
    assert any("invalid source constraints" in error for error in result["errors"])
    assert any("https://invented.example" in error for error in result["errors"])


def test_synthesize_notes_falls_back_when_llm_uses_unknown_subquestion_id():
    llm = FakeLLMClient([
        '{"notes":[{"subquestion_id":"q2","key_findings":["Wrong subquestion"],"source_urls":["https://example.com"],"confidence":"high"}]}'
    ])
    node = make_synthesize_notes_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="AI search summarizes results")],
        "errors": [],
    })

    assert result["notes"][0].subquestion_id == "q1"
    assert result["notes"][0].confidence == "low"
    assert any("invalid source constraints" in error for error in result["errors"])
    assert any("q2" in error for error in result["errors"])
