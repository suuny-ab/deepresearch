# Run Artifact & Metrics 模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Deep Research Agent 每次运行产出结构化的 RunArtifact JSON（含自动计算的质量指标），建立与业务解耦的独立 metrics 度量模块。

**Architecture:** 三层解耦——state.py 定义数据容器（RunArtifact / RunMeta / StandardMetrics），metrics.py 提供纯函数的度量计算，cli.py 在任意运行模式下组装 artifact 并写入文件。节点层不感知度量层。

**Tech Stack:** Python 3.11+, Pydantic v2, Typer, pytest, CliRunner

---

## File Structure

```
Create:
  src/deepresearch/metrics.py       — 纯函数度量计算
  tests/test_metrics.py             — metrics 单元测试

Modify:
  src/deepresearch/__init__.py      — 添加 __version__
  pyproject.toml                    — 更新 version 为 0.5.2
  src/deepresearch/state.py         — 添加 RunArtifact, RunMeta, StandardMetrics
  src/deepresearch/cli.py:161-176   — 重写 --output 逻辑
  tests/test_cli.py                 — 添加 --output 测试

Delete content:
  benchmark/results/*.json          — 旧格式文件清空

Unchanged:
  src/deepresearch/nodes/*.py       — 节点不感知度量
  src/deepresearch/graph.py         — 工作流定义不变
  benchmark/frozen/                 — replay 输入数据保留
  benchmark/compare.py              — 暂时保留（后续被 gate.py 替代）
```

---

### Task 1: 清理旧 benchmark results 文件

**Files:**
- Modify (delete content): `benchmark/results/*.json`

- [ ] **Step 1: 删除旧格式 JSON 文件**

```bash
rm benchmark/results/*.json
```

保留 `benchmark/results/.gitkeep` 如果存在，否则新建空目录占位。

- [ ] **Step 2: 验证清理结果**

Run: `ls benchmark/results/`
Expected: 目录为空（或只有 .gitkeep）

- [ ] **Step 3: Commit**

```bash
git add benchmark/results/
git commit -m "chore: remove old-format benchmark result files"
```

---

### Task 2: 添加版本标识

**Files:**
- Modify: `src/deepresearch/__init__.py`
- Modify: `pyproject.toml:3`

- [ ] **Step 1: 在 `__init__.py` 中添加 `__version__`**

`src/deepresearch/__init__.py` 当前是空文件（1行）。写入以下内容：

```python
__version__ = "0.5.2"
```

使用 Write 工具：

```python
# src/deepresearch/__init__.py
__version__ = "0.5.2"
```

- [ ] **Step 2: 更新 `pyproject.toml` 中的 version**

将 `pyproject.toml` 第 3 行从：

```toml
version = "0.1.0"
```

改为：

```toml
version = "0.5.2"
```

- [ ] **Step 3: 验证版本可导入**

Run: `uv run python -c "from deepresearch import __version__; print(__version__)"`
Expected: 输出 `0.5.2`

- [ ] **Step 4: Commit**

```bash
git add src/deepresearch/__init__.py pyproject.toml
git commit -m "chore: bump version to 0.5.2, add __version__"
```

---

### Task 3: 添加数据模型到 state.py

**Files:**
- Modify: `src/deepresearch/state.py`

- [ ] **Step 1: 在 state.py 末尾添加三个新模型**

当前 `state.py` 已有 `SubQuestion`, `SearchResult`, `ExtractedClaim`, `ExtractedSource`, `EvidenceCard`, `ReviewResult`, `ResearchState`。在其后追加：

```python
from datetime import datetime, timezone
from typing import Any, Literal


class RunMeta(BaseModel):
    """一次运行的元信息。"""
    app_version: str
    schema_version: int = 1
    timestamp: str
    mode: Literal["live", "dry-run", "replay"]
    config: dict[str, Any]


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


class RunArtifact(BaseModel):
    """一次运行的完整快照，所有模式产出一致结构。"""
    meta: RunMeta
    inputs: dict[str, Any]
    pipeline: dict[str, Any]
    standard_metrics: StandardMetrics
    output: dict[str, Any]
```

- [ ] **Step 2: 验证模型可导入且能正常实例化**

Run: `uv run python -c "from deepresearch.state import RunMeta, StandardMetrics, RunArtifact; m = StandardMetrics(); print(m.evidence_card_count); r = RunMeta(app_version='0.5.2', schema_version=1, timestamp='2026-06-13T00:00:00Z', mode='live', config={}); print(r.mode)"`
Expected: 输出 `0` 和 `live`

- [ ] **Step 3: 运行已有测试确认无回归**

Run: `uv run pytest tests/test_state.py -v`
Expected: 所有已有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add src/deepresearch/state.py
git commit -m "feat: add RunArtifact, RunMeta, StandardMetrics models to state"
```

---

### Task 4: 创建 metrics.py 及其测试

**Files:**
- Create: `tests/test_metrics.py`
- Create: `src/deepresearch/metrics.py`

- [ ] **Step 1: 写测试文件 `tests/test_metrics.py`**

```python
from deepresearch.metrics import compute_standard_metrics
from deepresearch.state import EvidenceCard, ReviewResult


def test_compute_standard_metrics_empty_state():
    """空 state 返回全零/null 的 metrics。"""
    result = compute_standard_metrics({})

    assert result.evidence_card_count == 0
    assert result.claims_per_source == 0.0
    assert result.source_utilization == 0.0
    assert result.corroboration_strong == 0
    assert result.corroboration_weak == 0
    assert result.corroboration_single == 0
    assert result.domain_diversity == 0
    assert result.review_score is None
    assert result.review_passed is None
    assert result.rewrite_triggered is False
    assert result.citation_coverage is None
    assert result.source_citation_rate is None
    assert result.orphan_url_count is None
    assert result.validation_first_pass is None


def test_compute_standard_metrics_with_evidence_cards():
    """有 evidence_cards 时正确统计数量和分布。"""
    cards = [
        EvidenceCard(
            id="c1", subquestion_id="sq1", claim="Claim A",
            source_url="https://example.com/a",
            source_title="Source A", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="strongly_corroborated",
            corroborating_sources=["https://other.com/1", "https://other.com/2"],
            confidence="high",
        ),
        EvidenceCard(
            id="c2", subquestion_id="sq1", claim="Claim B",
            source_url="https://example.com/b",
            source_title="Source B", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="weakly_corroborated",
            corroborating_sources=["https://other.com/3"],
            confidence="medium",
        ),
        EvidenceCard(
            id="c3", subquestion_id="sq2", claim="Claim C",
            source_url="https://example.com/a",
            source_title="Source A", supporting_snippet="...",
            content_type="extracted_content",
            corroboration_level="single_source",
            corroborating_sources=[],
            confidence="low",
        ),
    ]
    state = {"evidence_cards": cards}

    result = compute_standard_metrics(state)

    assert result.evidence_card_count == 3
    assert result.corroboration_strong == 1
    assert result.corroboration_weak == 1
    assert result.corroboration_single == 1


def test_compute_standard_metrics_claims_per_source():
    """claims_per_source = evidence_cards / search_results。"""
    cards = [
        EvidenceCard(
            id="c1", subquestion_id="sq1", claim="Claim",
            source_url="https://a.com/1",
            source_title="T", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="single_source",
            corroborating_sources=[], confidence="medium",
        ),
        EvidenceCard(
            id="c2", subquestion_id="sq1", claim="Claim",
            source_url="https://b.com/1",
            source_title="T", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="single_source",
            corroborating_sources=[], confidence="medium",
        ),
    ]
    from deepresearch.state import SearchResult
    sources = [
        SearchResult(subquestion_id="sq1", title="A", url="https://a.com/1", content="..."),
        SearchResult(subquestion_id="sq1", title="B", url="https://b.com/1", content="..."),
    ]
    state = {"evidence_cards": cards, "search_results": sources}

    result = compute_standard_metrics(state)

    assert result.evidence_card_count == 2
    assert result.claims_per_source == 1.0  # 2 cards / 2 sources


def test_compute_standard_metrics_source_utilization():
    """source_utilization = 被 evidence_cards 使用的搜索来源比例。"""
    from deepresearch.state import SearchResult
    cards = [
        EvidenceCard(
            id="c1", subquestion_id="sq1", claim="Claim",
            source_url="https://used.com/1",
            source_title="T", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="single_source",
            corroborating_sources=[], confidence="medium",
        ),
    ]
    sources = [
        SearchResult(subquestion_id="sq1", title="Used", url="https://used.com/1", content="..."),
        SearchResult(subquestion_id="sq1", title="Unused", url="https://unused.com/1", content="..."),
    ]
    state = {"evidence_cards": cards, "search_results": sources}

    result = compute_standard_metrics(state)

    assert result.source_utilization == 0.5  # 1 used / 2 total


def test_compute_standard_metrics_domain_diversity():
    """domain_diversity = 搜索结果的独立域名数。"""
    from deepresearch.state import SearchResult
    sources = [
        SearchResult(subquestion_id="sq1", title="A", url="https://example.com/1", content="..."),
        SearchResult(subquestion_id="sq1", title="B", url="https://other.org/1", content="..."),
        SearchResult(subquestion_id="sq2", title="C", url="https://example.com/2", content="..."),
    ]
    state = {"search_results": sources}

    result = compute_standard_metrics(state)

    assert result.domain_diversity == 2  # example.com + other.org


def test_compute_standard_metrics_with_review():
    """有 review 时正确捕获评分和状态。"""
    review = ReviewResult(passed=True, score=85, issues=[], suggestions=[])
    state = {"review": review}

    result = compute_standard_metrics(state)

    assert result.review_score == 85
    assert result.review_passed is True
    assert result.rewrite_triggered is False


def test_compute_standard_metrics_rewrite_triggered():
    """review_rewritten 为 True 时 rewrite_triggered 为 True。"""
    review = ReviewResult(passed=True, score=65, issues=["missing depth"], suggestions=["add more"])
    state = {"review": review, "review_rewritten": True}

    result = compute_standard_metrics(state)

    assert result.rewrite_triggered is True


def test_compute_standard_metrics_citation_validation():
    """有 report_markdown 时计算 citation 相关指标。"""
    from deepresearch.state import SearchResult
    report = (
        "Report body with citation.[1]\n\n"
        "## Sources\n"
        "[1] https://example.com/source-a\n"
    )
    sources = [
        SearchResult(subquestion_id="sq1", title="A", url="https://example.com/source-a", content="..."),
    ]
    state = {
        "report_markdown": report,
        "search_results": sources,
        "report_status": "success",
        "validation_failures": [],
    }

    result = compute_standard_metrics(state)

    assert result.citation_coverage == 1.0
    assert result.source_citation_rate == 1.0
    assert result.orphan_url_count == 0
    assert result.validation_first_pass is True


def test_compute_standard_metrics_citation_with_orphan_url():
    """Sources 中的 URL 不在搜索结果中 → orphan_url_count > 0。"""
    from deepresearch.state import SearchResult
    report = (
        "Report body.[1]\n\n"
        "## Sources\n"
        "[1] https://not-in-results.com/fake\n"
    )
    sources = [
        SearchResult(subquestion_id="sq1", title="A", url="https://example.com/real", content="..."),
    ]
    state = {
        "report_markdown": report,
        "search_results": sources,
        "report_status": "failed_validation",
        "validation_failures": [{"reason": "invalid_source_urls"}],
    }

    result = compute_standard_metrics(state)

    assert result.orphan_url_count == 1
    assert result.validation_first_pass is False


def test_compute_standard_metrics_handles_missing_url():
    """当 search_result 的 url 为 None 时不会崩溃。"""
    from deepresearch.state import SearchResult
    sources = [
        SearchResult(subquestion_id="sq1", title="A", url=None, content="..."),
    ]
    cards = [
        EvidenceCard(
            id="c1", subquestion_id="sq1", claim="Claim",
            source_url="https://example.com/a",
            source_title="T", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="single_source",
            corroborating_sources=[], confidence="medium",
        ),
    ]
    state = {"evidence_cards": cards, "search_results": sources}

    result = compute_standard_metrics(state)
    # 不应崩溃，source_utilization 和 domain_diversity 应为 0
    assert result.source_utilization == 0.0
    assert result.domain_diversity == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: 全部 FAIL — `ModuleNotFoundError: No module named 'deepresearch.metrics'`

- [ ] **Step 3: 实现 `src/deepresearch/metrics.py`**

```python
"""纯函数度量计算模块。

从 ResearchState dict 中提取质量指标，不依赖 LLM 或外部服务。
与业务节点解耦：节点不 import 本模块，本模块不 import 节点。
"""

from collections import Counter

from deepresearch.citations import validate_citations
from deepresearch.state import StandardMetrics
from deepresearch.utils.urls import extract_domain, normalize_url


def compute_standard_metrics(state: dict) -> StandardMetrics:
    """从 state dict 计算全部标准质量指标。

    Args:
        state: ResearchState 的 dict 形式（graph.invoke() 的返回值）。

    Returns:
        StandardMetrics: 所有可计算的质量指标。缺失数据对应的字段为 None 或 0。
    """
    cards = state.get("evidence_cards", [])
    search_results = state.get("search_results", [])
    review = state.get("review")
    report = state.get("report_markdown", "")

    # --- 证据维度 ---

    evidence_card_count = len(cards)
    claims_per_source = evidence_card_count / max(len(search_results), 1)

    # source_utilization: 被 evidence_cards 使用的搜索来源比例
    card_urls = {normalize_url(c.source_url) for c in cards if c.source_url}
    source_urls = {normalize_url(s.url) for s in search_results if s.url}
    used_sources = card_urls & source_urls if source_urls else set()
    source_utilization = len(used_sources) / max(len(source_urls), 1)

    # corroboration 分布
    corr_counter = Counter(c.corroboration_level for c in cards)
    corroboration_strong = corr_counter.get("strongly_corroborated", 0)
    corroboration_weak = corr_counter.get("weakly_corroborated", 0)
    corroboration_single = corr_counter.get("single_source", 0)

    # domain_diversity: 搜索结果的独立域名数
    domains = {extract_domain(s.url) for s in search_results if s.url}
    domain_diversity = len(domains)

    # --- 审查维度 ---

    review_score = review.score if review is not None else None
    review_passed = review.passed if review is not None else None
    rewrite_triggered = bool(state.get("review_rewritten", False))

    # --- 结构正确性维度（依赖 citation 验证） ---

    citation_coverage = None
    source_citation_rate = None
    orphan_url_count = None
    validation_first_pass = None

    if report:
        allowed_urls = {normalize_url(s.url) for s in search_results if s.url}
        validation = validate_citations(report, allowed_urls)

        total_body = len(validation.body_citations)
        if total_body > 0:
            undefined = len(validation.undefined_citations)
            citation_coverage = round((total_body - undefined) / total_body, 3)

        total_sources = len(validation.source_citations)
        if total_sources > 0:
            unused = len(validation.unused_sources)
            source_citation_rate = round((total_sources - unused) / total_sources, 3)

        orphan_url_count = len(validation.invalid_source_urls)

    # validation_first_pass: 首次就通过 citation 校验
    failures = state.get("validation_failures", [])
    report_status = state.get("report_status")
    if report_status is not None:
        validation_first_pass = report_status == "success" and len(failures) == 0

    return StandardMetrics(
        evidence_card_count=evidence_card_count,
        claims_per_source=round(claims_per_source, 2),
        source_utilization=round(source_utilization, 2),
        corroboration_strong=corroboration_strong,
        corroboration_weak=corroboration_weak,
        corroboration_single=corroboration_single,
        domain_diversity=domain_diversity,
        review_score=review_score,
        review_passed=review_passed,
        rewrite_triggered=rewrite_triggered,
        citation_coverage=citation_coverage,
        source_citation_rate=source_citation_rate,
        orphan_url_count=orphan_url_count,
        validation_first_pass=validation_first_pass,
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: 全部 10 个测试 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_metrics.py src/deepresearch/metrics.py
git commit -m "feat: add metrics.py — pure-function quality metric computation from state"
```

---

### Task 5: 重写 cli.py 的 --output 逻辑（测试先行）

**Files:**
- Modify: `tests/test_cli.py`（添加 --output 测试）
- Modify: `src/deepresearch/cli.py:161-176`（重写 --output 块）

- [ ] **Step 1: 在 `tests/test_cli.py` 中添加 --output 测试**

在文件末尾追加以下测试函数：

```python
import json as json_module


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
```

- [ ] **Step 2: 运行新测试确认失败**

Run: `uv run pytest tests/test_cli.py::test_cli_output_live_mode_saves_artifact tests/test_cli.py::test_cli_output_dry_run_mode_saves_artifact tests/test_cli.py::test_cli_output_replay_mode_saves_artifact -v`
Expected: FAIL — live 模式下不会写入文件（当前 `--output` 只在 dry_run 或 replay_search 时生效），或写入的文件结构不对（缺少 meta/inputs/pipeline 等顶层字段）

- [ ] **Step 3: 修改 `cli.py` 的 `--output` 逻辑**

将 `cli.py` 中 lines 161-176 的旧代码：

```python
        # --output (dry-run or replay output)
        if output and (dry_run or replay_search):
            import json as json_module
            output_data = {
                "evidence_cards": [c.model_dump() for c in result.get("evidence_cards", [])],
                "extracted_claims": [c.model_dump() for c in result.get("extracted_claims", [])],
                "evidence_metrics": result.get("evidence_metrics", {}),
            }
            review = result.get("review")
            if review is not None:
                output_data["review"] = review.model_dump()
            output_data["review_rewritten"] = result.get("review_rewritten", False)
            output_data["report_status"] = result.get("report_status")
            with open(output, "w", encoding="utf-8") as f:
                json_module.dump(output_data, f, indent=2, default=str)
            console.print(f"Benchmark output saved to {output}")
```

替换为：

```python
        # --output (保存完整 RunArtifact，所有模式可用)
        if output:
            import json as json_module
            from datetime import datetime, timezone

            from deepresearch import __version__
            from deepresearch.metrics import compute_standard_metrics
            from deepresearch.state import RunArtifact, RunMeta

            determined_mode: str
            if replay_search:
                determined_mode = "replay"
            elif dry_run:
                determined_mode = "dry-run"
            else:
                determined_mode = "live"

            meta = RunMeta(
                app_version=__version__,
                schema_version=1,
                timestamp=datetime.now(timezone.utc).isoformat(),
                mode=determined_mode,
                config={
                    "max_subquestions": config.max_subquestions,
                    "results_per_query": config.results_per_query,
                    "model": config.deepseek_model,
                },
            )

            inputs = {
                "question": result.get("question", question or ""),
                "subquestions": [sq.model_dump() for sq in result.get("subquestions", [])],
            }

            pipeline = {
                "search_results": [sr.model_dump() for sr in result.get("search_results", [])],
                "extracted_claims": [c.model_dump() for c in result.get("extracted_claims", [])],
                "evidence_cards": [c.model_dump() for c in result.get("evidence_cards", [])],
                "evidence_metrics": result.get("evidence_metrics", {}),
            }

            standard_metrics = compute_standard_metrics(result)

            review = result.get("review")
            output_section = {
                "report_markdown": result.get("report_markdown", ""),
                "report_status": result.get("report_status"),
                "review": review.model_dump() if review is not None else None,
                "validation_failures": result.get("validation_failures", []),
                "output_path": result.get("output_path"),
            }

            artifact = RunArtifact(
                meta=meta,
                inputs=inputs,
                pipeline=pipeline,
                standard_metrics=standard_metrics,
                output=output_section,
            )

            with open(output, "w", encoding="utf-8") as f:
                json_module.dump(artifact.model_dump(), f, indent=2, default=str)
            console.print(f"Run artifact saved to {output}")
```

同时修改 `--output` 选项的 help text（line 108）：

```python
    output: str | None = typer.Option(None, "--output", help="Save run artifact as JSON (all modes)"),
```

- [ ] **Step 4: 运行全部 --output 相关测试**

Run: `uv run pytest tests/test_cli.py -v -k "output"`
Expected: 5 个测试全部 PASS

- [ ] **Step 5: 运行全部已有 cli 测试确认无回归**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 所有已有测试 + 新增测试全部 PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_cli.py src/deepresearch/cli.py
git commit -m "feat: rewrite --output to save full RunArtifact in all modes"
```

---

### Task 6: 集成验证 — 端到端 dry-run 测试

**Files:**
- 无新建/修改，仅验证

- [ ] **Step 1: 用真实 LLM 运行一次 dry-run + --output 端到端验证**

```bash
uv run deepresearch "固态电池 2026 商业化进展" --dry-run --max-subquestions 2 --results-per-query 2 --output /tmp/test-artifact.json
```

- [ ] **Step 2: 检查输出的 artifact 结构**

Run: `uv run python -c "
import json
with open('/tmp/test-artifact.json') as f:
    a = json.load(f)
print('meta.mode:', a['meta']['mode'])
print('meta.app_version:', a['meta']['app_version'])
print('meta.schema_version:', a['meta']['schema_version'])
print('standard_metrics keys:', list(a['standard_metrics'].keys()))
print('evidence_card_count:', a['standard_metrics']['evidence_card_count'])
print('pipeline keys:', list(a['pipeline'].keys()))
print('output keys:', list(a['output'].keys()))
"`
Expected: 输出完整的结构信息，evidence_card_count > 0，所有字段齐全

- [ ] **Step 3: 运行全部离线测试确认零回归**

Run: `uv run pytest`
Expected: 全部测试 PASS

- [ ] **Step 4: Commit（如无更改则跳过）**

---

## 完成后的验证清单

- [ ] `uv run pytest` 全部通过
- [ ] `--output` 在 live / dry-run / replay 三种模式均能产出有效 JSON
- [ ] 产出的 JSON 包含 meta / inputs / pipeline / standard_metrics / output 五部分
- [ ] standard_metrics 中的数值与 evidence_cards / review / report 的实际内容一致
- [ ] 不加 `--output` 时行为与改动前完全一致
- [ ] 终端输出（报告打印、verbose 摘要）不受 `--output` 影响
