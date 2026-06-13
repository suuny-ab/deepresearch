"""Tests for CLI — core agent invocation only."""

import pytest
from typer.testing import CliRunner

from deepresearch.cli import app

runner = CliRunner()


def test_cli_requires_question_argument():
    """CLI must require a question argument."""
    result = runner.invoke(app, [])
    assert result.exit_code != 0


def test_cli_fails_without_api_keys(monkeypatch):
    """CLI must fail with clear error when API keys are missing."""
    monkeypatch.setattr("deepresearch.config.load_dotenv", lambda: None)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    result = runner.invoke(app, ["AI search"])
    assert result.exit_code == 1
    assert "DEEPSEEK_API_KEY" in result.output


def test_cli_full_pipeline_with_fake_graph(monkeypatch, tmp_path):
    """CLI invokes graph and prints report for successful run."""
    fake_state = {
        "question": "AI search trends",
        "subquestions": [],
        "search_results": [],
        "evidence_cards": [],
        "extracted_claims": [],
        "report_markdown": "# AI Search\n\nReport content.",
        "report_status": "success",
        "review": type("Review", (), {"score": 85, "passed": True, "issues": [], "suggestions": []})(),
        "errors": [],
        "output_path": str(tmp_path / "reports" / "test-report.md"),
        "rewrite_attempted": False,
        "validation_attempts": 1,
        "validation_failures": [],
        "review_feedback": None,
        "review_rewritten": False,
    }

    class FakeApp:
        def invoke(self, initial_state):
            return fake_state

    monkeypatch.setattr("deepresearch.cli._build_app", lambda config: FakeApp())
    monkeypatch.setattr("deepresearch.cli.AppConfig.from_env", lambda: type(
        "FakeConfig", (),
        {
            "deepseek_api_key": "sk-test",
            "tavily_api_key": "tvly-test",
            "deepseek_base_url": "https://api.test",
            "deepseek_model": "test-model",
            "max_subquestions": 5,
            "results_per_query": 5,
            "output_dir": str(tmp_path / "reports"),
            "with_overrides": lambda self, **kw: self,
            "validate_required": lambda self: None,
        },
    )())

    result = runner.invoke(app, ["AI search"])
    assert result.exit_code == 0
    assert "Saved report to:" in result.output
    assert "AI Search" in result.output
    assert "Report content" in result.output


def test_cli_prints_failure_when_validation_fails(monkeypatch, tmp_path):
    """CLI must surface failed_validation status clearly."""
    fake_state = {
        "question": "test",
        "report_markdown": "# Failed report",
        "report_status": "failed_validation",
        "review": type("Review", (), {"score": 0, "passed": False, "issues": ["Failed"], "suggestions": []})(),
        "errors": [],
        "output_path": str(tmp_path / "reports" / "test-failed.md"),
    }

    class FakeApp:
        def invoke(self, initial_state):
            return fake_state

    monkeypatch.setattr("deepresearch.cli._build_app", lambda config: FakeApp())
    monkeypatch.setattr("deepresearch.cli.AppConfig.from_env", lambda: type(
        "FakeConfig", (),
        {
            "deepseek_api_key": "sk-test",
            "tavily_api_key": "tvly-test",
            "deepseek_base_url": "https://api.test",
            "deepseek_model": "test-model",
            "max_subquestions": 5,
            "results_per_query": 5,
            "output_dir": str(tmp_path / "reports"),
            "with_overrides": lambda self, **kw: self,
            "validate_required": lambda self: None,
        },
    )())

    result = runner.invoke(app, ["test"])
    assert result.exit_code == 0
    assert "Report validation failed" in result.output
