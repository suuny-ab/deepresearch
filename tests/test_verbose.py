from deepresearch.state import ResearchNote, ReviewResult, SearchResult, SubQuestion
from deepresearch.verbose import format_verbose_summary


def test_format_verbose_summary_includes_compact_workflow_details():
    state = {
        "subquestions": [SubQuestion(id="q1", question="What is AI search?", search_query="AI search", rationale="Background")],
        "search_results": [
            SearchResult(subquestion_id="q1", title="A", url="https://example.com/a", content="Long content should not appear"),
            SearchResult(subquestion_id="q1", title="B", url="https://example.com/b", content="More long content should not appear"),
        ],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding 1", "Finding 2"], source_urls=["https://example.com/a"], confidence="high")],
        "review": ReviewResult(passed=True, score=92, issues=[], suggestions=["Add examples"]),
        "errors": ["One warning"],
    }

    summary = format_verbose_summary(state)

    assert "Workflow details:" in summary
    assert "Subquestions:" in summary
    assert "What is AI search?" in summary
    assert "query: AI search" in summary
    assert "Search results:" in summary
    assert "q1: 2 result(s)" in summary
    assert "Research notes:" in summary
    assert "q1: confidence=high, findings=2, sources=1" in summary
    assert "Review:" in summary
    assert "score: 92" in summary
    assert "Errors:" in summary
    assert "One warning" in summary
    assert "Long content should not appear" not in summary


def test_format_verbose_summary_includes_validation_retry_metadata():
    state = {
        "report_status": "failed_validation",
        "rewrite_attempted": True,
        "validation_attempts": 2,
        "validation_failures": [
            {"reason": "missing_body_citations", "message": "正文没有使用编号引用。"},
            {"reason": "unused_sources", "message": "Sources 中存在未被正文引用的编号。"},
        ],
    }

    summary = format_verbose_summary(state)

    assert "Report validation:" in summary
    assert "rewrite_attempted: True" in summary
    assert "validation_attempts: 2" in summary
    assert "final_status: failed_validation" in summary
    assert "attempt 1: missing_body_citations" in summary
    assert "attempt 2: unused_sources" in summary


def test_format_verbose_summary_includes_retry_success_metadata():
    state = {
        "report_status": "success",
        "rewrite_attempted": True,
        "validation_attempts": 2,
        "validation_failures": [
            {"reason": "missing_body_citations", "message": "正文没有使用编号引用。"},
        ],
    }

    summary = format_verbose_summary(state)

    assert "Report validation:" in summary
    assert "rewrite_attempted: True" in summary
    assert "validation_attempts: 2" in summary
    assert "final_status: success" in summary
    assert "attempt 1: missing_body_citations" in summary


def test_format_verbose_summary_includes_evidence_metrics():
    state = {
        "evidence_metrics": {
            "subquestions": 2,
            "total_queries": 5,
            "raw_search_results": 12,
            "deduped_sources": 8,
            "duplicates_removed": 4,
            "extracted_sources": 5,
            "evidence_cards": 9,
            "source_quality": {"official": 1, "industry_report": 2, "seo_content": 1},
            "evidence_reliability": {"high": 3, "medium": 4, "low": 2},
        }
    }

    summary = format_verbose_summary(state)

    assert "Search coverage:" in summary
    assert "raw search results: 12" in summary
    assert "deduped sources: 8" in summary
    assert "Source quality:" in summary
    assert "industry_report: 2" in summary
    assert "Evidence reliability:" in summary
    assert "high: 3" in summary
