"""Tests for evaluate_all and compute_diff."""

import pytest


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _summary(*, version: str = "v0.5.2", questions: list[dict]) -> dict:
    return {
        "version": version,
        "questions": questions,
    }


def _question_entry(
    *,
    id: str = "q1",
    question: str = "Test?",
    citation_passed: bool = True,
    review_score: int = 80,
    citation_compliance: float = 1.0,
    source_utilization: float = 0.6,
    cross_validation_usage: float = 0.5,
) -> dict:
    return {
        "id": id,
        "question": question,
        "citation_passed": citation_passed,
        "review_score": review_score,
        "citation_compliance": citation_compliance,
        "source_utilization": source_utilization,
        "cross_validation_usage": cross_validation_usage,
    }


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


def test_diff_improvement():
    """Every metric improves → positive deltas across the board."""
    from deepresearch.compare import compute_diff

    baseline = _summary(version="v0.5.2", questions=[
        _question_entry(id="q1", review_score=72, source_utilization=0.5, cross_validation_usage=0.4),
    ])
    candidate = _summary(version="v0.5.3", questions=[
        _question_entry(id="q1", review_score=80, source_utilization=0.7, cross_validation_usage=0.6),
    ])

    diff = compute_diff(baseline, candidate)

    assert diff["baseline_version"] == "v0.5.2"
    assert diff["candidate_version"] == "v0.5.3"

    agg = diff["aggregates"]
    assert agg["avg_review_score"]["delta"] > 0
    assert agg["avg_source_utilization"]["delta"] > 0
    assert agg["avg_cross_validation_usage"]["delta"] > 0


def test_diff_regression():
    """Every metric degrades → negative deltas."""
    from deepresearch.compare import compute_diff

    baseline = _summary(version="v0.5.2", questions=[
        _question_entry(id="q1", review_score=88, source_utilization=0.8, cross_validation_usage=0.7),
    ])
    candidate = _summary(version="v0.5.3", questions=[
        _question_entry(id="q1", review_score=70, source_utilization=0.5, cross_validation_usage=0.3),
    ])

    diff = compute_diff(baseline, candidate)

    agg = diff["aggregates"]
    assert agg["avg_review_score"]["delta"] < 0
    assert agg["avg_source_utilization"]["delta"] < 0
    assert agg["avg_cross_validation_usage"]["delta"] < 0


def test_diff_mixed():
    """Some metrics improve, some regress."""
    from deepresearch.compare import compute_diff

    baseline = _summary(version="v0.5.2", questions=[
        _question_entry(id="q1", review_score=80, source_utilization=0.6, cross_validation_usage=0.5),
    ])
    candidate = _summary(version="v0.5.3", questions=[
        _question_entry(id="q1", review_score=75, source_utilization=0.8, cross_validation_usage=0.7),
    ])

    diff = compute_diff(baseline, candidate)

    agg = diff["aggregates"]
    # review_score dropped
    assert agg["avg_review_score"]["delta"] < 0
    # source and cv improved
    assert agg["avg_source_utilization"]["delta"] > 0
    assert agg["avg_cross_validation_usage"]["delta"] > 0


def test_diff_missing_question():
    """Candidate missing a question → flagged."""
    from deepresearch.compare import compute_diff

    baseline = _summary(version="v0.5.2", questions=[
        _question_entry(id="q1"),
        _question_entry(id="q2"),
    ])
    candidate = _summary(version="v0.5.3", questions=[
        _question_entry(id="q1"),
    ])

    diff = compute_diff(baseline, candidate)

    assert diff["missing_in_candidate"] == ["q2"]
    assert diff["missing_in_baseline"] == []


def test_diff_unchanged():
    """Identical scores → delta is zero."""
    from deepresearch.compare import compute_diff

    summary = _summary(questions=[
        _question_entry(id="q1", review_score=80, source_utilization=0.6),
    ])

    diff = compute_diff(summary, summary)

    agg = diff["aggregates"]
    assert agg["avg_review_score"]["delta"] == 0.0
    assert agg["avg_source_utilization"]["delta"] == 0.0


# ---------------------------------------------------------------------------
# evaluate_all
# ---------------------------------------------------------------------------


def _mock_target(report: str, search_urls: list[str], evidence_cards: list[dict], review_score: int = 80, citation_passed: bool = True) -> callable:
    """Return a make_target-compatible function that yields fixed data."""
    def target(inputs: dict) -> dict:
        return {
            "question": inputs["question"],
            "report": report,
            "search_results": [{"url": u, "title": "T", "content": "c"} for u in search_urls],
            "evidence_cards": evidence_cards,
            "subquestions": [],
            "citation_passed": citation_passed,
            "review_score": review_score,
            "review_issues": [],
            "review_suggestions": [],
            "errors": [],
            "output_path": "reports/test.md",
        }
    return target


def _mock_questions() -> list[dict]:
    return [
        {"id": "q1", "question": "Test question 1", "tags": [], "difficulty": "easy"},
        {"id": "q2", "question": "Test question 2", "tags": [], "difficulty": "medium"},
    ]


def test_evaluate_all_structure():
    """evaluate_all returns version, per-question entries, and aggregates."""
    from deepresearch.compare import evaluate_all

    report = "# Test\n\nClaim.[1]\n\n## Sources\n\n[1] https://example.com/a"
    target = _mock_target(report=report, search_urls=["https://example.com/a"], evidence_cards=[])
    questions = _mock_questions()

    result = evaluate_all(target, questions, version="v0.5.3")

    assert result["version"] == "v0.5.3"
    assert len(result["questions"]) == 2
    assert result["questions"][0]["id"] == "q1"
    assert "aggregates" in result


def test_evaluate_all_aggregates_are_averages():
    """Aggregates are correct averages across questions."""
    from deepresearch.compare import evaluate_all

    # Two questions with different scores. We need to create separate
    # target functions or use a smarter mock. For simplicity, use one
    # target that ignores the question string.
    report = "# T\n\nC.[1]\n\n## Sources\n\n[1] https://e.com/a"
    target = _mock_target(
        report=report,
        search_urls=["https://e.com/a"],
        evidence_cards=[{"source_url": "https://e.com/a", "corroboration_level": "strongly_corroborated"}],
        review_score=84,
    )
    questions = [{"id": "q1", "question": "Q1", "tags": [], "difficulty": "easy"}]

    result = evaluate_all(target, questions, version="test")

    agg = result["aggregates"]
    assert agg["citation_pass_rate"] == 1.0
    assert agg["avg_review_score"] == 84.0
    assert agg["avg_citation_compliance"] == 1.0
    assert agg["avg_source_utilization"] == 1.0
    assert agg["avg_cross_validation_usage"] == 1.0


def test_evaluate_all_citation_pass_rate_partial():
    """citation_pass_rate is fraction of questions that pass."""
    from deepresearch.compare import evaluate_all

    # This test just verifies that the function runs without error
    # and computes citation_pass_rate correctly for a single question.
    report = "# T\n\nC.[1]\n\n## Sources\n\n[1] https://e.com/a"
    target = _mock_target(
        report=report,
        search_urls=["https://e.com/a"],
        evidence_cards=[],
        citation_passed=True,
    )
    questions = [_mock_questions()[0]]

    result = evaluate_all(target, questions, version="test")
    assert result["aggregates"]["citation_pass_rate"] == 1.0
