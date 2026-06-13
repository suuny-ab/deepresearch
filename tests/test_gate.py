"""Tests for gate.py — quality gate for A/B version comparison."""

import json

import pytest


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
    """Write baseline and new artifacts for a single query.

    Directory structure matches benchmark/baselines/ convention:
      baseline_dir/q1.json
      new_dir/q1.json
    """
    baseline_dir = tmp_path / "baseline"
    new_dir = tmp_path / "new"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    new_dir.mkdir(parents=True, exist_ok=True)

    baseline_file = baseline_dir / f"{query_id}.json"
    new_file = new_dir / f"{query_id}.json"

    with open(baseline_file, "w") as f:
        json.dump(_make_artifact("v0.5.2", **baseline_metrics), f)
    with open(new_file, "w") as f:
        json.dump(_make_artifact("v0.6.0", **new_metrics), f)

    return baseline_file, new_file


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


def test_gate_fails_when_source_utilization_drops_below_threshold(tmp_path):
    """source_utilization < 0.8 → 硬阻断 FAIL。"""
    baseline, new = _write_artifacts(
        tmp_path,
        {"evidence_card_count": 10, "claims_per_source": 2.0, "source_utilization": 0.9,
         "corroboration_strong": 5, "corroboration_weak": 3, "corroboration_single": 2,
         "domain_diversity": 5, "review_score": 85, "review_passed": True,
         "rewrite_triggered": False, "citation_coverage": 1.0,
         "source_citation_rate": 1.0, "orphan_url_count": 0,
         "validation_first_pass": True},
        {"evidence_card_count": 14, "claims_per_source": 2.5, "source_utilization": 0.6,
         "corroboration_strong": 8, "corroboration_weak": 4, "corroboration_single": 2,
         "domain_diversity": 6, "review_score": 88, "review_passed": True,
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

    assert report["overall"] == "WARN"  # WARN is reported but doesn't block
    assert report["exit_code"] == 0     # exit 0 = not a hard failure
    warns = [c for q in report["queries"].values() for c in q if c["level"] == "WARN"]
    assert len(warns) > 0


# ---------- per-query independence ----------

def test_gate_per_query_independence(tmp_path):
    """q1 PASS 但 q2 FAIL → 整体 FAIL（不被平均掩盖）。"""
    # q1: all good
    _write_artifacts(
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
    _write_artifacts(
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
    report = compare_directories(tmp_path / "baseline", tmp_path / "new")

    assert report["overall"] == "FAIL"
    q1_checks = report["queries"]["q1"]
    q2_checks = report["queries"]["q2"]
    assert all(c["level"] in ("PASS", "WARN") for c in q1_checks)
    assert any(c["level"] == "FAIL" for c in q2_checks)


# ---------- CLI tests ----------

def test_gate_run_mode_flag_accepted(tmp_path):
    """--run 参数被正确解析。"""
    from benchmark.gate import parse_args
    args = parse_args(["--baseline", str(tmp_path), "--new", str(tmp_path), "--run"])
    assert args.run is True


def test_gate_defaults_to_artifact_mode(tmp_path):
    """不带 --run 时默认为 artifact 对比模式。"""
    from benchmark.gate import parse_args
    args = parse_args(["--baseline", str(tmp_path), "--new", str(tmp_path)])
    assert args.run is False
