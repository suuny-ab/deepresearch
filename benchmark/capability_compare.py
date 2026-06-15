"""Compare capability evaluation results across architectures.

Reads JSON result files and generates a comparison matrix report with:
- Per-question quality scores (5 dimensions × 3 architectures)
- Per-question process metrics
- Overall summary with Limitations section
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any

# ---------------------------------------------------------------------------
# Display config
# ---------------------------------------------------------------------------

DIMENSION_LABELS = {
    # Factual Depth
    "distinct_claims": ("声明数", "↑"),
    "quality_weighted_claims": ("质量加权声明", "↑"),
    "avg_sources_per_claim": ("每声明均源", "↑"),
    "single_source_ratio": ("单源占比", "↓"),
    "max_corroboration_depth": ("最深印证", "↑"),
    # Exploration Breadth
    "unique_domains_cited": ("引用域名数", "↑"),
    "fulltext_ratio": ("全文提取率", "↑"),
    # Corroboration Strength
    "strong_corroboration_pct": ("强交叉验证%", "↑"),
    "weak_corroboration_pct": ("弱交叉验证%", "↑"),
    "cross_perspective_pct": ("跨视角验证%", "↑"),
    "contradictions_acknowledged": ("矛盾已标注", "✓"),
    # Structural Completeness
    "coverage_score": ("覆盖度", "↑"),
    "sections_present": ("已覆盖章节", "—"),
    # Uncertainty Honesty
    "honesty_score": ("诚实度(1-5)", "↑"),
    "hedge_word_count": ("保留措辞数", "↑"),
    "contradiction_presented": ("呈现矛盾", "✓"),
    # Composite
    "composite_score": ("综合分", "↑"),
}

PROCESS_LABELS = {
    "wall_time_seconds": ("墙钟时间(s)", ""),
    "total_tokens": ("Token总量", ""),
    "total_cost_usd": ("成本(USD)", ""),
    "llm_call_count": ("LLM调用次数", ""),
    "search_query_count": ("搜索Query数", ""),
    "pages_fetched": ("抓取页面数", ""),
    "iterations": ("循环轮次", ""),
    "error_count": ("错误数", ""),
}

_RESULT_GROUPS = [
    ("事实深度", [
        "distinct_claims", "quality_weighted_claims", "avg_sources_per_claim",
        "single_source_ratio", "max_corroboration_depth",
    ]),
    ("探索广度", [
        "unique_domains_cited", "fulltext_ratio",
    ]),
    ("交叉验证强度", [
        "strong_corroboration_pct", "weak_corroboration_pct",
        "cross_perspective_pct", "contradictions_acknowledged",
    ]),
    ("结构完整性", ["coverage_score", "sections_present"]),
    ("不确定性诚实度", ["honesty_score", "hedge_word_count", "contradiction_presented"]),
]

_LIMITATIONS = """## ⚠️ Limitations

1. **事实正确性** — 本评估测量报告的方法论质量（结构完整性、来源支撑度、不确定性诚实度），不直接测量事实正确性。Q1（固态电池）将对 strongly_corroborated + high confidence 的声明进行人工事实核实作为补充。
2. **Judge 模型** — Coverage 和 Honesty 评分使用 DeepSeek v4-pro（与生成报告相同的模型），存在自评偏差风险。后续应使用独立 judge 模型（如 Claude/GPT-4）。
3. **样本量** — 3 题 × 3 轮 = 每架构 9 个数据点。不足以进行统计显著性检验。结论为方向性指示，非统计验证。
4. **矛盾检测** — 当前为词法级别（正则匹配矛盾标记词），已知漏检语义矛盾和隐含矛盾的盲区。
5. **N/A 字段** — `cross_perspective_pct` 为 Multi-Agent 特有架构能力，Pipeline/ReAct 标记 N/A。`fulltext_ratio` 对 ReAct 不适用（ReAct 用 web_fetch 而非 Tavily extract），标记 N/A。"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_val(val: Any, direction: str = "", best_val: Any = None) -> str:
    """Format a value for display, handling None/N/A and best-value bolding."""
    if val is None:
        return "N/A"
    if isinstance(val, bool):
        s = "✓" if val else "—"
    elif isinstance(val, float):
        s = f"{val:.3f}" if abs(val) < 10 else f"{val:.1f}"
    else:
        s = str(val)

    # Bold if this is the best value (direction-aware)
    if best_val is not None and val is not None and not isinstance(val, (bool, list)):
        try:
            if (direction == "↑" and float(val) >= float(best_val) * 0.99) or \
               (direction == "↓" and float(val) <= float(best_val) * 1.01):
                s = f"**{s}**"
        except (ValueError, TypeError):
            pass
    return s


def _safe_mean(values: list, default: Any = None) -> Any:
    """Compute mean, returning default for empty or mixed-type lists."""
    nums = [v for v in values if isinstance(v, (int, float))]
    return mean(nums) if nums else default


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------

def compare(results: list[dict], output_path: Path | None = None) -> str:
    """Generate the full capability comparison report."""
    by_question: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        qid = r.get("question_id", "?")
        arch = r.get("architecture", "?")
        by_question[qid][arch].append(r)

    lines: list[str] = []
    lines.append("# Architecture Capability Comparison")
    lines.append("")
    lines.append(_LIMITATIONS)
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Per-question tables ---
    for qid in sorted(by_question):
        lines.append(f"## {qid}")
        lines.append("")

        arch_data = by_question[qid]

        # Per-architecture means
        arch_means: dict[str, dict[str, Any]] = {}
        for arch, rounds in arch_data.items():
            caps = [r.get("capability", {}) for r in rounds if r.get("capability")]
            if not caps:
                continue
            means: dict[str, Any] = {}
            for key in DIMENSION_LABELS:
                values = [c.get(key) for c in caps if c.get(key) is not None]
                if not values:
                    means[key] = None
                elif isinstance(values[0], (int, float)):
                    means[key] = _safe_mean(values, 0.0)
                else:
                    means[key] = values[0]  # bool, list — take first
            arch_means[arch] = means

        # --- Quality Matrix ---
        lines.append("### Quality Scores (mean of 3 rounds)")
        lines.append("")

        for group_name, keys in _RESULT_GROUPS:
            lines.append(f"**{group_name}**")
            lines.append("")

            header = "| 指标 | 方向 |"
            for arch in sorted(arch_means):
                header += f" {arch} |"
            lines.append(header)
            lines.append("|------|-----|" + "------|" * len(arch_means))

            for key in keys:
                label, direction = DIMENSION_LABELS.get(key, (key, ""))
                row = f"| {label} | {direction} |"

                # Find best value for this metric
                non_none = {a: m.get(key) for a, m in arch_means.items() if m.get(key) is not None}
                if non_none and direction == "↑":
                    best_val = max(v for v in non_none.values() if isinstance(v, (int, float)))
                elif non_none and direction == "↓":
                    best_val = min(v for v in non_none.values() if isinstance(v, (int, float)))
                else:
                    best_val = None

                for arch in sorted(arch_means):
                    val = arch_means[arch].get(key)
                    if key == "sections_present" and isinstance(val, list):
                        val_str = str(len(val))
                    else:
                        val_str = _fmt_val(val, direction, best_val)
                    row += f" {val_str} |"
                lines.append(row)
            lines.append("")

        # --- Process Metrics ---
        lines.append("### Process Metrics (mean of 3 rounds)")
        lines.append("")

        proc_header = "| 指标 |"
        for arch in sorted(arch_data):
            proc_header += f" {arch} |"
        lines.append(proc_header)
        lines.append("|------|" + "------|" * len(arch_data))

        for key, (label, _) in PROCESS_LABELS.items():
            row = f"| {label} |"
            for arch in sorted(arch_data):
                vals = [
                    r.get("process", {}).get(key)
                    for r in arch_data[arch] if r.get("process")
                ]
                # Filter out None (N/A)
                vals = [v for v in vals if v is not None]
                if not vals:
                    row += " N/A |"
                    continue
                if isinstance(vals[0], (int, float)):
                    avg_val = mean(vals)
                    if key == "total_cost_usd":
                        row += f" ${avg_val:.4f} |"
                    elif isinstance(avg_val, float) and abs(avg_val) < 100:
                        row += f" {avg_val:.1f} |"
                    else:
                        row += f" {avg_val:.0f} |"
                else:
                    row += f" {vals[0]} |"
            lines.append(row)

        # --- Winner ---
        lines.append("")
        valid = {a: m for a, m in arch_means.items() if m.get("composite_score") is not None}
        if valid:
            best_arch = max(valid, key=lambda a: valid[a].get("composite_score", 0))
            best_score = valid[best_arch].get("composite_score", 0)
            lines.append(f"### 🏆 Winner: **{best_arch}** (composite {best_score:.3f})")
        lines.append("")

        # Variance
        for arch in sorted(arch_data):
            cs = [
                r.get("capability", {}).get("composite_score")
                for r in arch_data[arch] if r.get("capability", {}).get("composite_score") is not None
            ]
            if len(cs) >= 2:
                sd = stdev(cs)
                lines.append(f"- {arch}: σ = {sd:.3f} ({len(cs)} rounds)")

        lines.append("")
        lines.append("---")
        lines.append("")

    # --- Overall Summary ---
    lines.append("## Overall Summary")
    lines.append("")

    overall: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for qid, archs in by_question.items():
        for arch, rounds in archs.items():
            for r in rounds:
                cap = r.get("capability", {})
                if cap:
                    for k in ["composite_score", "coverage_score", "honesty_score",
                               "strong_corroboration_pct", "distinct_claims",
                               "quality_weighted_claims"]:
                        v = cap.get(k)
                        if v is not None and isinstance(v, (int, float)):
                            overall[arch][k].append(v)
                proc = r.get("process", {})
                if proc:
                    for k in ["wall_time_seconds", "total_tokens", "total_cost_usd"]:
                        v = proc.get(k)
                        if v is not None and isinstance(v, (int, float)):
                            overall[arch][k].append(v)

    lines.append("| 架构 | 综合分 | 质量加权声明 | 覆盖度 | 诚实度 | 强印证% | 时间(s) | Token | 成本 |")
    lines.append("|------|--------|-------------|--------|--------|---------|---------|-------|------|")
    for arch in ["pipeline", "multi-agent", "react"]:
        if arch not in overall:
            continue
        m = lambda key: mean(overall[arch][key]) if overall[arch][key] else 0
        lines.append(
            f"| {arch} | {m('composite_score'):.3f} | {m('quality_weighted_claims'):.1f} | "
            f"{m('coverage_score'):.2f} | {m('honesty_score'):.1f} | "
            f"{m('strong_corroboration_pct'):.1%} | "
            f"{m('wall_time_seconds'):.0f} | {m('total_tokens'):.0f} | ${m('total_cost_usd'):.4f} |"
        )

    report = "\n".join(lines)
    if output_path:
        output_path.write_text(report, encoding="utf-8")
        print(f"Report saved to {output_path}")
    return report


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print("Usage: python capability_compare.py <result1.json> [result2.json ...]")
        print("       python capability_compare.py results_dir/")
        sys.exit(1)

    results: list[dict] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.is_dir():
            for f in sorted(path.glob("*.json")):
                try:
                    results.append(json.loads(f.read_text(encoding="utf-8")))
                except Exception:
                    pass
        elif path.is_file():
            try:
                results.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                print(f"Error loading {path}: {exc}", file=sys.stderr)

    if not results:
        print("No results loaded.", file=sys.stderr)
        sys.exit(1)

    report = compare(results)
    print(report)


if __name__ == "__main__":
    main()
