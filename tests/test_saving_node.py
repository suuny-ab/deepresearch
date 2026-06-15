from unittest.mock import MagicMock, patch

from deepresearch.nodes.saving import make_save_report_node
from deepresearch.state import ReviewResult


def test_save_report_node_uses_failed_filename_for_failed_validation(tmp_path):
    node = make_save_report_node(tmp_path)

    result = node({
        "question": "AI Search",
        "report_markdown": "# 研究报告生成失败",
        "review": ReviewResult(passed=False, score=0, issues=[], suggestions=[]),
        "report_status": "failed_validation",
    })

    assert result["output_path"].endswith("-failed.md")


def test_save_report_node_syncs_citation_feedback_when_trace_active(tmp_path):
    """When a LangSmith trace is active, citation result is written as feedback."""
    fake_client = MagicMock()
    mock_run_tree = MagicMock()
    mock_run_tree.trace_id = "trace-abc-123"

    with (
        patch("deepresearch.nodes.saving._get_current_run_tree", return_value=mock_run_tree),
        patch("deepresearch.nodes.saving.Client", return_value=fake_client),
    ):
        node = make_save_report_node(tmp_path)

        result = node({
            "question": "AI Search",
            "report_markdown": "# Report\n\nClaim.[1]\n\n## Sources\n\n[1] https://e.com",
            "review": ReviewResult(passed=True, score=90, issues=[], suggestions=[]),
            "report_status": "success",
        })

    assert result["output_path"]
    fake_client.create_feedback.assert_called_once()
    call_kwargs = fake_client.create_feedback.call_args.kwargs
    assert call_kwargs["key"] == "citation_compliance"
    assert call_kwargs["score"] == 1.0
    assert "trace-abc-123" in str(call_kwargs)


def test_save_report_node_does_not_crash_when_no_trace_context(tmp_path):
    """When no LangSmith trace is active, the node works normally without feedback."""
    with patch("deepresearch.nodes.saving._get_current_run_tree", return_value=None):
        node = make_save_report_node(tmp_path)

        result = node({
            "question": "AI Search",
            "report_markdown": "# Report",
            "review": ReviewResult(passed=False, score=0, issues=[], suggestions=[]),
            "report_status": "failed_validation",
        })

    assert result["output_path"].endswith("-failed.md")


def test_save_report_node_syncs_failure_score(tmp_path):
    """Failed validation → score 0.0 in feedback."""
    fake_client = MagicMock()
    mock_run_tree = MagicMock()
    mock_run_tree.trace_id = "trace-fail-456"

    with (
        patch("deepresearch.nodes.saving._get_current_run_tree", return_value=mock_run_tree),
        patch("deepresearch.nodes.saving.Client", return_value=fake_client),
    ):
        node = make_save_report_node(tmp_path)

        result = node({
            "question": "AI Search",
            "report_markdown": "# Failed",
            "review": ReviewResult(passed=False, score=0, issues=["bad"], suggestions=[]),
            "report_status": "failed_validation",
            "validation_failures": [{"reason": "missing_sources_section"}],
        })

    assert result["output_path"].endswith("-failed.md")
    call_kwargs = fake_client.create_feedback.call_args.kwargs
    assert call_kwargs["score"] == 0.0
    assert call_kwargs["comment"]
    assert "missing_sources_section" in call_kwargs["comment"].lower()
