import pytest

from deepresearch.config import AppConfig
from deepresearch.state import ExtractedSource, SearchResult

# Reuse FakeLLMClient from conftest
from tests.conftest import FakeLLMClient


class FakeSearchClient:
    """Fake search client that supports both search() and extract()."""

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
                url=f"https://example.com/{subquestion_id}",
                content="AI search engines use RAG and generated answers to improve relevance.",
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
                raw_content="AI search engines use RAG and generated answers to improve relevance.",
            )
            for url in urls
        ]


# ---------------------------------------------------------------------------
# LLM response sequence for a full pipeline run (1 subquestion)
# ---------------------------------------------------------------------------
# plan_research → Phase 1 extraction → Phase 2 validation (1 subquestion)
# → write_report → review_report
# = 5 LLM calls
_MOCK_RESPONSES_FULL_RUN = [
    # plan_research
    '{"subquestions":[{"id":"q1","question":"What is AI search?","search_query":"AI search trends","search_queries":["AI 搜索 发展趋势","AI search engine trends"],"rationale":"Understand the core technology and market trends"}]}',
    # Phase 1: extraction
    '{"claims":[{"id":"e1","subquestion_id":"q1","claim":"AI search engines use RAG to improve relevance.","source_url":"https://example.com/q1","source_title":"Test Source","supporting_snippet":"AI search engines use RAG and generated answers to improve relevance.","content_type":"extracted_content","confidence":"high"}]}',
    # Phase 2: validation for q1
    '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"AI search engines use RAG to improve relevance.","source_url":"https://example.com/q1","source_title":"Test Source","supporting_snippet":"AI search engines use RAG and generated answers to improve relevance.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
    # write_report
    '# AI Search Trends\n\nAI search engines use RAG to improve relevance.[1]\n\n## Sources\n\n[1] https://example.com/q1',
    # review_report
    '{"passed":true,"score":88,"issues":[],"suggestions":[]}',
]


def test_build_agent_returns_callable():
    """build_agent should return a callable object."""
    from deepresearch.runner import build_agent

    llm = FakeLLMClient(list(_MOCK_RESPONSES_FULL_RUN))
    search = FakeSearchClient()

    agent = build_agent(
        llm=llm,
        search=search,
        max_subquestions=5,
        results_per_query=5,
    )

    assert callable(agent)


def test_build_agent_invokes_all_nodes_and_produces_expected_fields(tmp_path):
    """A full pipeline run should produce all expected state keys."""
    from deepresearch.runner import build_agent

    llm = FakeLLMClient(list(_MOCK_RESPONSES_FULL_RUN))
    search = FakeSearchClient()

    agent = build_agent(
        llm=llm,
        search=search,
        max_subquestions=5,
        results_per_query=5,
        output_dir=str(tmp_path),
    )

    result = agent("AI search trends")

    # All expected state fields should be present
    assert result["question"] == "AI search trends"
    assert len(result["subquestions"]) == 1
    assert result["subquestions"][0].id == "q1"
    assert len(result["search_results"]) >= 1
    assert len(result["extracted_claims"]) == 1
    assert len(result["evidence_cards"]) == 1
    assert result["report_markdown"]
    assert result["report_status"] == "success"
    assert result["output_path"]
    assert result["review"].score == 88


def test_build_agent_preserves_errors_list():
    """Errors accumulated during the pipeline should be in the final state."""
    from deepresearch.runner import build_agent

    llm = FakeLLMClient(list(_MOCK_RESPONSES_FULL_RUN))
    search = FakeSearchClient()

    agent = build_agent(
        llm=llm,
        search=search,
        max_subquestions=5,
        results_per_query=5,
    )

    result = agent("test question")

    # errors list should exist (even if empty)
    assert "errors" in result
    assert isinstance(result["errors"], list)


def test_build_agent_passes_config_values_through():
    """build_agent should respect max_subquestions and results_per_query parameters."""
    from deepresearch.runner import build_agent

    llm = FakeLLMClient(list(_MOCK_RESPONSES_FULL_RUN))
    search = FakeSearchClient()

    agent = build_agent(
        llm=llm,
        search=search,
        max_subquestions=3,
        results_per_query=7,
    )

    result = agent("test")

    # max_subquestions=3 is passed to plan_research node factory,
    # results_per_query=7 is passed to search_web node factory.
    # Both are consumed via closure — we verify the pipeline completes without error.
    assert result["report_status"] == "success"


def test_cli_imports_build_agent():
    """Smoke test: cli.py should import build_agent from runner (or continue working)."""
    from deepresearch.cli import app as _cli_app
    assert _cli_app is not None


# ---------------------------------------------------------------------------
# Multi-agent architecture tests
# ---------------------------------------------------------------------------

# FakeSearchClient returns URLs like "https://example.com/{subquestion_id}"
_MOCK_MULTI_AGENT_RESPONSES = [
    # plan_research (1 subquestion)
    '{"subquestions":[{"id":"q1","question":"Tech","search_query":"AI tech","search_queries":["AI technology"],"rationale":"Tech"}]}',
    # Agent q1 Phase 1: extraction
    '{"claims":[{"id":"e1","subquestion_id":"q1","claim":"RAG improves search accuracy.","source_url":"https://example.com/q1","source_title":"Test Source","supporting_snippet":"AI search engines use RAG.","content_type":"extracted_content","confidence":"high"}]}',
    # Agent q1 Phase 2: validation
    '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"RAG improves search accuracy.","source_url":"https://example.com/q1","source_title":"Test Source","supporting_snippet":"AI search engines use RAG.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
    # write_report
    '# AI Search Report\n\nRAG improves search accuracy.[1]\n\n## Sources\n\n[1] https://example.com/q1',
    # review_report
    '{"passed":true,"score":85,"issues":[],"suggestions":[]}',
]


def test_build_agent_multi_agent_architecture(tmp_path):
    """Multi-agent mode should build and produce expected state keys."""
    from deepresearch.runner import build_agent

    llm = FakeLLMClient(list(_MOCK_MULTI_AGENT_RESPONSES))
    search = FakeSearchClient()

    agent = build_agent(
        llm=llm,
        search=search,
        max_subquestions=5,
        results_per_query=3,
        output_dir=str(tmp_path),
        architecture="multi-agent",
    )

    result = agent("AI search trends")

    assert result["question"] == "AI search trends"
    assert len(result["subquestions"]) == 1
    assert len(result["evidence_cards"]) == 1
    assert result["report_markdown"]
    assert result["report_status"] == "success"
    assert result["review"].score == 85


def test_multi_agent_produces_coordinator_state(tmp_path):
    """Multi-agent mode should populate coordinator-specific state keys."""
    from deepresearch.runner import build_agent

    llm = FakeLLMClient(list(_MOCK_MULTI_AGENT_RESPONSES))
    search = FakeSearchClient()

    agent = build_agent(
        llm=llm,
        search=search,
        max_subquestions=5,
        output_dir=str(tmp_path),
        architecture="multi-agent",
    )

    result = agent("test")

    # Coordinator state should exist
    assert "_agent_results" in result
    assert "_contradictions_text" in result
    assert "_cross_agent_corroborations" in result

