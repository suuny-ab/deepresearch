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
