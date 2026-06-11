from tests.conftest import FakeLLMClient

from deepresearch.nodes.synthesizing import make_synthesize_notes_node
from deepresearch.state import EvidenceCard, SearchResult, SubQuestion


def test_synthesize_notes_parses_notes():
    llm = FakeLLMClient([
        '{"notes":[{"subquestion_id":"q1","key_findings":["AI search summarizes results"],"source_urls":["https://example.com"],"confidence":"high"}]}'
    ])
    node = make_synthesize_notes_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [],
        "evidence_cards": [EvidenceCard(
            id="e1",
            subquestion_id="q1",
            claim="AI search summarizes results",
            source_url="https://example.com",
            source_title="Source",
            supporting_snippet="AI search summarizes results",
            content_type="extracted_content",
            source_type="industry_report",
            source_quality_score=85,
            evidence_reliability="high",
            confidence="high",
        )],
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
        "search_results": [SearchResult(subquestion_id="q1", title="Search only", url="https://not-evidence.example", content="Search-only content")],
        "evidence_cards": [EvidenceCard(
            id="e1",
            subquestion_id="q1",
            claim="AI search summarizes results",
            source_url="https://example.com",
            source_title="Source",
            supporting_snippet="AI search summarizes results",
            content_type="extracted_content",
            source_type="industry_report",
            source_quality_score=85,
            evidence_reliability="high",
            confidence="high",
        )],
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
        "search_results": [],
        "evidence_cards": [EvidenceCard(
            id="e1",
            subquestion_id="q1",
            claim="AI search summarizes results",
            source_url="https://example.com",
            source_title="Source",
            supporting_snippet="AI search summarizes results",
            content_type="extracted_content",
            source_type="industry_report",
            source_quality_score=85,
            evidence_reliability="high",
            confidence="high",
        )],
        "errors": [],
    })

    assert result["notes"][0].subquestion_id == "q1"
    assert result["notes"][0].confidence == "low"
    assert any("invalid source constraints" in error for error in result["errors"])
    assert any("q2" in error for error in result["errors"])


def test_synthesize_notes_uses_evidence_cards():
    llm = FakeLLMClient([
        '{"notes":[{"subquestion_id":"q1","key_findings":["RAG remains important."],"source_urls":["https://example.com/a"],"confidence":"high"}]}'
    ])
    node = make_synthesize_notes_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [
            SubQuestion(
                id="q1",
                question="What?",
                search_query="AI search",
                search_queries=["AI search"],
                rationale="Background",
            )
        ],
        "search_results": [],
        "evidence_cards": [
            EvidenceCard(
                id="e1",
                subquestion_id="q1",
                claim="RAG remains important.",
                source_url="https://example.com/a",
                source_title="A",
                supporting_snippet="RAG remains important.",
                content_type="extracted_content",
                source_type="industry_report",
                source_quality_score=85,
                evidence_reliability="high",
                confidence="high",
            )
        ],
        "errors": [],
    })

    assert result["notes"][0].source_urls == ["https://example.com/a"]
    assert "EvidenceCard" in llm.prompts[0] or "evidence_cards" in llm.prompts[0]


def test_synthesize_notes_without_evidence_cards_returns_low_confidence_fallback():
    llm = FakeLLMClient([
        '{"notes":[{"subquestion_id":"q1","key_findings":["Strong unsupported claim"],"source_urls":["https://example.com"],"confidence":"high"}]}'
    ])
    node = make_synthesize_notes_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Search only", url="https://example.com", content="Search-only content")],
        "evidence_cards": [],
        "errors": [],
    })

    assert result["notes"][0].confidence == "low"
    assert result["notes"][0].source_urls == []
    assert "No EvidenceCards were available" in result["notes"][0].key_findings[0]
    assert any("No EvidenceCards available" in error for error in result["errors"])
