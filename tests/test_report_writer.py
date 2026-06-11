from datetime import datetime
from pathlib import Path

import pytest

from deepresearch.errors import ReportWriteError
from deepresearch.state import ReviewResult
from deepresearch.utils.report_writer import append_quality_review, save_report


def test_append_quality_review():
    report = "# Report\n\nBody"
    review = ReviewResult(
        passed=False,
        score=72,
        issues=["Missing source near one claim"],
        suggestions=["Add a stronger source"],
    )

    result = append_quality_review(report, review)

    assert "## Quality Review" in result
    assert "Score: 72/100" in result
    assert "Passed: False" in result
    assert "Missing source near one claim" in result
    assert "Add a stronger source" in result


def test_save_report_writes_utf8_markdown(tmp_path):
    review = ReviewResult(passed=True, score=90, issues=[], suggestions=[])
    now = datetime(2026, 6, 10, 15, 30, 0)

    output_path = save_report(
        question="AI Search Trends",
        report_markdown="# 标题\n\n内容",
        review=review,
        output_dir=tmp_path,
        now=now,
    )

    assert output_path.exists()
    assert output_path.name == "2026-06-10-153000-ai-search-trends.md"
    assert "# 标题" in output_path.read_text(encoding="utf-8")
    assert "## Quality Review" in output_path.read_text(encoding="utf-8")


def test_save_report_wraps_filesystem_errors(monkeypatch, tmp_path):
    review = ReviewResult(passed=True, score=90, issues=[], suggestions=[])

    def fail_write_text(self, content, encoding=None):
        raise OSError("disk is full")

    monkeypatch.setattr(Path, "write_text", fail_write_text)

    with pytest.raises(ReportWriteError) as exc_info:
        save_report(
            question="AI Search Trends",
            report_markdown="# Report\n\nBody",
            review=review,
            output_dir=tmp_path,
            now=datetime(2026, 6, 10, 15, 30, 0),
        )

    assert "Failed to write report: disk is full" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, OSError)
