"""Compare two local eval result files.

Usage::

    uv run python benchmark/compare.py results/v0.5.2.json results/v0.5.3.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Chinese labels
# ---------------------------------------------------------------------------

_METRIC_LABELS = {
    # Planning
    "subquestion_count": "子问题数",
    "search_query_count": "搜索词总数",
    # Search
    "search_result_count": "搜索结果数",
    "domain_diversity": "域名多样性",
    # Extraction
    "extracted_claim_count": "Claim 提取数",
    "claims_per_source": "每来源 Claim 数",
    # Validation
    "evidence_card_count": "证据卡总数",
    "extraction_retention": "提取→验证保留率",
    "corroboration_strong_ratio": "强印证占比",
    "corroboration_weak_ratio": "弱印证占比",
    # Reporting
    "citation_compliance": "引用合规",
    "cross_validation_usage": "交叉验证利用率",
    "source_utilization": "来源利用率",
    "report_length": "报告长度",
    "citation_density": "引用密度",
    "review_score": "自评分数",
    # Aggregates
    "citation_pass_rate": "引用通过率",
    "avg_review_score": "平均自评分数",
    "avg_citation_compliance": "平均引用合规",
    "avg_source_utilization": "平均来源利用率",
    "avg_cross_validation_usage": "平均交叉验证利用率",
    "avg_subquestion_count": "平均子问题数",
    "avg_search_query_count": "平均搜索词数",
    "avg_search_result_count": "平均搜索结果数",
    "avg_domain_diversity": "平均域名多样性",
    "avg_extracted_claim_count": "平均 Claim 数",
    "avg_claims_per_source": "平均每来源 Claim",
    "avg_evidence_card_count": "平均证据卡数",
    "avg_extraction_retention": "平均提取保留率",
    "avg_corroboration_strong_ratio": "平均强印证占比",
    "avg_corroboration_weak_ratio": "平均弱印证占比",
    "avg_report_length": "平均报告长度",
    "avg_citation_density": "平均引用密度",
}

_PER_QUESTION_ORDER = [
    # Planning
    "subquestion_count",
    "search_query_count",
    # Search
    "search_result_count",
    "domain_diversity",
    # Extraction
    "extracted_claim_count",
    "claims_per_source",
    # Validation
    "evidence_card_count",
    "extraction_retention",
    "corroboration_strong_ratio",
    "corroboration_weak_ratio",
    # Reporting
    "citation_compliance",
    "cross_validation_usage",
    "source_utilization",
    "report_length",
    "citation_density",
    "review_score",
]


def _fmt_delta(delta: float) -> str:
    if delta > 0:
        return f"+{delta:.3f}"
    if delta < 0:
        return f"{delta:.3f}"
    return " 0.000"


def _fmt_score(value: float) -> str:
    return f"{value:.3f}"


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <baseline.json> <candidate.json>", file=sys.stderr)
        sys.exit(1)

    baseline_path = Path(sys.argv[1])
    candidate_path = Path(sys.argv[2])

    for label, path in [("基线", baseline_path), ("候选", candidate_path)]:
        if not path.exists():
            print(f"错误: {label} 文件不存在: {path}", file=sys.stderr)
            sys.exit(1)

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))

    from deepresearch.compare import compute_diff

    diff = compute_diff(baseline, candidate)

    # ---------- header ----------
    print(f"基线版本: {diff['baseline_version']}")
    print(f"候选版本: {diff['candidate_version']}")
    print()

    # ---------- per-question table ----------
    col_headers = f"{'问题':<38} {'指标':<16} {'基线':>8} {'候选':>8} {'变化':>8}"
    print(col_headers)
    print("-" * len(col_headers) + "─" * 22)

    for entry in diff["per_question"]:
        name = entry["question"][:36]
        if entry.get("missing"):
            print(f"{name:<38} {'(某版本缺失)':<16}")
            continue
        for metric_key in _PER_QUESTION_ORDER:
            if metric_key == "cross_validation_usage" and entry.get("_cv_na"):
                label = _METRIC_LABELS.get(metric_key, metric_key)
                display_name = name if metric_key == _PER_QUESTION_ORDER[0] else ""
                print(f"{display_name:<38} {label:<16} {'(不适用)':>30}")
                continue
            m = entry.get(metric_key)
            if m is None:
                continue
            label = _METRIC_LABELS.get(metric_key, metric_key)
            display_name = name if metric_key == _PER_QUESTION_ORDER[0] else ""
            print(
                f"{display_name:<38} {label:<16} {_fmt_score(m['before']):>8} "
                f"{_fmt_score(m['after']):>8} {_fmt_delta(m['delta']):>8}"
            )
        print()

    # ---------- aggregates ----------
    print("=" * 78 + "─" * 22)
    print(f"{'聚合指标':<38} {'':<16} {'基线':>8} {'候选':>8} {'变化':>8}")
    print("-" * 78 + "─" * 22)
    for key, agg in diff["aggregates"].items():
        label = _METRIC_LABELS.get(key, key)
        print(
            f"{label:<38} {'':<16} {_fmt_score(agg['before']):>8} "
            f"{_fmt_score(agg['after']):>8} {_fmt_delta(agg['delta']):>8}"
        )

    # ---------- missing ----------
    if diff["missing_in_candidate"]:
        print(f"\n⚠  候选版本缺失的问题: {diff['missing_in_candidate']}")
    if diff["missing_in_baseline"]:
        print(f"\n⚠  基线版本缺失的问题 (候选新增): {diff['missing_in_baseline']}")


if __name__ == "__main__":
    main()
