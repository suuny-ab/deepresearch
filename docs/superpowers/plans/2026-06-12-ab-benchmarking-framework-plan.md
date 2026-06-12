# A/B Benchmarking Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable A/B benchmarking framework with frozen-search replay, multi-version comparison, and statistical reporting.

**Architecture:** Four independent artifacts: a query config file (queries.json), a comparison script (compare.py), a v0.3.1 replay adapter (replay_v031.py), and a README. The existing `--output` flag is extended to capture review/rewrite metadata for full-flow benchmark runs.

**Tech Stack:** Python stdlib (json, statistics, argparse/pathlib), no new dependencies.

---

### Task 1: Create Benchmark Query Config

**Files:**
- Create: `benchmark/queries.json`

- [ ] **Step 1: Create queries.json**

```json
{
  "queries": [
    {
      "id": "q1-langgraph-crewai",
      "type": "comparison",
      "question": "LangGraph 和 CrewAI 的适用场景有什么区别，各自适合什么类型的 AI Agent 项目",
      "max_subquestions": 4,
      "results_per_query": 4,
      "test": ["A", "B", "C"]
    },
    {
      "id": "q2-solid-state-battery",
      "type": "factual",
      "question": "固态电池 2026 年商业化进展：哪些公司在量产，技术路线有什么突破",
      "max_subquestions": 4,
      "results_per_query": 4,
      "test": ["A", "B", "C"]
    },
    {
      "id": "q3-ai-search-trends",
      "type": "forward-looking",
      "question": "AI 搜索引擎 2027 年的发展趋势：技术架构、商业模式、用户体验各有什么变化",
      "max_subquestions": 4,
      "results_per_query": 4,
      "test": ["A", "B", "C"]
    },
    {
      "id": "q4-quantum-crypto",
      "type": "chinese-technical",
      "question": "量子计算对现有密码体系的威胁有多紧迫，后量子密码算法的迁移进展如何",
      "max_subquestions": 4,
      "results_per_query": 4,
      "test": ["C"]
    },
    {
      "id": "q5-short-answer",
      "type": "boundary",
      "question": "用 3 句话概括 2026 年 AI Agent 的关键技术进展和产业落地情况",
      "max_subquestions": 3,
      "results_per_query": 1,
      "test": ["C"]
    }
  ],
  "tests": {
    "A": {
      "description": "Test A: v0.3.1 vs v0.4 — extraction suppression",
      "versions": ["v0.3.1", "v0.4"],
      "query_ids": ["q1-langgraph-crewai", "q2-solid-state-battery", "q3-ai-search-trends"],
      "runs_per_query": 1,
      "mode": "dry-run"
    },
    "B": {
      "description": "Test B: v0.4 vs v0.5.1 — score consistency",
      "versions": ["v0.4", "v0.5.1"],
      "query_ids": ["q1-langgraph-crewai", "q2-solid-state-battery", "q3-ai-search-trends"],
      "runs_per_query": 6,
      "mode": "full"
    },
    "C": {
      "description": "Test C: v0.5.1 vs v0.5.2 — review feedback loop",
      "versions": ["v0.5.1", "v0.5.2"],
      "query_ids": ["q1-langgraph-crewai", "q2-solid-state-battery", "q3-ai-search-trends", "q4-quantum-crypto", "q5-short-answer"],
      "runs_per_query": 1,
      "mode": "full"
    }
  },
  "thresholds": {
    "test_a_claims_per_source_min": 1.5,
    "test_a_source_utilization_min": 0.9,
    "test_a_corroboration_rate_max": 0.8,
    "test_b_score_std_max_ratio": 1.0,
    "test_c_min_score_improvement": 0,
    "test_c_at_least_one_improvement_by": 5
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add benchmark/queries.json
git commit -m "feat: add benchmark query config with 5 queries and 3 test definitions"
```

---

### Task 2: Extend --output for Full-Flow Benchmark Data

**Files:**
- Modify: `src/deepresearch/cli.py:160-169` — add review/rewrite fields to output

**Problem:** Current `--output` only saves evidence data. For Test B/C (full flow), we also need review score and rewrite metadata.

- [ ] **Step 1: Modify the --output section**

Edit `src/deepresearch/cli.py`, replace lines 160-169:

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
            output_data["review_feedback"] = result.get("review_feedback")
            output_data["report_status"] = result.get("report_status")
            with open(output, "w", encoding="utf-8") as f:
                json_module.dump(output_data, f, indent=2, default=str)
            console.print(f"Benchmark output saved to {output}")
```

- [ ] **Step 2: Run existing tests to verify no breakage**

```bash
uv run pytest tests/ -q
```
Expected: 136 passed

- [ ] **Step 3: Commit**

```bash
git add src/deepresearch/cli.py
git commit -m "feat: extend --output to include review, rewrite, and status metadata for benchmarks"
```

---

### Task 3: Create compare.py — Comparison Script

**Files:**
- Create: `benchmark/compare.py`

- [ ] **Step 1: Write compare.py**

```python
#!/usr/bin/env python3
"""A/B Benchmark comparison script for Deep Research Agent.

Reads output JSONs from benchmark runs and produces a comparison report.
Usage: python benchmark/compare.py benchmark/results/ --config benchmark/queries.json
"""

import json
import statistics
from argparse import ArgumentParser
from pathlib import Path


def load_results(results_dir: Path, test_config: dict) -> dict[str, dict]:
    """Load all result JSONs for a test, grouped by version and query.

    Returns: {version: {query_id: [list of result dicts]}}
    """
    versions = test_config["versions"]
    queries = test_config["query_ids"]
    runs = test_config["runs_per_query"]

    data: dict[str, dict] = {v: {} for v in versions}
    for version in versions:
        for qid in queries:
            version_results = []
            for run in range(1, runs + 1):
                path = results_dir / f"{version}-{qid}-run{run}.json"
                if path.exists():
                    with open(path) as f:
                        version_results.append(json.load(f))
            if version_results:
                data[version][qid] = version_results
    return data


def compute_test_a(data: dict) -> dict:
    """Test A: claims/source ratio, source_utilization, corroboration_rate."""
    results = {}
    for version in data:
        total_claims = 0
        total_sources = 0
        corroboration = {"strongly_corroborated": 0, "weakly_corroborated": 0, "single_source": 0}
        for qid, runs in data[version].items():
            for run in runs:
                metrics = run.get("evidence_metrics", {})
                total_claims += metrics.get("evidence_cards", 0)
                total_sources += metrics.get("extracted_sources", 1)
                corr = metrics.get("corroboration", {})
                for k in corroboration:
                    corroboration[k] += corr.get(k, 0)
        total_cards = sum(corroboration.values())
        results[version] = {
            "claims_per_source": round(total_claims / max(total_sources, 1), 2),
            "source_utilization": round(total_claims / max(total_sources, 1), 2),  # all sources contribute if > 0 claims
            "corroboration_rate": round(
                (corroboration["strongly_corroborated"] + corroboration["weakly_corroborated"]) / max(total_cards, 1), 3
            ) if total_cards > 0 else 0,
            "total_cards": total_cards,
            "total_sources": total_sources,
        }
    return results


def compute_test_b(data: dict) -> dict:
    """Test B: score standard deviation and range across runs."""
    results = {}
    for version in data:
        all_scores = []
        for qid, runs in data[version].items():
            for run in runs:
                review = run.get("review", {})
                if review:
                    all_scores.append(review.get("score", 0))
        if all_scores:
            results[version] = {
                "score_mean": round(statistics.mean(all_scores), 1),
                "score_std": round(statistics.stdev(all_scores), 1) if len(all_scores) > 1 else 0,
                "score_min": min(all_scores),
                "score_max": max(all_scores),
                "score_range": max(all_scores) - min(all_scores),
                "n_scores": len(all_scores),
            }
        else:
            results[version] = {
                "score_mean": "N/A",
                "score_std": "N/A",
                "score_min": "N/A",
                "score_max": "N/A",
                "score_range": "N/A",
                "n_scores": 0,
            }
    return results


def compute_test_c(data: dict) -> dict:
    """Test C: rewrite count, score improvement, claims/source."""
    results = {}
    for version in data:
        rewrites = 0
        score_before = []
        score_after = []
        total_claims = 0
        total_sources = 0
        for qid, runs in data[version].items():
            for run in runs:
                if run.get("review_rewritten"):
                    rewrites += 1
                review = run.get("review", {})
                if review:
                    score_after.append(review.get("score", 0))
                metrics = run.get("evidence_metrics", {})
                total_claims += metrics.get("evidence_cards", 0)
                total_sources += metrics.get("extracted_sources", 1)
        # v0.5.1 doesn't rewrite, so score_before = score_after
        v2 = data.get("v0.5.2", data.get(version, []))
        results[version] = {
            "rewrites_triggered": rewrites,
            "avg_score": round(statistics.mean(score_after), 1) if score_after else "N/A",
            "claims_per_source": round(total_claims / max(total_sources, 1), 2),
        }
    return results


def evaluate_test_a(results: dict, thresholds: dict) -> tuple[bool, str]:
    """Check if Test A passes."""
    v1, v2 = list(results.keys())
    cps1 = results[v1]["claims_per_source"]
    cps2 = results[v2]["claims_per_source"]
    min_cps = thresholds.get("test_a_claims_per_source_min", 1.5)

    messages = []
    passed = True
    if cps2 < min_cps:
        messages.append(f"FAIL: claims/source {cps2} below threshold {min_cps}")
        passed = False
    else:
        ratio = cps2 / max(cps1, 0.01)
        messages.append(f"PASS: claims/source {cps1} → {cps2} ({ratio:.0%} improvement)")

    corr1 = results[v1]["corroboration_rate"]
    corr2 = results[v2]["corroboration_rate"]
    max_corr = thresholds.get("test_a_corroboration_rate_max", 0.8)
    if corr2 > max_corr:
        messages.append(f"WARN: corroboration_rate {corr2:.1%} still above {max_corr:.0%} (may be inflated)")
    else:
        messages.append(f"PASS: corroboration_rate {corr1:.1%} → {corr2:.1%} (below {max_corr:.0%} threshold)")

    return passed, "\n  ".join(messages)


def evaluate_test_b(results: dict, thresholds: dict) -> tuple[bool, str]:
    """Check if Test B passes — v0.5.1 should have lower score variance."""
    v1, v2 = list(results.keys())
    std1 = results[v1]["score_std"]
    std2 = results[v2]["score_std"]

    messages = []
    if std2 <= std1:
        reduction = (std1 - std2) / max(std1, 0.01)
        messages.append(f"PASS: score_std {std1} → {std2} ({reduction:.0%} reduction)")
        return True, "\n  ".join(messages)
    else:
        messages.append(f"FAIL: score_std {std1} → {std2} (increased)")
        return False, "\n  ".join(messages)


def evaluate_test_c(results: dict, thresholds: dict) -> tuple[bool, str]:
    """Check if Test C passes — rewrite should improve scores."""
    messages = []
    v2 = results.get("v0.5.2", {})
    rewrites = v2.get("rewrites_triggered", 0)

    if rewrites > 0:
        messages.append(f"PASS: {rewrites} rewrite(s) triggered")
    else:
        messages.append("WARN: no rewrites triggered (may need adjusted query design)")

    passed = rewrites > 0
    return passed, "\n  ".join(messages)


def render_report(test_configs: dict, all_data: dict, thresholds: dict) -> str:
    """Render the full A/B comparison report."""
    lines = [
        "A/B Benchmark Report",
        "=" * 60,
        "",
    ]

    evaluators = {
        "A": (compute_test_a, evaluate_test_a),
        "B": (compute_test_b, evaluate_test_b),
        "C": (compute_test_c, evaluate_test_c),
    }

    for test_id in ["A", "B", "C"]:
        config = test_configs["tests"].get(test_id)
        if not config or test_id not in all_data:
            continue

        lines.append(f"Test {test_id}: {config['description']}")
        lines.append("-" * 60)

        compute, evaluate = evaluators[test_id]
        results = compute(all_data[test_id])
        passed, detail = evaluate(results, thresholds)

        lines.append(f"  Status: {'PASS' if passed else 'FAIL'}")
        lines.append(f"  {detail}")
        lines.append("")

        # Render data table
        headers = ["Metric"] + config["versions"]
        rows = []
        for metric in results[config["versions"][0]]:
            row = [metric] + [str(results[v].get(metric, "N/A")) for v in config["versions"]]
            rows.append(row)

        col_widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
        fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
        lines.append(fmt.format(*headers))
        for row in rows:
            lines.append(fmt.format(*row))
        lines.append("")

    # Overall
    passes = sum(1 for tid in ["A", "B", "C"] if evaluate(
        evaluators[tid][0](all_data.get(tid, {})), thresholds
    )[0])
    lines.append(f"Overall: {passes}/3 tests pass")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = ArgumentParser(description="A/B Benchmark comparison for Deep Research Agent")
    parser.add_argument("results_dir", type=Path, help="Directory containing result JSON files")
    parser.add_argument("--config", type=Path, default=Path("benchmark/queries.json"),
                        help="Path to queries.json config")
    parser.add_argument("--output", type=Path, default=None,
                        help="Write report to file instead of stdout")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    all_data = {}
    for test_id in ["A", "B", "C"]:
        test_config = config["tests"].get(test_id)
        if not test_config:
            continue
        data = load_results(args.results_dir, test_config)
        if data:
            all_data[test_id] = data

    thresholds = config.get("thresholds", {})
    report = render_report(config, all_data, thresholds)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"Report saved to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test with sample data**

Create sample test data to verify:

```bash
mkdir -p /tmp/bench-test
# Create minimal sample results
python -c "
import json
sample = {
    'evidence_metrics': {
        'evidence_cards': 26, 'extracted_sources': 15,
        'corroboration': {'strongly_corroborated': 10, 'weakly_corroborated': 6, 'single_source': 10}
    }
}
json.dump(sample, open('/tmp/bench-test/v0.4-q1-langgraph-crewai-run1.json', 'w'))
"
python benchmark/compare.py /tmp/bench-test/ --config benchmark/queries.json
```
Expected: "No data found for Test A" or graceful handling of missing runs

- [ ] **Step 3: Commit**

```bash
git add benchmark/compare.py
git commit -m "feat: add A/B benchmark comparison script with per-test evaluation"
```

---

### Task 4: Create v0.3.1 Replay Script

**Files:**
- Create: `benchmark/scripts/replay_v031.py`

v0.3.1 doesn't have `--replay-search`. This script directly constructs the graph with initial state from frozen.json, bypassing plan_research and search_web.

- [ ] **Step 1: Write replay_v031.py**

```python
#!/usr/bin/env python3
"""Replay benchmark queries on v0.3.1 using frozen search results.

v0.3.1 does not have --replay-search, and its graph cannot skip plan+search.
Instead of using the full graph, this script directly calls prepare_evidence
with frozen search data for dry-run tests (Test A).
For full-flow tests, v0.3.1 is not supported — use v0.4+.

Usage:
  git checkout v0.3.1
  python benchmark/scripts/replay_v031.py benchmark/frozen/q1.json --output results.json
"""

import json
import sys
from argparse import ArgumentParser
from pathlib import Path

# Add v0.3.1 source to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily import TavilySearchClient
from deepresearch.config import AppConfig
from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node


def main():
    parser = ArgumentParser(description="v0.3.1 benchmark dry-run replay adapter")
    parser.add_argument("frozen", type=Path, help="Path to frozen search JSON")
    parser.add_argument("--output", type=Path, default=None, help="Save output as JSON")
    parser.add_argument("--max-sources", type=int, default=3,
                        help="Max sources per subquestion for evidence selection")
    args = parser.parse_args()

    with open(args.frozen) as f:
        frozen = json.load(f)

    config = AppConfig.from_env()
    llm = DeepSeekLLMClient(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )
    search = TavilySearchClient(api_key=config.tavily_api_key)

    # v0.3.1 doesn't support --replay-search — directly call prepare_evidence
    prepare_evidence = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=args.max_sources)

    result = prepare_evidence({
        "question": frozen["question"],
        "subquestions": frozen["subquestions"],
        "search_results": frozen["search_results"],
        "errors": [],
    })

    if args.output:
        output_data = {
            "evidence_cards": [c.model_dump() for c in result.get("evidence_cards", [])],
            "extracted_claims": [c.model_dump() for c in result.get("extracted_claims", [])],
            "evidence_metrics": result.get("evidence_metrics", {}),
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"Output saved to {args.output}")

    print(f"Evidence cards: {len(result.get('evidence_cards', []))}")
    print(f"Extracted claims: {len(result.get('extracted_claims', []))}")


if __name__ == "__main__":
    main()
```

**注意：** v0.3.1 的 `build_research_graph`/`create_research_app` 签名可能与当前版本略有不同（如没有 `dry_run`/`replay_search` 参数）。实际运行时需要根据 v0.3.1 的代码调整。此脚本的正确运行依赖于 v0.3.1 的 branch checkout。

- [ ] **Step 3: Verify v0.3.1 graph compatibility**

v0.3.1 的实际图签名（从 `git show 53d3581:src/deepresearch/graph.py` 确认）：

```python
def build_research_graph(
    *,
    plan_research: Node,
    search_web: Node,
    prepare_evidence: Node,
    synthesize_notes: Node,      # v0.3.1 特有，v0.4 移除
    write_report: Node,
    review_report: Node,
    save_report: Node,
    dry_run: bool = False,        # 有 dry_run，但无 replay_search
):
```

v0.3.1 支持 `dry_run` 但不支持 `replay_search`。因此 replay 脚本的策略是：
- **Test A 只需要 dry-run** → 直接调 v0.3.1 的全图（会执行 plan+search，但我们用 frozen 的 search_results 替换）。不对——plan+search 会覆盖 frozen search_results。

**正确的策略：** v0.3.1 不支持跳过 plan+search，所以不能用全图。改用 **直接调用 prepare_evidence 节点函数**，跳过 graph.compile() 调用：

```python
# 不走图，手动链式调用节点
prepare_evidence_node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)
result_state = {"question": frozen["question"], "subquestions": frozen["subquestions"],
                "search_results": frozen["search_results"], "errors": []}
result = prepare_evidence_node(result_state)
# result 包含 evidence_cards, extracted_claims, evidence_metrics
```

这只适用于 Test A 的 dry-run 场景。如果未来需要 v0.3.1 的完整流程，需要 monkey-patch `build_research_graph` 的 edges 来跳过 plan+search。

- [ ] **Step 4: Commit**

```bash
git add benchmark/scripts/replay_v031.py
git commit -m "feat: add v0.3.1 benchmark replay adapter script"
```

---

### Task 5: Create benchmark/README.md

**Files:**
- Create: `benchmark/README.md`

- [ ] **Step 1: Write README.md**

```markdown
# A/B Benchmarking Framework

用于 Deep Research Agent 版本间 A/B 对比测试的基础设施。

## 快速开始

```bash
# 1. 冻结搜索（用最新版本）
git checkout main
uv run deepresearch "查询文本" --save-search benchmark/frozen/q1.json --max-subquestions 4 --results-per-query 4

# 2. 回放测试（各版本）
git checkout v0.5.2
uv run deepresearch --replay-search benchmark/frozen/q1.json --output benchmark/results/v0.5.2-q1-run1.json

# 3. 对比分析
python benchmark/compare.py benchmark/results/ --config benchmark/queries.json
```

## 目录结构

```
benchmark/
├── queries.json              # 查询配置和测试定义
├── frozen/                   # 冻结的搜索结果
├── results/                  # 各版本运行输出
├── scripts/
│   └── replay_v031.py        # v0.3.1 回放适配器
├── compare.py                # 对比脚本
└── README.md
```

## 配置

编辑 `queries.json` 添加/修改查询和阈值。

## 版本要求

- v0.4+: 内置 `--save-search` 和 `--replay-search`
- v0.3.1: 使用 `scripts/replay_v031.py` 适配器
```

- [ ] **Step 2: Commit**

```bash
git add benchmark/README.md
git commit -m "docs: add benchmark framework README"
```

---

### Task 6: Tests for compare.py

**Files:**
- Create: `benchmark/tests/test_compare.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for benchmark/compare.py."""
import json
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compare import load_results, compute_test_a, compute_test_b, compute_test_c


def _make_result_dir(version_qid_run_data: dict) -> Path:
    """Create a temp directory with result JSONs from dict."""
    d = Path(tempfile.mkdtemp(prefix="bench-test-"))
    for (version, qid, run), data in version_qid_run_data.items():
        path = d / f"{version}-{qid}-run{run}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    return d


def test_load_results_single_run():
    config = {
        "versions": ["v0.4"],
        "query_ids": ["q1"],
        "runs_per_query": 1,
    }
    data = _make_result_dir({
        ("v0.4", "q1", 1): {"evidence_metrics": {"evidence_cards": 20, "extracted_sources": 12}},
    })
    results = load_results(data, config)
    assert "v0.4" in results
    assert "q1" in results["v0.4"]
    assert len(results["v0.4"]["q1"]) == 1


def test_compute_test_a_claims_per_source():
    data = {
        "v0.3.1": {
            "q1": [{"evidence_metrics": {"evidence_cards": 8, "extracted_sources": 10, "corroboration": {"strongly_corroborated": 6, "weakly_corroborated": 2, "single_source": 0}}}],
        },
        "v0.4": {
            "q1": [{"evidence_metrics": {"evidence_cards": 24, "extracted_sources": 15, "corroboration": {"strongly_corroborated": 8, "weakly_corroborated": 8, "single_source": 8}}}],
        },
    }
    results = compute_test_a(data)
    assert results["v0.3.1"]["claims_per_source"] == 0.8
    assert results["v0.4"]["claims_per_source"] == 1.6


def test_compute_test_b_score_stats():
    data = {
        "v0.4": {
            "q1": [
                {"review": {"score": 84}}, {"review": {"score": 88}},
                {"review": {"score": 92}}, {"review": {"score": 85}},
                {"review": {"score": 90}}, {"review": {"score": 87}},
            ],
        },
    }
    results = compute_test_b(data)
    assert results["v0.4"]["n_scores"] == 6
    assert 83 < results["v0.4"]["score_mean"] < 93
    assert results["v0.4"]["score_std"] > 0


def test_compute_test_c_rewrites():
    data = {
        "v0.5.2": {
            "q5": [{"review_rewritten": True, "review": {"score": 78}, "evidence_metrics": {"evidence_cards": 5, "extracted_sources": 3}}],
            "q1": [{"review_rewritten": False, "review": {"score": 85}, "evidence_metrics": {"evidence_cards": 26, "extracted_sources": 15}}],
        },
    }
    results = compute_test_c(data)
    assert results["v0.5.2"]["rewrites_triggered"] == 1
    assert results["v0.5.2"]["avg_score"] == 81.5
```

- [ ] **Step 2: Run tests**

```bash
cd benchmark && python -m pytest tests/test_compare.py -v
```
Expected: 4 passed

- [ ] **Step 3: Commit**

```bash
git add benchmark/tests/test_compare.py
git commit -m "test: add unit tests for benchmark comparison script"
```

---

### Task 7: End-to-End Smoke Test

**Files:**
- No new files — manual verification

- [ ] **Step 1: Freeze one query**

```bash
git checkout main
uv run deepresearch "固态电池 2026 年商业化进展" \
  --max-subquestions 2 --results-per-query 2 \
  --save-search benchmark/frozen/q2-solid-state.json
```
Expected: `benchmark/frozen/q2-solid-state.json` created

- [ ] **Step 2: Replay on current version in dry-run mode**

```bash
uv run deepresearch --replay-search benchmark/frozen/q2-solid-state.json \
  --dry-run --output benchmark/results/v0.5.2-q2-solid-state-run1.json
```
Expected: `benchmark/results/v0.5.2-q2-solid-state-run1.json` created with evidence data

- [ ] **Step 3: Run compare.py**

```bash
python benchmark/compare.py benchmark/results/ --config benchmark/queries.json
```
Expected: Prints comparison report with available data

- [ ] **Step 4: Verify compare.py output**

```bash
python benchmark/compare.py benchmark/results/ --config benchmark/queries.json
```

Expected output should show:
```
Test A: ... — extraction suppression
  Status: PASS (if v0.3.1 data available) or "No data"
```

If adjustments were needed during smoke test:

```bash
git add benchmark/
git commit -m "chore: end-to-end smoke test adjustments for benchmark framework"
```
