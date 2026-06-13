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
from pathlib import Path
from typing import Literal

CheckLevel = Literal["PASS", "WARN", "FAIL"]


# ---------- data structures ----------

class CheckResult:
    """A single metric comparison result."""

    def __init__(self, metric: str, level: CheckLevel, baseline_value: object,
                 new_value: object, message: str):
        self.metric = metric
        self.level = level
        self.baseline_value = baseline_value
        self.new_value = new_value
        self.message = message


class QueryResult:
    """All checks for one query."""

    def __init__(self, query_id: str):
        self.query_id = query_id
        self.checks: list[CheckResult] = []

    @property
    def overall(self) -> CheckLevel:
        if any(c.level == "FAIL" for c in self.checks):
            return "FAIL"
        if any(c.level == "WARN" for c in self.checks):
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
                           "citation_coverage dropped below 1.0")
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
                           "orphan URLs eliminated")
    return CheckResult("orphan_url_count", "PASS", b, n, "")


def _check_errors(baseline_output: dict, new_output: dict) -> CheckResult:
    b_errors = baseline_output.get("errors", [])
    n_errors = new_output.get("errors", [])
    b = len(b_errors) if b_errors else 0
    n = len(n_errors) if n_errors else 0
    if n > b:
        return CheckResult("error_count", "FAIL", b, n,
                           f"errors increased ({b} → {n})")
    return CheckResult("error_count", "PASS", b, n, "")


def _check_claims_per_source(baseline_sm: dict, new_sm: dict) -> CheckResult:
    threshold = 1.5
    b = baseline_sm.get("claims_per_source", 0)
    n = new_sm.get("claims_per_source", 0)
    if n < threshold:
        return CheckResult("claims_per_source", "FAIL", b, n,
                           f"claims_per_source {n} below threshold {threshold}")
    return CheckResult("claims_per_source", "PASS", b, n, "")


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
                           f"domain_diversity dropped significantly ({b} → {n})")
    return CheckResult("domain_diversity", "PASS", b, n, "")


def _check_evidence_count(baseline_sm: dict, new_sm: dict) -> CheckResult:
    b = baseline_sm.get("evidence_card_count", 0)
    n = new_sm.get("evidence_card_count", 0)
    if b > 0 and n < b * 0.5:
        return CheckResult("evidence_card_count", "WARN", b, n,
                           f"evidence_card_count dropped by >50% ({b} → {n})")
    return CheckResult("evidence_card_count", "PASS", b, n, "")


# ---------- check lists ----------

HARD_BLOCKS = [
    _check_citation_coverage,
    _check_orphan_url,
    _check_errors,
    _check_claims_per_source,
    _check_source_utilization,
]

SOFT_WARNS = [
    _check_review_score,
    _check_rewrite_rate,
    _check_domain_diversity,
    _check_evidence_count,
]


# ---------- query-level comparison ----------

def compare_artifacts(baseline_path: Path, new_path: Path) -> QueryResult:
    """Compare two RunArtifact files and return a QueryResult."""
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

    for check_fn in HARD_BLOCKS:
        if check_fn == _check_errors:
            ck = check_fn(baseline_output, new_output)
        else:
            ck = check_fn(baseline_sm, new_sm)
        if ck is not None:
            result.checks.append(ck)

    for check_fn in SOFT_WARNS:
        ck = check_fn(baseline_sm, new_sm)
        if ck is not None:
            result.checks.append(ck)

    return result


def compare_directories(baseline_dir: Path, new_dir: Path) -> dict:
    """Compare all artifact pairs in two directories. Returns a gate report dict."""
    baseline_version = None
    new_version = None
    queries: dict[str, QueryResult] = {}

    for artifact_file in sorted(baseline_dir.glob("*.json")):
        query_id = artifact_file.stem
        new_file = new_dir / f"{query_id}.json"
        if not new_file.exists():
            continue

        result = compare_artifacts(artifact_file, new_file)
        queries[query_id] = result

        if baseline_version is None:
            with open(artifact_file) as f:
                baseline_version = json.load(f)["meta"]["app_version"]
        if new_version is None:
            with open(new_file) as f:
                new_version = json.load(f)["meta"]["app_version"]

    overall: str = "PASS"
    exit_code = 0
    for q in queries.values():
        if q.overall == "FAIL":
            overall = "FAIL"
            exit_code = 1
            break
        if q.overall == "WARN" and overall != "FAIL":
            overall = "WARN"

    return {
        "baseline_version": baseline_version,
        "new_version": new_version,
        "overall": overall,
        "exit_code": exit_code,
        "queries": {
            qid: [
                {
                    "metric": c.metric,
                    "level": c.level,
                    "baseline": c.baseline_value,
                    "new": c.new_value,
                    "message": c.message,
                }
                for c in result.checks
            ]
            for qid, result in queries.items()
        },
    }


# ---------- CLI ----------

def parse_args(argv=None) -> Namespace:
    parser = ArgumentParser(description="Quality gate for A/B version comparison")
    parser.add_argument("--baseline", type=Path, required=True,
                        help="Baseline artifact directory")
    parser.add_argument("--new", type=Path, required=True,
                        help="New version artifact directory")
    parser.add_argument("--run", action="store_true",
                        help="Run replay instead of reading existing artifacts")
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
            detail = c["message"] or f"{c['baseline']} → {c['new']}"
            lines.append(f"    {symbol} {c['metric']}: {detail}")
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
