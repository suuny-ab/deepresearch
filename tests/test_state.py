import pytest
from pydantic import ValidationError

from deepresearch.state import ResearchNote, ReviewResult, SearchResult, SubQuestion


def test_subquestion_requires_core_fields():
    item = SubQuestion(
        id="q1",
        question="What changed in AI search?",
        search_query="AI search trends 2026",
        rationale="Establish context",
    )

    assert item.id == "q1"
    assert item.search_query == "AI search trends 2026"


def test_search_result_keeps_source_url():
    result = SearchResult(
        subquestion_id="q1",
        title="Report",
        url="https://example.com/report",
        content="Useful summary",
        score=0.8,
    )

    assert result.url == "https://example.com/report"
    assert result.score == 0.8


def test_search_result_no_longer_has_source_quality_fields():
    result = SearchResult(
        subquestion_id="q1",
        title="Report",
        url="https://example.com/report",
        content="Summary",
    )

    assert not hasattr(result, "source_type")
    assert not hasattr(result, "source_quality_score")
    assert not hasattr(result, "source_quality_reason")


def test_research_note_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        ResearchNote(
            subquestion_id="q1",
            key_findings=["Finding"],
            source_urls=["https://example.com"],
            confidence="certain",
        )


def test_review_result_score_range():
    review = ReviewResult(passed=True, score=86, issues=[], suggestions=[])

    assert review.score == 86

    with pytest.raises(ValidationError):
        ReviewResult(passed=False, score=101, issues=[], suggestions=[])


def test_research_state_accepts_report_status():
    from deepresearch.state import ResearchState

    state: ResearchState = {"question": "AI search", "report_status": "failed_validation"}

    assert state["report_status"] == "failed_validation"


def test_research_state_accepts_validation_retry_metadata():
    from deepresearch.state import ResearchState

    state: ResearchState = {
        "question": "AI search",
        "rewrite_attempted": True,
        "validation_attempts": 2,
        "validation_failures": [
            {"reason": "missing_body_citations", "message": "正文没有使用编号引用。"},
            {"reason": "unused_sources", "message": "Sources 中存在未被正文引用的编号。"},
        ],
    }

    assert state["rewrite_attempted"] is True
    assert state["validation_attempts"] == 2
    assert len(state["validation_failures"]) == 2


def test_subquestion_accepts_multiple_search_queries():
    from deepresearch.state import SubQuestion

    item = SubQuestion(
        id="q1",
        question="AI 搜索技术趋势是什么？",
        search_query="AI 搜索 技术趋势",
        search_queries=[
            "AI 搜索 技术趋势 RAG",
            "AI search technology trends RAG 2026",
        ],
        rationale="覆盖中英文来源",
    )

    assert item.search_queries == [
        "AI 搜索 技术趋势 RAG",
        "AI search technology trends RAG 2026",
    ]


def test_subquestion_normalizes_missing_search_queries_from_search_query():
    from deepresearch.state import SubQuestion

    item = SubQuestion(
        id="q1",
        question="What is AI search?",
        search_query="AI search definition",
        rationale="Background",
    )

    assert item.search_queries == ["AI search definition"]


def test_evidence_card_has_corroboration_fields_not_source_quality():
    from deepresearch.state import EvidenceCard

    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="RAG remains important for AI search.",
        source_url="https://example.com/report",
        source_title="AI Search Report",
        supporting_snippet="RAG remains a core architecture for AI search systems.",
        content_type="extracted_content",
        corroboration_level="weakly_corroborated",
        corroborating_sources=["https://other-domain.com/article"],
        confidence="high",
    )

    assert card.source_url == "https://example.com/report"
    assert card.supporting_snippet
    assert card.corroboration_level == "weakly_corroborated"
    assert card.corroborating_sources == ["https://other-domain.com/article"]
    assert not hasattr(card, "source_type")
    assert not hasattr(card, "source_quality_score")
    assert not hasattr(card, "evidence_reliability")


def test_evidence_card_defaults_corroboration_to_single_source():
    from deepresearch.state import EvidenceCard

    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="Single source claim.",
        source_url="https://example.com/report",
        source_title="Report",
        supporting_snippet="Single source claim.",
        content_type="extracted_content",
        confidence="medium",
    )

    assert card.corroboration_level == "single_source"
    assert card.corroborating_sources == []


def test_extracted_source_no_longer_has_source_quality_fields():
    from deepresearch.state import ExtractedSource

    source = ExtractedSource(
        subquestion_id="q1",
        url="https://example.com/a",
        title="Source A",
        raw_content="Full content.",
    )

    assert source.url == "https://example.com/a"
    assert source.raw_content == "Full content."
    assert not hasattr(source, "source_type")
    assert not hasattr(source, "source_quality_score")
    assert not hasattr(source, "source_quality_reason")


def test_extracted_claim_has_no_corroboration_fields():
    from deepresearch.state import ExtractedClaim

    claim = ExtractedClaim(
        id="e1",
        subquestion_id="q1",
        claim="RAG remains important.",
        source_url="https://example.com/a",
        source_title="Source A",
        supporting_snippet="RAG remains important.",
        content_type="extracted_content",
        confidence="high",
    )

    assert claim.claim == "RAG remains important."
    assert not hasattr(claim, "corroboration_level")
    assert not hasattr(claim, "corroborating_sources")


def test_research_state_accepts_extracted_claims():
    from deepresearch.state import ExtractedClaim, ResearchState

    state: ResearchState = {
        "question": "AI search",
        "extracted_claims": [
            ExtractedClaim(
                id="e1", subquestion_id="q1",
                claim="RAG remains important.",
                source_url="https://example.com/a", source_title="Source A",
                supporting_snippet="RAG remains important.",
                content_type="extracted_content", confidence="high",
            )
        ],
    }

    assert len(state["extracted_claims"]) == 1


def test_research_state_no_longer_has_extracted_sources():
    from deepresearch.state import ResearchState

    state: ResearchState = {
        "question": "AI search",
        "evidence_cards": [],
        "evidence_metrics": {},
    }

    assert "extracted_sources" not in state
