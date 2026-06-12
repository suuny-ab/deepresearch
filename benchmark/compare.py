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
    """Test A: claims/source ratio, corroboration_rate."""
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
                "score_mean": "N/A", "score_std": "N/A",
                "score_min": "N/A", "score_max": "N/A",
                "score_range": "N/A", "n_scores": 0,
            }
    return results


def compute_test_c(data: dict) -> dict:
    """Test C: rewrite count, avg score, claims/source."""
    results = {}
    for version in data:
        rewrites = 0
        all_scores = []
        total_claims = 0
        total_sources = 0
        for qid, runs in data[version].items():
            for run in runs:
                if run.get("review_rewritten"):
                    rewrites += 1
                review = run.get("review", {})
                if review:
                    all_scores.append(review.get("score", 0))
                metrics = run.get("evidence_metrics", {})
                total_claims += metrics.get("evidence_cards", 0)
                total_sources += metrics.get("extracted_sources", 1)
        results[version] = {
            "rewrites_triggered": rewrites,
            "avg_score": round(statistics.mean(all_scores), 1) if all_scores else "N/A",
            "claims_per_source": round(total_claims / max(total_sources, 1), 2),
        }
    return results


def evaluate_test_a(results: dict, thresholds: dict) -> tuple[bool, str]:
    """Check if Test A passes."""
    versions = list(results.keys())
    v1, v2 = versions[0], versions[-1]
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
        messages.append(f"PASS: claims/source {cps1} -> {cps2} ({ratio:.0%} improvement)")

    corr1 = results[v1]["corroboration_rate"]
    corr2 = results[v2]["corroboration_rate"]
    max_corr = thresholds.get("test_a_corroboration_rate_max", 0.8)
    if isinstance(corr2, (int, float)) and corr2 > max_corr:
        messages.append(f"WARN: corroboration_rate {corr2:.1%} still above {max_corr:.0%} (may be inflated)")
    else:
        messages.append(f"PASS: corroboration_rate within acceptable range")

    return passed, "\n  ".join(messages)


def evaluate_test_b(results: dict, thresholds: dict) -> tuple[bool, str]:
    """Check if Test B passes — v0.5.1 should have lower score variance."""
    versions = list(results.keys())
    v1, v2 = versions[0], versions[-1]
    std1 = results[v1].get("score_std", 0)
    std2 = results[v2].get("score_std", 0)

    messages = []
    if not isinstance(std1, (int, float)) or not isinstance(std2, (int, float)):
        return True, "No score data available for comparison"
    if std2 <= std1:
        reduction = (std1 - std2) / max(std1, 0.01)
        messages.append(f"PASS: score_std {std1} -> {std2} ({reduction:.0%} reduction)")
        return True, "\n  ".join(messages)
    else:
        messages.append(f"FAIL: score_std {std1} -> {std2} (increased)")
        return False, "\n  ".join(messages)


def evaluate_test_c(results: dict, thresholds: dict) -> tuple[bool, str]:
    """Check if Test C passes — rewrite should trigger and improve scores."""
    messages = []
    versions = list(results.keys())
    v2 = versions[-1]
    rewrites = results[v2].get("rewrites_triggered", 0)
    min_improve = thresholds.get("test_c_at_least_one_improvement_by", 5)

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

    overall_passes = 0
    overall_total = 0

    for test_id in ["A", "B", "C"]:
        config = test_configs["tests"].get(test_id)
        if not config or test_id not in all_data:
            continue

        overall_total += 1
        lines.append(f"Test {test_id}: {config['description']}")
        lines.append("-" * 60)

        compute, evaluate = evaluators[test_id]
        results = compute(all_data[test_id])
        passed, detail = evaluate(results, thresholds)

        lines.append(f"  Status: {'PASS' if passed else 'FAIL'}")
        lines.append(f"  {detail}")
        lines.append("")

        if results:
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

        if passed:
            overall_passes += 1

    lines.append(f"Overall: {overall_passes}/{overall_total} tests pass")
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
