"""Tests for subquestion agent and coordinator modules."""

import pytest

from deepresearch.agents.coordinator import (
    Contradiction,
    _claims_overlap,
    _detect_contradictions,
    _merge_cards,
    coordinate,
)
from deepresearch.agents.subquestion_agent import AgentResult, run_subquestion_agent
from deepresearch.state import (
    EvidenceCard, ExtractedClaim, SearchResult, SubQuestion,
)
from tests.conftest import FakeLLMClient

# ---------------------------------------------------------------------------
# Fake search client for agent tests
# ---------------------------------------------------------------------------


class FakeAgentSearchClient:
    def __init__(self):
        self.searches: list[tuple[str, str, int]] = []
        self.extracts: list[tuple[list[str], str]] = []

    def search(self, query: str, *, subquestion_id: str, max_results: int):
        self.searches.append((query, subquestion_id, max_results))
        return [
            SearchResult(
                subquestion_id=subquestion_id, query=query,
                title=f"Result for {query}", url=f"https://example.com/{subquestion_id}",
                content=f"Content for {query}", score=1.0,
            )
        ]

    def extract(self, urls, *, subquestion_id):
        self.extracts.append((urls, subquestion_id))
        from deepresearch.state import ExtractedSource
        return [
            ExtractedSource(
                subquestion_id=subquestion_id, url=url,
                title=f"Extracted {url}",
                raw_content=f"Full content from {url} for {subquestion_id}",
                extract_depth="basic", format="markdown",
            )
            for url in urls
        ]


# ---------------------------------------------------------------------------
# Agent tests
# ---------------------------------------------------------------------------

_CLAIMS_JSON = """```json
{"claims": [
    {"id": "c1", "subquestion_id": "q1", "claim": "Claim from source 1",
     "source_url": "https://example.com/q1", "source_title": "Source 1",
     "supporting_snippet": "...", "content_type": "extracted_content",
     "confidence": "high"}
]}
```"""

_CARDS_JSON = """```json
{"evidence_cards": [
    {"id": "c1", "subquestion_id": "q1", "claim": "Claim from source 1",
     "source_url": "https://example.com/q1", "source_title": "Source 1",
     "supporting_snippet": "...", "content_type": "extracted_content",
     "corroboration_level": "single_source", "corroborating_sources": [],
     "confidence": "high"}
]}
```"""


def test_agent_produces_evidence_cards():
    """Full agent run: search → extract → validate."""
    search_client = FakeAgentSearchClient()
    llm = FakeLLMClient([_CLAIMS_JSON, _CARDS_JSON])
    subq = SubQuestion(
        id="q1", question="What is AI search?",
        search_query="AI search trends", rationale="Understanding",
    )

    result = run_subquestion_agent(
        question="What is AI search?",
        subquestion=subq,
        search_client=search_client,
        llm=llm,
        results_per_query=2,
        max_sources=2,
    )

    assert result.subquestion_id == "q1"
    assert len(result.evidence_cards) == 1
    assert result.evidence_cards[0].id == "c1"
    assert len(search_client.searches) == 1
    assert len(search_client.extracts) == 1


def test_agent_handles_search_failure():
    """Agent returns empty result when all searches fail."""

    class FailingSearchClient:
        def search(self, query, *, subquestion_id, max_results):
            raise Exception("Search API error")

    subq = SubQuestion(
        id="q1", question="Test?", search_query="test", rationale="Test",
    )
    llm = FakeLLMClient([])

    result = run_subquestion_agent(
        question="Test?", subquestion=subq,
        search_client=FailingSearchClient(),
        llm=llm,
    )

    assert result.subquestion_id == "q1"
    assert result.evidence_cards == []
    assert len(result.errors) > 0


def test_agent_handles_llm_failure():
    """Agent returns empty cards when LLM fails."""
    search_client = FakeAgentSearchClient()

    class FailingLLMClient:
        def complete(self, prompt):
            raise Exception("LLM error")

    subq = SubQuestion(
        id="q1", question="Test?", search_query="test", rationale="Test",
    )

    result = run_subquestion_agent(
        question="Test?", subquestion=subq,
        search_client=search_client, llm=FailingLLMClient(),
    )

    assert result.subquestion_id == "q1"
    assert result.evidence_cards == []
    assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# Coordinator tests
# ---------------------------------------------------------------------------

def _make_card(_id, claim, sq_id, source_url, level="single_source"):
    return EvidenceCard(
        id=_id, subquestion_id=sq_id, claim=claim,
        source_url=source_url, source_title="Test Source",
        supporting_snippet="...", content_type="extracted_content",
        corroboration_level=level, corroborating_sources=[],
        confidence="medium",
    )


def test_merge_cards_deduplicates():
    """Coordinator deduplicates cards by id."""
    card1 = _make_card("c1", "Claim A", "q1", "https://a.com/q1")
    card2 = _make_card("c2", "Claim B", "q2", "https://b.com/q2")
    dup_card = _make_card("c1", "Claim A duplicate", "q1", "https://a.com/q1")

    results = [
        AgentResult(subquestion_id="q1", evidence_cards=[card1]),
        AgentResult(subquestion_id="q2", evidence_cards=[card2, dup_card]),
    ]

    merged = _merge_cards(results)
    assert len(merged) == 2  # dup_card not added
    ids = {c.id for c in merged}
    assert ids == {"c1", "c2"}


def test_cross_agent_corroboration():
    """Coordinator detects same fact from different agents/domains."""
    card1 = _make_card(
        "c1", "Solid-state batteries will reach mass production by 2027",
        "q1", "https://nature.com/battery", "single_source",
    )
    card2 = _make_card(
        "c2", "Solid-state batteries expected to reach mass production in 2027",
        "q2", "https://techreview.com/ssb", "single_source",
    )

    results = [
        AgentResult(subquestion_id="q1", evidence_cards=[card1]),
        AgentResult(subquestion_id="q2", evidence_cards=[card2]),
    ]

    coord_result = coordinate(results)

    # Both cards should have upgraded corroboration
    final_cards = {c.id: c for c in coord_result.evidence_cards}
    assert final_cards["c1"].corroboration_level != "single_source"
    assert final_cards["c2"].corroboration_level != "single_source"
    assert coord_result.cross_agent_corroborations > 0


def test_coordinator_handles_empty_results():
    """Coordinator returns empty result for no agent results."""
    result = coordinate([])
    assert result.evidence_cards == []
    assert result.contradictions == []


def test_claims_overlap_detection():
    """Word overlap threshold correctly identifies matching claims."""
    assert _claims_overlap(
        "Solid-state batteries will reach mass production by 2027",
        "Solid-state batteries expected to reach mass production in 2027",
    )
    assert not _claims_overlap(
        "Solid-state batteries are promising",
        "AI search engines use neural networks",
    )


def test_contradiction_detection():
    """Coordinator detects contradictory claims."""
    card1 = _make_card(
        "c1", "Solid-state batteries face significant cost barriers however",
        "q1", "https://a.com/ssb",
    )
    card2 = _make_card(
        "c2", "Solid-state batteries cost barriers may decrease rapidly but",
        "q2", "https://b.com/ssb",
    )

    results = [
        AgentResult(subquestion_id="q1", evidence_cards=[card1]),
        AgentResult(subquestion_id="q2", evidence_cards=[card2]),
    ]

    contradictions = _detect_contradictions(results)
    assert len(contradictions) >= 1
