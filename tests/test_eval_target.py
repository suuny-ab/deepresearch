import pytest

from deepresearch.state import ExtractedSource, SearchResult
from tests.conftest import FakeLLMClient

# ---------------------------------------------------------------------------
# Reuse the same FakeSearchClient pattern from test_runner.py
# ---------------------------------------------------------------------------


class FakeSearchClient:
    def __init__(self):
        self.search_calls: list[dict] = []
        self.extract_calls: list[dict] = []

    def search(self, query: str, *, subquestion_id: str, max_results: int):
        self.search_calls.append(
            {"query": query, "subquestion_id": subquestion_id, "max_results": max_results}
        )
        return [
            SearchResult(
                subquestion_id=subquestion_id,
                query=query,
                title="Test Source",
                url="https://example.com/test-source",
                content="AI search engines use RAG to improve relevance.",
                score=0.95,
            )
        ]

    def extract(self, urls: list[str], *, subquestion_id: str):
        self.extract_calls.append({"urls": list(urls), "subquestion_id": subquestion_id})
        return [
            ExtractedSource(
                subquestion_id=subquestion_id,
                title="Test Source",
                url=url,
                raw_content="AI search engines use RAG to improve relevance.",
            )
            for url in urls
        ]


# LLM responses for a full pipeline: plan → phase1 → phase2 → write → review
_MOCK = [
    '{"subquestions":[{"id":"q1","question":"What is AI search?","search_query":"AI search","search_queries":["AI search"],"rationale":"Core"}]}',
    '{"claims":[{"id":"e1","subquestion_id":"q1","claim":"RAG improves relevance.","source_url":"https://example.com/test-source","source_title":"Test Source","supporting_snippet":"AI search engines use RAG to improve relevance.","content_type":"extracted_content","confidence":"high"}]}',
    '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"RAG improves relevance.","source_url":"https://example.com/test-source","source_title":"Test Source","supporting_snippet":"AI search engines use RAG to improve relevance.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
    "# Report\n\nRAG improves relevance.[1]\n\n## Sources\n\n[1] https://example.com/test-source",
    '{"passed":true,"score":90,"issues":[],"suggestions":[]}',
]


# ---------------------------------------------------------------------------
# Tests for make_target
# ---------------------------------------------------------------------------


def test_make_target_returns_callable(tmp_path):
    """make_target should accept an agent and return a callable with the
    (inputs: dict) -> dict signature expected by langsmith.evaluate()."""
    from deepresearch.runner import build_agent
    from deepresearch.eval_target import make_target

    agent = build_agent(
        llm=FakeLLMClient(list(_MOCK)),
        search=FakeSearchClient(),
        max_subquestions=5,
        results_per_query=5,
        output_dir=str(tmp_path),
    )
    target = make_target(agent)
    assert callable(target)


def test_make_target_preserves_question(tmp_path):
    """The output dict must echo back the input question for traceability."""
    from deepresearch.runner import build_agent
    from deepresearch.eval_target import make_target

    agent = build_agent(
        llm=FakeLLMClient(list(_MOCK)),
        search=FakeSearchClient(),
        max_subquestions=5,
        results_per_query=5,
        output_dir=str(tmp_path),
    )
    target = make_target(agent)

    result = target({"question": "AI search trends"})

    assert result["question"] == "AI search trends"


def test_make_target_output_has_required_keys(tmp_path):
    """Output must include all keys that downstream evaluators depend on."""
    from deepresearch.runner import build_agent
    from deepresearch.eval_target import make_target

    agent = build_agent(
        llm=FakeLLMClient(list(_MOCK)),
        search=FakeSearchClient(),
        max_subquestions=5,
        results_per_query=5,
        output_dir=str(tmp_path),
    )
    target = make_target(agent)
    result = target({"question": "AI search"})

    required = {
        "question",
        "report",
        "evidence_cards",
        "search_results",
        "subquestions",
        "extracted_claims",
        "citation_passed",
        "review_score",
        "review_issues",
        "review_suggestions",
        "errors",
        "output_path",
    }
    missing = required - set(result)
    assert not missing, f"Missing output keys: {missing}"


def test_make_target_citation_passed_is_bool(tmp_path):
    """citation_passed must be a boolean for downstream gating checks."""
    from deepresearch.runner import build_agent
    from deepresearch.eval_target import make_target

    agent = build_agent(
        llm=FakeLLMClient(list(_MOCK)),
        search=FakeSearchClient(),
        max_subquestions=5,
        results_per_query=5,
        output_dir=str(tmp_path),
    )
    target = make_target(agent)
    result = target({"question": "AI search"})

    assert isinstance(result["citation_passed"], bool)


def test_make_target_evidence_cards_are_serializable(tmp_path):
    """evidence_cards must be a list of plain dicts (already model_dump'd),
    so LangSmith can store them without Pydantic serialization issues."""
    from deepresearch.runner import build_agent
    from deepresearch.eval_target import make_target

    agent = build_agent(
        llm=FakeLLMClient(list(_MOCK)),
        search=FakeSearchClient(),
        max_subquestions=5,
        results_per_query=5,
        output_dir=str(tmp_path),
    )
    target = make_target(agent)
    result = target({"question": "AI search"})

    cards = result["evidence_cards"]
    assert isinstance(cards, list), "evidence_cards must be a list"
    assert len(cards) >= 1, "Expected at least 1 evidence card"
    assert isinstance(cards[0], dict), "Each evidence card must be a plain dict"
    assert "id" in cards[0]
    assert "claim" in cards[0]
    assert "corroboration_level" in cards[0]
