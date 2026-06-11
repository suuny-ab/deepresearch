from typer.testing import CliRunner

import deepresearch.config
from deepresearch.cli import app


runner = CliRunner()


def test_cli_reports_missing_api_key(monkeypatch):
    monkeypatch.setattr(deepresearch.config, "load_dotenv", lambda: None)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = runner.invoke(app, ["AI search"])

    assert result.exit_code == 1
    assert "DEEPSEEK_API_KEY is not set" in result.output


def test_cli_reports_invalid_max_subquestions(monkeypatch):
    monkeypatch.setattr(deepresearch.config, "load_dotenv", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-tavily-key")
    monkeypatch.setenv("DEEPRESEARCH_MAX_SUBQUESTIONS", "abc")

    result = runner.invoke(app, ["AI search"])

    assert result.exit_code == 1
    assert "DEEPRESEARCH_MAX_SUBQUESTIONS must be an integer" in result.output


def test_cli_rejects_zero_max_subquestions_option(monkeypatch):
    monkeypatch.setattr(deepresearch.config, "load_dotenv", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-tavily-key")

    result = runner.invoke(app, ["AI search", "--max-subquestions", "0"])

    assert result.exit_code == 1
    assert "max-subquestions" in result.output or "DEEPRESEARCH_MAX_SUBQUESTIONS" in result.output


def test_cli_rejects_zero_results_per_query_option_before_building_clients(monkeypatch):
    monkeypatch.setattr(deepresearch.config, "load_dotenv", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-tavily-key")

    def fail_if_building_clients(_config):
        raise AssertionError("API clients should not be built when config validation fails")

    monkeypatch.setattr("deepresearch.cli._build_app", fail_if_building_clients)

    result = runner.invoke(app, ["AI search", "--results-per-query", "0"])

    assert result.exit_code == 1
    assert "results-per-query" in result.output or "DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY" in result.output
