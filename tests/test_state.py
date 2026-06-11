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


def test_search_result_accepts_query_and_source_quality_fields():
    from deepresearch.state import SearchResult

    item = SearchResult(
        subquestion_id="q1",
        query="AI search trends",
        title="Report",
        url="https://example.com/report",
        content="Summary",
        source_type="industry_report",
        source_quality_score=85,
        source_quality_reason="Report-like source",
    )

    assert item.query == "AI search trends"
    assert item.source_type == "industry_report"
    assert item.source_quality_score == 85


def test_evidence_card_model_requires_traceable_fields():
    from deepresearch.state import EvidenceCard

    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="RAG remains important for AI search.",
        source_url="https://example.com/report",
        source_title="AI Search Report",
        supporting_snippet="RAG remains a core architecture for AI search systems.",
        content_type="extracted_content",
        source_type="industry_report",
        source_quality_score=85,
        evidence_reliability="high",
        confidence="high",
    )

    assert card.source_url == "https://example.com/report"
    assert card.supporting_snippet
    assert card.evidence_reliability == "high"
