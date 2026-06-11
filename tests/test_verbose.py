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
