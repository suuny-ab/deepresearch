# Phase 3: Gate 脚本实施计划

> 按 spec §3.3 的硬阻断/软警告规则，实现自动化质量门禁。

## 设计决策

- **默认读已有 artifact**（秒级），`--run` 参数触发实时 replay（~5分钟）
- **按 query 独立判定**，任一 query 硬阻断 FAIL → 整体 exit 1
- **硬阻断**：citation_coverage < 1.0, orphan_url_count > 0, error_count > 0, claims_per_source < 1.5, source_utilization < 0.8
- **软警告**：review_score 下降 ≥ 5, rewrite_rate 上升 ≥ 20pp, domain_diversity 下降 ≥ 20%

## Task 1: 创建 benchmark/tests/test_gate.py（测试先行）

```python
"""Tests for gate.py — quality gate for A/B version comparison."""

import json
import pytest
from pathlib import Path


# ---------- helpers ----------

def _make_artifact(app_version, evidence_card_count, claims_per_source,
                   source_utilization, corroboration_strong, corroboration_weak,
                   corroboration_single, domain_diversity, review_score,
                   review_passed, rewrite_triggered, citation_coverage,
                   source_citation_rate, orphan_url_count, validation_first_pass,
                   error_count=0):
    """Build a minimal RunArtifact dict for gate testing."""
    return {
        "meta": {
            "app_version": app_version, "schema_version": 1,
            "timestamp": "2026-06-13T00:00:00Z", "mode": "replay", "config": {},
        },
        "inputs": {"question": "test", "subquestions": []},
        "pipeline": {"search_results": [], "extracted_claims": [], "evidence_cards": [], "evidence_metrics": {}},
        "standard_metrics": {
            "evidence_card_count": evidence_card_count,
            "claims_per_source": claims_per_source,
            "source_utilization": source_utilization,
            "corroboration_strong": corroboration_strong,
            "corroboration_weak": corroboration_weak,
            "corroboration_single": corroboration_single,
            "domain_diversity": domain_diversity,
            "review_score": review_score,
            "review_passed": review_passed,
            "rewrite_triggered": rewrite_triggered,
            "citation_coverage": citation_coverage,
            "source_citation_rate": source_citation_rate,
            "orphan_url_count": orphan_url_count,
            "validation_first_pass": validation_first_pass,
        },
        "output": {
            "report_markdown": "", "report_status": "success",
            "review": None, "validation_failures": [],
            "errors": ["error"] if error_count > 0 else [],
            "output_path": "",
        },
    }


def _write_artifacts(tmp_path, baseline_metrics, new_metrics, query_id="q1"):
    """Write baseline and new artifacts for a single query."""
    baseline_dir = tmp_path / "baseline" / query_id
    new_dir = tmp_path / "new" / query_id
    baseline_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)

    baseline_file = baseline_dir / "artifact.json"
    new_file = new_dir / "artifact.json"

    with open(baseline_file, "w") as f:
        json.dump(_make_artifact("v0.5.2", **baseline_metrics), f)
    with open(new_file, "w") as f:
        json.dump(_make_artifact("v0.6.0", **new_metrics), f)

    return baseline_dir, new_dir


# ---------- gate result structure ----------

def test_gate_result_has_required_fields():
    """验证 gate 输出结构包含必需的顶层字段。"""
    from benchmark.gate import GateResult
    result = GateResult(query_id="q1", overall="PASS", checks=[])
    assert result.query_id == "q1"
    assert result.overall == "PASS"
    assert result.checks == []


# ---------- hard block tests ----------

def test_gate_all_pass_when_metrics_improve(tmp_path):
    """所有指标都 improved → 每个 query PASS，整体 exit 0。"""
    baseline, new = _write_artifacts(
        tmp_path,
        {"evidence_card_count": 10, "claims_per_source": 2.0, "source_utilization": 0.9,
         "corroboration_strong": 5, "corroboration_weak": 3, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 85, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
        {"evidence_card_count": 14, "claims_per_source": 2.5, "source_utilization": 0.95,
         "corroboration_strong": 8, "corroboration_weak": 4, "corroboration_single": 2,
         "domain_diversity": 6, "review_score": 88, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
    )

    from benchmark.gate import compare_directories
    report = compare_directories(baseline.parent, new.parent)

    assert report["overall"] == "PASS"
    assert report["exit_code"] == 0


def test_gate_fails_when_citation_coverage_drops(tmp_path):
    """citation_coverage < 1.0 → 硬阻断 FAIL。"""
    baseline, new = _write_artifacts(
        tmp_path,
        {"evidence_card_count": 10, "claims_per_source": 2.0, "source_utilization": 0.9,
         "corroboration_strong": 5, "corroboration_weak": 3, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 85, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
        {"evidence_card_count": 14, "claims_per_source": 2.5, "source_utilization": 0.95,
         "corroboration_strong": 8, "corroboration_weak": 4, "corroboration_single": 2,
         "domain_diversity": 6, "review_score": 88, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 0.8,
         "source_citation_rate": 0.8, "orphan_url_count": 0,
         "validation_first_pass": False},
    )

    from benchmark.gate import compare_directories
    report = compare_directories(baseline.parent, new.parent)

    assert report["overall"] == "FAIL"
    assert report["exit_code"] == 1


def test_gate_fails_when_orphan_url_appears(tmp_path):
    """orphan_url_count 从 0 变 >0 → 硬阻断 FAIL。"""
    baseline, new = _write_artifacts(
        tmp_path,
        {"evidence_card_count": 10, "claims_per_source": 2.0, "source_utilization": 0.9,
         "corroboration_strong": 5, "corroboration_weak": 3, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 85, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
        {"evidence_card_count": 14, "claims_per_source": 2.5, "source_utilization": 0.95,
         "corroboration_strong": 8, "corroboration_weak": 4, "corroboration_single": 2,
         "domain_diversity": 6, "review_score": 88, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 3,
         "validation_first_pass": True},
    )

    from benchmark.gate import compare_directories
    report = compare_directories(baseline.parent, new.parent)

    assert report["overall"] == "FAIL"
    assert report["exit_code"] == 1


def test_gate_fails_when_error_count_increases(tmp_path):
    """error_count 从 0 变 >0 → 硬阻断 FAIL。"""
    baseline, new = _write_artifacts(
        tmp_path,
        {"evidence_card_count": 10, "claims_per_source": 2.0, "source_utilization": 0.9,
         "corroboration_strong": 5, "corroboration_weak": 3, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 85, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True, "error_count": 0},
        {"evidence_card_count": 14, "claims_per_source": 2.5, "source_utilization": 0.95,
         "corroboration_strong": 8, "corroboration_weak": 4, "corroboration_single": 2,
         "domain_diversity": 6, "review_score": 88, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True, "error_count": 2},
    )

    from benchmark.gate import compare_directories
    report = compare_directories(baseline.parent, new.parent)

    assert report["overall"] == "FAIL"
    assert report["exit_code"] == 1


def test_gate_fails_when_claims_per_source_drops_below_threshold(tmp_path):
    """claims_per_source < 1.5 → 硬阻断 FAIL。"""
    baseline, new = _write_artifacts(
        tmp_path,
        {"evidence_card_count": 10, "claims_per_source": 2.0, "source_utilization": 0.9,
         "corroboration_strong": 5, "corroboration_weak": 3, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 85, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
        {"evidence_card_count": 5, "claims_per_source": 0.8, "source_utilization": 0.9,
         "corroboration_strong": 2, "corroboration_weak": 1, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 85, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
    )

    from benchmark.gate import compare_directories
    report = compare_directories(baseline.parent, new.parent)

    assert report["overall"] == "FAIL"


# ---------- soft warn tests ----------

def test_gate_warns_when_review_score_drops(tmp_path):
    """review_score 下降 ≥ 5 → WARN 但整体 PASS。"""
    baseline, new = _write_artifacts(
        tmp_path,
        {"evidence_card_count": 10, "claims_per_source": 2.0, "source_utilization": 0.9,
         "corroboration_strong": 5, "corroboration_weak": 3, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 88, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
        {"evidence_card_count": 10, "claims_per_source": 2.0, "source_utilization": 0.9,
         "corroboration_strong": 5, "corroboration_weak": 3, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 82, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
    )

    from benchmark.gate import compare_directories
    report = compare_directories(baseline.parent, new.parent)

    assert report["overall"] == "PASS"  # warn doesn't block
    assert report["exit_code"] == 0
    # Check that a WARN exists
    warns = [c for q in report["queries"].values() for c in q if c["level"] == "WARN"]
    assert len(warns) > 0


# ---------- per-query independence ----------

def test_gate_per_query_independence(tmp_path):
    """q1 PASS 但 q2 FAIL → 整体 FAIL（不被平均掩盖）。"""
    # q1: all good
    q1_base, q1_new = _write_artifacts(
        tmp_path,
        {"evidence_card_count": 10, "claims_per_source": 2.0, "source_utilization": 0.9,
         "corroboration_strong": 5, "corroboration_weak": 3, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 85, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
        {"evidence_card_count": 14, "claims_per_source": 2.5, "source_utilization": 0.95,
         "corroboration_strong": 8, "corroboration_weak": 4, "corroboration_single": 2,
         "domain_diversity": 6, "review_score": 88, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
        query_id="q1",
    )
    # q2: citation degraded
    q2_base, q2_new = _write_artifacts(
        tmp_path,
        {"evidence_card_count": 10, "claims_per_source": 2.0, "source_utilization": 0.9,
         "corroboration_strong": 5, "corroboration_weak": 3, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 85, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
        {"evidence_card_count": 14, "claims_per_source": 2.5, "source_utilization": 0.95,
         "corroboration_strong": 8, "corroboration_weak": 4, "corroboration_single": 2,
         "domain_diversity": 6, "review_score": 88, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 0.5,
         "source_citation_rate": 0.5, "orphan_url_count": 0,
         "validation_first_pass": False},
        query_id="q2",
    )

    from benchmark.gate import compare_directories
    baseline_root = tmp_path / "baseline"
    new_root = tmp_path / "new"
    report = compare_directories(baseline_root, new_root)

    assert report["overall"] == "FAIL"
    q1_checks = report["queries"]["q1"]
    q2_checks = report["queries"]["q2"]
    assert all(c["level"] in ("PASS", "WARN") for c in q1_checks)
    assert any(c["level"] == "FAIL" for c in q2_checks)


# ---------- --run mode (placeholder) ----------

def test_gate_run_mode_flag_accepted(tmp_path, monkeypatch):
    """--run 参数被正确解析为 replay mode 标记。"""
    import sys
    # Verify the CLI accepts the --run flag (smoke test for arg parsing)
    # Full integration test would require mocking _build_app
    from benchmark.gate import parse_args
    args = parse_args(["--baseline", str(tmp_path), "--new", str(tmp_path), "--run"])
    assert args.run is True


def test_gate_defaults_to_artifact_mode(tmp_path):
    """不带 --run 时默认为 artifact 对比模式。"""
    from benchmark.gate import parse_args
    args = parse_args(["--baseline", str(tmp_path), "--new", str(tmp_path)])
    assert args.run is False
```

## Task 2: 实现 benchmark/gate.py

核心结构：

```python
#!/usr/bin/env python3
"""Quality gate for A/B version comparison.

Usage:
  # Compare existing artifacts (fast, default)
  python benchmark/gate.py --baseline benchmark/baselines/v0.5.2 --new benchmark/baselines/v0.6.0

  # Run replay then compare (slow but guarantees matching conditions)
  python benchmark/gate.py --baseline v0.5.2 --new HEAD --run
"""

import json
import sys
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

CheckLevel = Literal["PASS", "WARN", "FAIL"]


@dataclass
class CheckResult:
    metric: str
    level: CheckLevel
    baseline_value: object
    new_value: object
    message: str


@dataclass
class QueryResult:
    query_id: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def overall(self) -> CheckLevel:
        if any(c.level == "FAIL" for c in self.checks):
            return "FAIL"
        if any(c.level == "WARN" for c in self.checks):
            return "WARN"
        return "PASS"


@dataclass
class GateReport:
    baseline_version: str
    new_version: str
    queries: dict[str, QueryResult]

    @property
    def overall(self) -> CheckLevel:
        if any(q.overall == "FAIL" for q in self.queries.values()):
            return "FAIL"
        if any(q.overall == "WARN" for q in self.queries.values()):
            return "WARN"
        return "PASS"


# ---------- hard block checks ----------

def _check_citation_coverage(baseline_sm: dict, new_sm: dict) -> CheckResult | None:
    b = baseline_sm.get("citation_coverage")
    n = new_sm.get("citation_coverage")
    if b is None or n is None:
        return None  # no report in dry-run — skip
    if n < 1.0:
        return CheckResult("citation_coverage", "FAIL", b, n,
                           f"citation_coverage dropped below 1.0 ({b} → {n})")
    return CheckResult("citation_coverage", "PASS", b, n, "")


def _check_orphan_url(baseline_sm: dict, new_sm: dict) -> CheckResult | None:
    b = baseline_sm.get("orphan_url_count", 0)
    n = new_sm.get("orphan_url_count", 0)
    if b is None or n is None:
        return None
    if n > 0:
        return CheckResult("orphan_url_count", "FAIL", b, n,
                           f"orphan URLs detected: {n}")
    if b > 0 and n == 0:
        return CheckResult("orphan_url_count", "PASS", b, n,
                           f"orphan URLs eliminated ({b} → 0)")
    return CheckResult("orphan_url_count", "PASS", b, n, "")


def _check_errors(baseline_output: dict, new_output: dict) -> CheckResult:
    b = len(baseline_output.get("errors", []))
    n = len(new_output.get("errors", []))
    if n > 0:
        return CheckResult("error_count", "FAIL", b, n,
                           f"errors detected: {n}")
    return CheckResult("error_count", "PASS", b, n, "")


def _check_claims_per_source(baseline_sm: dict, new_sm: dict) -> CheckResult:
    threshold = 1.5
    b = baseline_sm.get("claims_per_source", 0)
    n = new_sm.get("claims_per_source", 0)
    if n < threshold:
        return CheckResult("claims_per_source", "FAIL", b, n,
                           f"claims_per_source {n} below threshold {threshold}")
    if n >= b:
        return CheckResult("claims_per_source", "PASS", b, n,
                           f"claims_per_source {b} → {n}")
    return CheckResult("claims_per_source", "PASS", b, n,
                       f"claims_per_source {b} → {n} (above threshold, minor drop)")


def _check_source_utilization(baseline_sm: dict, new_sm: dict) -> CheckResult:
    threshold = 0.8
    b = baseline_sm.get("source_utilization", 0)
    n = new_sm.get("source_utilization", 0)
    if n < threshold:
        return CheckResult("source_utilization", "FAIL", b, n,
                           f"source_utilization {n} below threshold {threshold}")
    return CheckResult("source_utilization", "PASS", b, n, "")


# ---------- soft warn checks ----------

def _check_review_score(baseline_sm: dict, new_sm: dict) -> CheckResult | None:
    b = baseline_sm.get("review_score")
    n = new_sm.get("review_score")
    if b is None or n is None:
        return None
    delta = b - n
    if delta >= 5:
        return CheckResult("review_score", "WARN", b, n,
                           f"review_score dropped by {delta} ({b} → {n})")
    return CheckResult("review_score", "PASS", b, n, "")


def _check_rewrite_rate(baseline_sm: dict, new_sm: dict) -> CheckResult:
    b = baseline_sm.get("rewrite_triggered", False)
    n = new_sm.get("rewrite_triggered", False)
    if n and not b:
        return CheckResult("rewrite_triggered", "WARN", b, n,
                           "rewrite newly triggered (was not happening)")
    return CheckResult("rewrite_triggered", "PASS", b, n, "")


def _check_domain_diversity(baseline_sm: dict, new_sm: dict) -> CheckResult:
    b = baseline_sm.get("domain_diversity", 0)
    n = new_sm.get("domain_diversity", 0)
    if b > 0 and n < b * 0.8:
        return CheckResult("domain_diversity", "WARN", b, n,
                           f"domain_diversity dropped by {(b-n)/b:.0%} ({b} → {n})")
    return CheckResult("domain_diversity", "PASS", b, n, "")


def _check_evidence_count(baseline_sm: dict, new_sm: dict) -> CheckResult:
    b = baseline_sm.get("evidence_card_count", 0)
    n = new_sm.get("evidence_card_count", 0)
    if n < b * 0.5:
        return CheckResult("evidence_card_count", "WARN", b, n,
                           f"evidence_card_count dropped by {(b-n)/b:.0%} ({b} → {n})")
    return CheckResult("evidence_card_count", "PASS", b, n, "")


# ---------- query-level comparison ----------

HARD_BLOCKS = [_check_citation_coverage, _check_orphan_url, _check_errors,
               _check_claims_per_source, _check_source_utilization]
SOFT_WARNS = [_check_review_score, _check_rewrite_rate, _check_domain_diversity,
              _check_evidence_count]


def compare_artifacts(baseline_path: Path, new_path: Path) -> QueryResult:
    with open(baseline_path) as f:
        baseline = json.load(f)
    with open(new_path) as f:
        new = json.load(f)

    query_id = baseline_path.stem
    result = QueryResult(query_id=query_id)

    baseline_sm = baseline.get("standard_metrics", {})
    new_sm = new.get("standard_metrics", {})
    baseline_output = baseline.get("output", {})
    new_output = new.get("output", {})

    for check_fn in HARD_BLOCKS + SOFT_WARNS:
        try:
            check = check_fn(baseline_sm if check_fn != _check_errors else baseline_output,
                             new_sm if check_fn != _check_errors else new_output)
        except TypeError:
            # _check_errors takes output, not sm
            check = check_fn(baseline_output, new_output) if check_fn == _check_errors else \
                    check_fn(baseline_sm, new_sm)
        if check is not None:
            result.checks.append(check)

    return result


def compare_directories(baseline_dir: Path, new_dir: Path) -> dict:
    baseline_version = None
    new_version = None
    queries = {}

    for artifact_file in sorted(baseline_dir.glob("*.json")):
        query_id = artifact_file.stem
        new_file = new_dir / f"{query_id}.json"
        if not new_file.exists():
            continue

        result = compare_artifacts(artifact_file, new_file)
        queries[query_id] = result.checks

        if baseline_version is None:
            with open(artifact_file) as f:
                baseline_version = json.load(f)["meta"]["app_version"]
        if new_version is None:
            with open(new_file) as f:
                new_version = json.load(f)["meta"]["app_version"]

    overall = "PASS"
    exit_code = 0
    for qid, checks in queries.items():
        if any(c.level == "FAIL" for c in checks):
            overall = "FAIL"
            exit_code = 1
            break
        if any(c.level == "WARN" for c in checks):
            overall = "WARN"

    return {
        "baseline_version": baseline_version,
        "new_version": new_version,
        "overall": overall,
        "exit_code": exit_code,
        "queries": {qid: [{"metric": c.metric, "level": c.level,
                           "baseline": c.baseline_value, "new": c.new_value,
                           "message": c.message} for c in checks]
                    for qid, checks in queries.items()},
    }


# ---------- CLI ----------

def parse_args(argv=None):
    parser = ArgumentParser(description="Quality gate for A/B version comparison")
    parser.add_argument("--baseline", type=Path, required=True,
                        help="Baseline version tag or artifact directory")
    parser.add_argument("--new", type=Path, required=True,
                        help="New version tag or artifact directory")
    parser.add_argument("--run", action="store_true",
                        help="Run replay instead of reading existing artifacts")
    parser.add_argument("--frozen-dir", type=Path, default=Path("benchmark/frozen"),
                        help="Frozen search data directory (for --run mode)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Write gate report to file instead of stdout")
    return parser.parse_args(argv)


def render_report(report: dict) -> str:
    lines = [
        f"Gate Report: {report['baseline_version']} → {report['new_version']}",
        "=" * 60,
        f"Overall: {report['overall']}",
        "",
    ]
    for qid, checks in report["queries"].items():
        lines.append(f"  {qid}:")
        for c in checks:
            symbol = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[c["level"]]
            lines.append(f"    {symbol} {c['metric']}: {c['message'] or f'{c['baseline']} → {c['new']}'}")
        lines.append("")
    return "\n".join(lines)


def main():
    args = parse_args()

    if args.run:
        print("--run mode: replay-based comparison not yet implemented. Use artifact mode.")
        sys.exit(1)

    report = compare_directories(args.baseline, args.new)
    output_text = render_report(report)

    if args.output:
        args.output.write_text(output_text, encoding="utf-8")
        print(f"Gate report saved to {args.output}")
    else:
        print(output_text)

    sys.exit(report["exit_code"])


if __name__ == "__main__":
    main()
```

### Task 3: 用真实 baselines 跑一次

```bash
uv run python benchmark/gate.py \
  --baseline benchmark/baselines/v0.5.1 \
  --new benchmark/baselines/v0.5.2
```

验证产出有意义的 gate report。

### Task 4: Commit

```bash
git add benchmark/gate.py benchmark/tests/test_gate.py
git commit -m "feat: add gate.py — quality gate for A/B version comparison"
```
