# 架构简化 & LangSmith 集成 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除全部自建观测/测试基础设施 (~1,500 行)，引入 LangSmith 自动 tracing，Agent 代码库只保留核心研究功能。

**Architecture:** 删除 `metrics.py`、`verbose.py`、`benchmark/` 目录、`RunArtifact` 系列模型、6 个 CLI 标志。图拓扑简化为单一标准路径。LangSmith 在 LangGraph 框架层零代码自动捕获 trace。

**Tech Stack:** Python 3.11+, LangGraph, LangSmith, DeepSeek, Tavily, Typer, Pydantic

---

### Task 1: 添加 LangSmith 依赖

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: 添加 langsmith 到 pyproject.toml**

在 `dependencies` 列表末尾追加：

```toml
"langsmith>=0.1.0",
```

完整 dependencies 变为：

```toml
dependencies = [
    "langgraph>=0.2.0",
    "openai>=1.0.0",
    "pydantic>=2.7.0",
    "python-dotenv>=1.0.1",
    "rich>=13.7.0",
    "tavily-python>=0.5.0",
    "typer>=0.12.0",
    "langsmith>=0.1.0",
]
```

- [ ] **Step 2: 追加 LangSmith 环境变量到 .env.example**

在文件末尾追加：

```env
# LangSmith (可观测性 — 可选，不设置则静默跳过)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=deepresearch
```

- [ ] **Step 3: 安装依赖并验证**

```bash
uv sync
```

Expected: `langsmith` 安装成功，无冲突。

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock .env.example
git commit -m "chore: add langsmith dependency and env vars"
```

---

### Task 2: 清理 state.py — 删除观测模型

**Files:**
- Modify: `src/deepresearch/state.py`

- [ ] **Step 1: 删除 RunMeta 类定义**

删除以下代码（原 98-105 行）：

```python
class RunMeta(BaseModel):
    """一次运行的元信息。"""
    app_version: str
    schema_version: int = 1
    timestamp: str
    mode: Literal["live", "dry-run", "replay"]
    config: dict[str, Any]
```

- [ ] **Step 2: 删除 StandardMetrics 类定义**

删除以下代码（原 107-123 行）：

```python
class StandardMetrics(BaseModel):
    """从 state 中计算的质量指标，与业务节点解耦。"""
    evidence_card_count: int = 0
    claims_per_source: float = 0.0
    source_utilization: float = 0.0
    corroboration_strong: int = 0
    corroboration_weak: int = 0
    corroboration_single: int = 0
    domain_diversity: int = 0
    review_score: int | None = None
    review_passed: bool | None = None
    rewrite_triggered: bool = False
    citation_coverage: float | None = None
    source_citation_rate: float | None = None
    orphan_url_count: int | None = None
    validation_first_pass: bool | None = None
```

- [ ] **Step 3: 删除 RunArtifact 类定义**

删除以下代码（原 125-131 行）：

```python
class RunArtifact(BaseModel):
    """一次运行的完整快照，所有模式产出一致结构。"""
    meta: RunMeta
    inputs: dict[str, Any]
    pipeline: dict[str, Any]
    standard_metrics: StandardMetrics
    output: dict[str, Any]
```

- [ ] **Step 4: 从 ResearchState 删除 evidence_metrics 字段**

删除这行（原 84 行）：

```python
    evidence_metrics: dict[str, Any]
```

- [ ] **Step 5: 删除不再需要的 Any import（如仅 RunMeta 使用）**

检查 `from typing import Any` 是否仍被 `ResearchState` 的 `validation_failures` 字段使用。如果是，保留 import。

- [ ] **Step 6: Commit**

```bash
git add src/deepresearch/state.py
git commit -m "refactor: remove RunArtifact/RunMeta/StandardMetrics/evidence_metrics from state"
```

---

### Task 3: 清理 config.py — 删除 verbose 字段

**Files:**
- Modify: `src/deepresearch/config.py`

- [ ] **Step 1: 从 dataclass 删除 verbose 字段**

删除这行（原 26 行）：

```python
    verbose: bool = False
```

- [ ] **Step 2: 从 from_env() 删除 verbose 初始化**

`from_env()` 中没有 verbose 初始化行（它只在 `with_overrides` 中使用），无需修改。

- [ ] **Step 3: 从 with_overrides() 删除 verbose 参数**

修改 `with_overrides` 方法签名和函数体，删除 `verbose` 参数：

```python
def with_overrides(
    self,
    *,
    max_subquestions: int | None = None,
    results_per_query: int | None = None,
    output_dir: str | None = None,
    model: str | None = None,
) -> "AppConfig":
    return AppConfig(
        deepseek_api_key=self.deepseek_api_key,
        tavily_api_key=self.tavily_api_key,
        deepseek_base_url=self.deepseek_base_url,
        deepseek_model=self.deepseek_model if model is None else model,
        max_subquestions=self.max_subquestions if max_subquestions is None else max_subquestions,
        results_per_query=self.results_per_query if results_per_query is None else results_per_query,
        output_dir=self.output_dir if output_dir is None else output_dir,
    )
```

- [ ] **Step 4: Commit**

```bash
git add src/deepresearch/config.py
git commit -m "refactor: remove verbose field from AppConfig"
```

---

### Task 4: 简化 graph.py — 删除 dry_run 和 replay_search 分支

**Files:**
- Modify: `src/deepresearch/graph.py`

- [ ] **Step 1: 重写 build_research_graph 函数**

完整替换文件内容为：

```python
from collections.abc import Callable
from typing import Literal

from langgraph.graph import END, START, StateGraph

from deepresearch.state import ResearchState

Node = Callable[[ResearchState], ResearchState]


def _review_router(state: ResearchState) -> Literal["write_report", "save_report"]:
    """Route after review_report: rewrite if feedback is present, otherwise save."""
    if state.get("report_status") == "failed_validation":
        return "save_report"
    if state.get("review_feedback"):
        return "write_report"
    return "save_report"


def build_research_graph(
    *,
    plan_research: Node,
    search_web: Node,
    prepare_evidence: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
):
    graph = StateGraph(ResearchState)
    graph.add_node("plan_research", plan_research)
    graph.add_node("search_web", search_web)
    graph.add_node("prepare_evidence", prepare_evidence)
    graph.add_node("write_report", write_report)
    graph.add_node("review_report", review_report)
    graph.add_node("save_report", save_report)

    graph.add_edge(START, "plan_research")
    graph.add_edge("plan_research", "search_web")
    graph.add_edge("search_web", "prepare_evidence")
    graph.add_edge("prepare_evidence", "write_report")
    graph.add_edge("write_report", "review_report")
    graph.add_conditional_edges(
        "review_report",
        _review_router,
        {"write_report": "write_report", "save_report": "save_report"},
    )
    graph.add_edge("save_report", END)

    return graph.compile()


def create_research_app(
    *,
    plan_research: Node,
    search_web: Node,
    prepare_evidence: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
):
    return build_research_graph(
        plan_research=plan_research,
        search_web=search_web,
        prepare_evidence=prepare_evidence,
        write_report=write_report,
        review_report=review_report,
        save_report=save_report,
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/deepresearch/graph.py
git commit -m "refactor: simplify graph to single standard topology, remove dry_run and replay_search"
```

---

### Task 5: 清理 prepare_evidence.py — 删除统计和断言函数

**Files:**
- Modify: `src/deepresearch/nodes/prepare_evidence.py`

- [ ] **Step 1: 删除 _build_metrics 函数**

删除以下代码（原 160-169 行）：

```python
def _build_metrics(raw, deduped, extracted_sources, evidence_cards):
    return {
        "raw_search_results": len(raw),
        "deduped_sources": len(deduped),
        "duplicates_removed": len(raw) - len(deduped),
        "extracted_sources": len(extracted_sources),
        "evidence_cards": len(evidence_cards),
        "corroboration": dict(Counter(c.corroboration_level for c in evidence_cards)),
        "confidence": dict(Counter(c.confidence for c in evidence_cards)),
    }
```

- [ ] **Step 2: 删除 _run_assertions 函数**

删除以下代码（原 172-191 行）：

```python
def _run_assertions(claims, sources, cards):
    results = []
    for source in sources:
        count = len([c for c in claims if normalize_url(c.source_url) == normalize_url(source.url)])
        if count == 0:
            results.append(f"[FAIL] Source {source.url} contributed 0 claims")
    if cards:
        strong_weak = sum(1 for c in cards if c.corroboration_level in ("strongly_corroborated", "weakly_corroborated"))
        rate = strong_weak / len(cards)
        if rate < 0.6:
            results.append(f"[FAIL] Corroboration rate {rate:.0%} below 60% threshold")
    if claims:
        sq_counts = defaultdict(int)
        for c in claims:
            sq_counts[c.subquestion_id] += 1
        if sq_counts:
            mx, mn = max(sq_counts.values()), min(sq_counts.values())
            if mn > 0 and mx > mn * 3:
                results.append(f"[FAIL] Claims distribution skewed: {dict(sq_counts)}")
    return results
```

- [ ] **Step 3: 删除 prepare_evidence 内部对 _build_metrics 和 _run_assertions 的调用**

在 `make_prepare_evidence_node` 返回的 `prepare_evidence` 函数中，删除这两段代码：

删除 assertion 调用（原 238-239 行）：
```python
        assertion_results = _run_assertions(claims, extracted_sources, all_cards)
        errors.extend(assertion_results)
```

删除 metrics 构建和 state 返回中的 `evidence_metrics`（原 241-247 行），将返回语句改为：

```python
        return {
            **state,
            "search_results": deduped,
            "extracted_claims": claims,
            "evidence_cards": all_cards,
            "errors": errors,
        }
```

- [ ] **Step 4: 删除不再使用的 import**

删除 `from collections import Counter`（如果 Counter 不再被其他地方使用——`_validate_corroboration` 和 `_dedupe_results` 不使用 Counter）。检查后：Counter 仅被 `_build_metrics` 使用，可以删除。

修改 import 行：
```python
from collections import defaultdict
```

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/nodes/prepare_evidence.py
git commit -m "refactor: remove _build_metrics and _run_assertions from prepare_evidence"
```

---

### Task 6: 精简 cli.py — Agent 核心调用

**Files:**
- Modify: `src/deepresearch/cli.py`

这是最复杂的修改。完整重写文件。

- [ ] **Step 1: 用精简版替换 cli.py**

```python
import typer
from rich.console import Console
from rich.markdown import Markdown

from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily import TavilySearchClient
from deepresearch.config import AppConfig
from deepresearch.errors import ConfigError, DeepResearchError
from deepresearch.graph import create_research_app
from deepresearch.nodes.planning import make_plan_research_node
from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node
from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.nodes.saving import make_save_report_node
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.nodes.writing import make_write_report_node

app = typer.Typer(no_args_is_help=True)
console = Console()


def _build_app(config: AppConfig):
    if config.deepseek_api_key is None:
        raise ConfigError("DEEPSEEK_API_KEY is not set")
    if config.tavily_api_key is None:
        raise ConfigError("TAVILY_API_KEY is not set")
    llm = DeepSeekLLMClient(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )
    search = TavilySearchClient(api_key=config.tavily_api_key)

    plan_research = make_plan_research_node(llm, config.max_subquestions)
    search_web = make_search_web_node(search, config.results_per_query)
    prepare_evidence = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)
    write_report = make_write_report_node(llm)
    review_report = make_review_report_node(llm)
    save_report = make_save_report_node(config.output_dir)

    return create_research_app(
        plan_research=plan_research,
        search_web=search_web,
        prepare_evidence=prepare_evidence,
        write_report=write_report,
        review_report=review_report,
        save_report=save_report,
    )


@app.command()
def main(
    question: str = typer.Argument(..., help="Research question"),
    max_subquestions: int = typer.Option(5, "--max-subquestions", help="Maximum generated subquestions"),
    results_per_query: int = typer.Option(5, "--results-per-query", help="Tavily results per query"),
    output_dir: str = typer.Option("reports", "--output-dir", help="Report output directory"),
    model: str = typer.Option("deepseek-v4-pro", "--model", help="DeepSeek model"),
):
    try:
        config = AppConfig.from_env().with_overrides(
            max_subquestions=max_subquestions,
            results_per_query=results_per_query,
            output_dir=output_dir,
            model=model,
        )
        config.validate_required()

        console.print("[1/6] Planning research...")
        console.print("[2/6] Searching web...")
        console.print("[3/6] Preparing evidence...")
        console.print("[4/6] Writing report...")
        console.print("[5/6] Reviewing report...")
        console.print("[6/6] Saving report...")

        research_app = _build_app(config)
        result = research_app.invoke({"question": question, "errors": []})

        if result.get("report_status") == "failed_validation":
            console.print(f"\n[bold red]Report validation failed.[/bold red]")
            console.print(f"Saved failure report to: {result['output_path']}")
        else:
            console.print(f"\nSaved report to: {result['output_path']}")

        console.print(Markdown(result.get("report_markdown", "")))

    except ConfigError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except DeepResearchError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
```

- [ ] **Step 2: 验证 CLI 基本功能**

```bash
uv run deepresearch --help
```

Expected: 显示 4 个 option（`--max-subquestions`、`--results-per-query`、`--output-dir`、`--model`），不显示已删除的 `--verbose`、`--dry-run`、`--output`、`--save-search`、`--replay-search`、`--compare`。

- [ ] **Step 3: Commit**

```bash
git add src/deepresearch/cli.py
git commit -m "refactor: simplify CLI to core agent — remove 6 flags and verbose/dry-run logic"
```

---

### Task 7: 删除文件

**Files:**
- Delete: `src/deepresearch/metrics.py`
- Delete: `src/deepresearch/verbose.py`
- Delete: `benchmark/` (整个目录)
- Modify: `src/deepresearch/nodes/writing.py` (移除 `--verbose` 提示文本)

- [ ] **Step 1: 删除 metrics.py**

```bash
git rm src/deepresearch/metrics.py
```

- [ ] **Step 2: 删除 verbose.py**

```bash
git rm src/deepresearch/verbose.py
```

- [ ] **Step 3: 删除 benchmark/ 目录**

```bash
git rm -r benchmark/
```

- [ ] **Step 4: 更新 writing.py 中的用户提示文本**

在 `_validation_failure_report` 函数的用户建议部分，有一行提到 `--verbose`：

删除这行（原 80 行）：
```python
        "- 使用 `--verbose` 查看子问题、搜索 query 和搜索结果数量。\n"
```

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/nodes/writing.py
git commit -m "refactor: delete metrics.py, verbose.py, benchmark/ directory; remove --verbose hint from writing.py"
```

---

### Task 8: 更新测试文件

**Files:**
- Delete: `tests/test_gate.py`
- Delete: `tests/test_metrics.py`
- Delete: `tests/test_verbose.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_graph_structure.py`
- Modify: `tests/test_prepare_evidence_node.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_integration_offline.py`

- [ ] **Step 1: 删除 3 个废弃测试文件**

```bash
git rm tests/test_gate.py tests/test_metrics.py tests/test_verbose.py
```

- [ ] **Step 2: 重写 test_cli.py — 只保留核心功能测试**

完整替换文件内容为：

```python
"""Tests for CLI — core agent invocation only."""

import json

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
```

- [ ] **Step 3: 重写 test_graph_structure.py — 只保留标准拓扑测试**

完整替换文件内容为：

```python
"""Tests for graph structure — standard topology only."""
from pathlib import Path

from deepresearch.graph import create_research_app


def _fake_node(state):
    return state


def test_standard_graph_compiles(tmp_path):
    """Standard graph compiles with all 6 nodes in correct sequence."""
    app = create_research_app(
        plan_research=_fake_node,
        search_web=_fake_node,
        prepare_evidence=_fake_node,
        write_report=_fake_node,
        review_report=_fake_node,
        save_report=_fake_node,
    )
    assert app is not None


def test_standard_graph_executes_all_nodes(tmp_path):
    """Standard graph traverses all nodes end to end."""
    app = create_research_app(
        plan_research=_fake_node,
        search_web=_fake_node,
        prepare_evidence=_fake_node,
        write_report=_fake_node,
        review_report=_fake_node,
        save_report=_fake_node,
    )
    result = app.invoke({"question": "test", "errors": []})
    assert result is not None
```

- [ ] **Step 4: 更新 test_prepare_evidence_node.py — 删除 _run_assertions 相关代码**

修改文件：删除 `_run_assertions` 的 import，删除 `evidence_metrics` 的断言。

**删除 import 行**（原第 3 行）：
```python
from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node, _run_assertions
```
改为：
```python
from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node
```

**修改 test_prepare_evidence_basic** 函数中的断言（原 52-53 行），删除这两行：
```python
    assert result["evidence_metrics"]["evidence_cards"] == 1
    assert "corroboration" in result["evidence_metrics"]
```

**删除 test_run_assertions_* 三个测试函数**（原约 100-145 行区域）：`test_run_assertions_detects_zero_claim_sources`、`test_run_assertions_detects_low_corroboration`、`test_run_assertions_detects_skewed_distribution`。

- [ ] **Step 5: 更新 test_state.py — 删除 evidence_metrics 引用**

修改 `test_research_state_no_longer_has_extracted_sources` 函数（原 211-220 行），删除 `evidence_metrics` 字段：

```python
def test_research_state_no_longer_has_extracted_sources():
    from deepresearch.state import ResearchState

    state: ResearchState = {
        "question": "AI search",
        "evidence_cards": [],
    }

    assert "extracted_sources" not in state
```

- [ ] **Step 6: 更新 test_integration_offline.py — 删除 evidence_metrics 断言**

删除原 68-76 行的 `evidence_metrics` 断言块：
```python
    assert result["evidence_metrics"] == {
        "raw_search_results": 1,
        "deduped_sources": 1,
        "duplicates_removed": 0,
        "extracted_sources": 1,
        "evidence_cards": 1,
        "corroboration": {"single_source": 1},
        "confidence": {"high": 1},
    }
```

- [ ] **Step 7: 运行全部离线测试验证**

```bash
uv run pytest
```

Expected: 所有保留的测试通过（21 个测试文件），零 regression。

- [ ] **Step 8: Commit**

```bash
git add tests/
git commit -m "test: remove tests for deleted features, update remaining tests"
```

---

### Task 9: 更新 README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README — 删除已废弃的特性说明**

删除以下已废弃的章节/内容：
- "Verbose mode" 章节（原 110-118 行区域）
- "Validation failures" 章节中 `--verbose` 的提及
- "Citation format" 章节中 `--verbose` 的提及（原 80 行）
- 所有 `--dry-run`、`--save-search`、`--replay-search`、`--compare`、`--output` 的文档

添加 LangSmith 说明：

在 "Setup" 和 "Run" 章节之间插入：

```markdown
## Observability

This project uses [LangSmith](https://smith.langchain.com/) for tracing. Set these environment variables in `.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=deepresearch
```

If `LANGCHAIN_API_KEY` is not set, tracing is silently skipped — the agent works normally without it.

Each run automatically captures: node inputs/outputs, LLM token usage, and execution latency in the LangSmith UI.
```

更新 Run 命令示例，删除 `--verbose`:

```bash
uv run deepresearch "AI 搜索引擎的发展趋势" \
  --max-subquestions 5 \
  --results-per-query 5 \
  --output-dir reports \
  --model deepseek-v4-pro
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README — remove deleted flags, add LangSmith section"
```

---

### Task 10: 最终验证

- [ ] **Step 1: 运行全部离线测试**

```bash
uv run pytest -v
```

Expected: 全部 PASS，零 regression。

- [ ] **Step 2: 代码清理验证**

```bash
grep -r "RunArtifact\|RunMeta\|StandardMetrics\|evidence_metrics" src/ || echo "CLEAN"
grep -r "verbose\|dry.run\|save.search\|replay.search" src/deepresearch/cli.py || echo "CLEAN"
grep "langsmith" pyproject.toml
grep "LANGCHAIN" .env.example
```

Expected: 前两个 grep 无结果或只命中注释，后两个 grep 有匹配。

- [ ] **Step 3: 清理 __pycache__**

```bash
find src -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find tests -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
```

- [ ] **Step 4: 在线冒烟测试（需要 API 密钥）**

```bash
uv run deepresearch "测试问题" --max-subquestions 2 --results-per-query 2
```

Expected:
- 显示六步进度
- 生成并打印 Markdown 报告
- 保存报告到 `reports/`
- 如有 LangSmith API key，trace 出现在 LangSmith UI

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: final cleanup — remove pycache, verify all tests pass"
```

---

## 变更统计

| 类别 | 数量 |
|------|------|
| 删除文件 | ~15 个（metrics.py, verbose.py, benchmark/ 全部, 3 个测试文件） |
| 修改文件 | 9 个（state.py, config.py, graph.py, cli.py, prepare_evidence.py, writing.py, pyproject.toml, .env.example, README.md） |
| 新增依赖 | 1 个（langsmith） |
| 净删代码 | ~1,500 行 |
| CLI 参数 | 10 → 4（删除 6 个） |
