import pytest
from typer.testing import CliRunner

import deepresearch.config
from deepresearch.cli import app
from deepresearch.state import ReviewResult
import json as json_module


runner = CliRunner()


@pytest.fixture(autouse=True)
def isolate_app_config_env(monkeypatch):
    monkeypatch.setattr(deepresearch.config, "load_dotenv", lambda: None)
    for env_var in (
        "DEEPSEEK_API_KEY",
        "TAVILY_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPRESEARCH_MAX_SUBQUESTIONS",
        "DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY",
        "DEEPRESEARCH_OUTPUT_DIR",
    ):
        monkeypatch.delenv(env_var, raising=False)


def test_cli_reports_missing_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = runner.invoke(app, ["AI search"])

    assert result.exit_code == 1
    assert "DEEPSEEK_API_KEY is not set" in result.output


def test_cli_reports_invalid_max_subquestions(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-tavily-key")
    monkeypatch.setenv("DEEPRESEARCH_MAX_SUBQUESTIONS", "abc")

    result = runner.invoke(app, ["AI search"])

    assert result.exit_code == 1
    assert "DEEPRESEARCH_MAX_SUBQUESTIONS must be an integer" in result.output


def test_cli_rejects_zero_max_subquestions_option(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-tavily-key")

    result = runner.invoke(app, ["AI search", "--max-subquestions", "0"])

    assert result.exit_code == 1
    assert "max-subquestions" in result.output or "DEEPRESEARCH_MAX_SUBQUESTIONS" in result.output


def test_cli_rejects_zero_results_per_query_option_before_building_clients(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-tavily-key")

    def fail_if_building_clients(_config, **kwargs):
        raise AssertionError("API clients should not be built when config validation fails")

    monkeypatch.setattr("deepresearch.cli._build_app", fail_if_building_clients)

    result = runner.invoke(app, ["AI search", "--results-per-query", "0"])

    assert result.exit_code == 1
    assert "results-per-query" in result.output or "DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY" in result.output


class FakeResearchApp:
    def __init__(self, result):
        self.result = result
        self.inputs = []

    def invoke(self, state):
        self.inputs.append(state)
        return self.result


def _set_required_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-tavily-key")


def test_cli_prints_success_message_for_successful_report(monkeypatch):
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "report_markdown": "# Report\n\nBody",
        "output_path": "reports/success.md",
        "report_status": "success",
        "review": ReviewResult(passed=True, score=90, issues=[], suggestions=[]),
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda _config, **kwargs: fake_app)

    result = runner.invoke(app, ["AI search"])

    assert result.exit_code == 0
    assert "Saved report to: reports/success.md" in result.output
    assert "Report validation failed." not in result.output


def test_cli_prints_failure_message_for_failed_validation(monkeypatch):
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "report_markdown": "# 研究报告生成失败",
        "output_path": "reports/failed-failed.md",
        "report_status": "failed_validation",
        "review": ReviewResult(passed=False, score=0, issues=[], suggestions=[]),
        "errors": ["Report contains invalid source URL(s) outside search_results: https://invalid.example"],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda _config, **kwargs: fake_app)

    result = runner.invoke(app, ["AI search"])

    assert result.exit_code == 0
    assert "Report validation failed." in result.output
    assert "Saved failure report to: reports/failed-failed.md" in result.output
    assert "Run again or use --verbose" in result.output


def test_with_progress_prints_label_before_running_node(capsys):
    from deepresearch.cli import _with_progress

    calls = []

    def node(state):
        calls.append("node-ran")
        return {**state, "done": True}

    wrapped = _with_progress("[3/7] Preparing evidence...", node)
    result = wrapped({"question": "AI search"})

    captured = capsys.readouterr()
    assert "[3/7] Preparing evidence..." in captured.out
    assert calls == ["node-ran"]
    assert result["done"] is True


def test_cli_verbose_prints_workflow_summary(monkeypatch):
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "subquestions": [],
        "search_results": [],
        "notes": [],
        "report_markdown": "# Report\n\nBody",
        "output_path": "reports/success.md",
        "report_status": "success",
        "review": ReviewResult(passed=True, score=90, issues=[], suggestions=[]),
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda _config, **kwargs: fake_app)

    result = runner.invoke(app, ["AI search", "--verbose"])

    assert result.exit_code == 0
    assert "Workflow details:" in result.output
    assert "Subquestions:" in result.output
    assert "Review:" in result.output


def test_cli_dry_run_prints_evidence_summary(monkeypatch):
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "evidence_cards": [],
        "evidence_metrics": {
            "evidence_cards": 5,
            "corroboration": {"strongly_corroborated": 2, "weakly_corroborated": 2, "single_source": 1},
        },
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda config, dry_run=False, replay_search=False: fake_app)

    result = runner.invoke(app, ["AI search", "--dry-run"])

    assert result.exit_code == 0
    assert "[Dry run] Evidence extraction complete." in result.output
    assert "EvidenceCards: 5" in result.output
    assert "strongly_corroborated: 2" in result.output
    assert "weakly_corroborated" in result.output


def test_cli_save_search_writes_file(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "subquestions": [],
        "search_results": [],
        "evidence_cards": [],
        "evidence_metrics": {},
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda config, dry_run=False, replay_search=False: fake_app)
    output = tmp_path / "search.json"

    result = runner.invoke(app, ["AI search", "--dry-run", "--save-search", str(output)])

    assert result.exit_code == 0
    assert output.exists()


def test_cli_compare_prints_comparison(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    baseline_file = tmp_path / "baseline.json"
    new_file = tmp_path / "new.json"
    baseline_file.write_text(json_module.dumps({
        "evidence_cards": [{"id": "e1", "corroboration_level": "single_source"}],
        "evidence_metrics": {"extracted_sources": 3, "evidence_cards": 1,
                             "corroboration": {"single_source": 1}},
    }))
    new_file.write_text(json_module.dumps({
        "evidence_cards": [{"id": "e1", "corroboration_level": "strongly_corroborated"},
                           {"id": "e2", "corroboration_level": "weakly_corroborated"}],
        "evidence_metrics": {"extracted_sources": 3, "evidence_cards": 2,
                             "corroboration": {"strongly_corroborated": 1, "weakly_corroborated": 1}},
    }))

    result = runner.invoke(app, ["--compare", str(baseline_file), str(new_file)])

    assert result.exit_code == 0
    assert "A/B Comparison" in result.output
    assert "+100%" in result.output


def test_cli_output_live_mode_saves_artifact(monkeypatch, tmp_path):
    """--output 在 live 模式下保存 RunArtifact JSON。"""
    _set_required_env(monkeypatch)
    output_file = tmp_path / "result.json"
    fake_app = FakeResearchApp({
        "question": "AI search",
        "subquestions": [],
        "search_results": [],
        "extracted_claims": [],
        "evidence_cards": [],
        "evidence_metrics": {},
        "report_markdown": "# Report\n\nBody",
        "output_path": "reports/success.md",
        "report_status": "success",
        "review": ReviewResult(passed=True, score=90, issues=[], suggestions=[]),
        "review_rewritten": False,
        "validation_failures": [],
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda _config, **kwargs: fake_app)

    result = runner.invoke(app, ["AI search", "--output", str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()

    with open(output_file) as f:
        artifact = json_module.load(f)

    # 验证顶层结构
    assert "meta" in artifact
    assert "inputs" in artifact
    assert "pipeline" in artifact
    assert "standard_metrics" in artifact
    assert "output" in artifact

    # 验证 meta
    meta = artifact["meta"]
    assert meta["app_version"] == "0.5.2"
    assert meta["schema_version"] == 1
    assert meta["mode"] == "live"
    assert "timestamp" in meta
    assert "config" in meta

    # 验证 inputs
    assert artifact["inputs"]["question"] == "AI search"

    # 验证 output 包含 report_markdown
    assert artifact["output"]["report_markdown"] == "# Report\n\nBody"
    assert artifact["output"]["report_status"] == "success"


def test_cli_output_dry_run_mode_saves_artifact(monkeypatch, tmp_path):
    """--output 在 dry-run 模式下保存 RunArtifact JSON。"""
    _set_required_env(monkeypatch)
    output_file = tmp_path / "dryrun.json"
    fake_app = FakeResearchApp({
        "question": "AI search",
        "evidence_cards": [],
        "evidence_metrics": {
            "evidence_cards": 5,
            "corroboration": {"strongly_corroborated": 2, "weakly_corroborated": 2, "single_source": 1},
        },
        "errors": [],
    })
    monkeypatch.setattr(
        "deepresearch.cli._build_app",
        lambda config, dry_run=False, replay_search=False: fake_app,
    )

    result = runner.invoke(app, ["AI search", "--dry-run", "--output", str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()

    with open(output_file) as f:
        artifact = json_module.load(f)

    assert artifact["meta"]["mode"] == "dry-run"
    # dry-run 模式没有 report
    assert artifact["output"]["report_markdown"] == ""


def test_cli_output_replay_mode_saves_artifact(monkeypatch, tmp_path):
    """--output 在 replay 模式下保存 RunArtifact JSON。"""
    _set_required_env(monkeypatch)
    output_file = tmp_path / "replay.json"

    # 创建临时的 frozen search JSON
    frozen_file = tmp_path / "frozen.json"
    frozen_file.write_text(json_module.dumps({
        "question": "AI search",
        "subquestions": [],
        "search_results": [],
    }))

    fake_app = FakeResearchApp({
        "question": "AI search",
        "subquestions": [],
        "search_results": [],
        "extracted_claims": [],
        "evidence_cards": [],
        "evidence_metrics": {},
        "report_markdown": "# Replay Report",
        "output_path": "reports/success.md",
        "report_status": "success",
        "review": ReviewResult(passed=True, score=88, issues=[], suggestions=[]),
        "review_rewritten": False,
        "validation_failures": [],
        "errors": [],
    })
    monkeypatch.setattr(
        "deepresearch.cli._build_app",
        lambda config, dry_run=False, replay_search=False: fake_app,
    )

    result = runner.invoke(app, [
        "--replay-search", str(frozen_file),
        "--output", str(output_file),
    ])

    assert result.exit_code == 0
    assert output_file.exists()

    with open(output_file) as f:
        artifact = json_module.load(f)

    assert artifact["meta"]["mode"] == "replay"


def test_cli_output_terminal_unchanged(monkeypatch):
    """--output 不改变终端输出行为：live 模式依然打印报告路径。"""
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "report_markdown": "# Report\n\nBody",
        "output_path": "reports/success.md",
        "report_status": "success",
        "review": ReviewResult(passed=True, score=90, issues=[], suggestions=[]),
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda _config, **kwargs: fake_app)

    result = runner.invoke(app, ["AI search", "--output", "result.json"])

    assert result.exit_code == 0
    # 终端输出不受影响
    assert "Saved report to: reports/success.md" in result.output


def test_cli_output_includes_standard_metrics(monkeypatch, tmp_path):
    """--output 的 artifact 包含 metrics.py 计算的质量指标。"""
    _set_required_env(monkeypatch)
    output_file = tmp_path / "metrics_test.json"
    fake_app = FakeResearchApp({
        "question": "test",
        "subquestions": [],
        "search_results": [],
        "extracted_claims": [],
        "evidence_cards": [],
        "evidence_metrics": {},
        "report_markdown": "",
        "output_path": "reports/success.md",
        "report_status": "success",
        "review": ReviewResult(passed=True, score=85, issues=[], suggestions=[]),
        "review_rewritten": False,
        "validation_failures": [],
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda _config, **kwargs: fake_app)

    result = runner.invoke(app, ["test", "--output", str(output_file)])

    assert result.exit_code == 0

    with open(output_file) as f:
        artifact = json_module.load(f)

    sm = artifact["standard_metrics"]
    assert sm["evidence_card_count"] == 0
    assert sm["review_score"] == 85
    assert sm["review_passed"] is True
    assert sm["rewrite_triggered"] is False
