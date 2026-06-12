"""Tests for benchmark/compare.py."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compare import load_results, compute_test_a, compute_test_b, compute_test_c


def _make_result_dir(version_qid_run_data: dict) -> Path:
    """Create a temp directory with result JSONs from dict.

    Keys are (version, qid, run) tuples, values are data dicts.
    """
    d = Path(tempfile.mkdtemp(prefix="bench-test-"))
    for (version, qid, run), data in version_qid_run_data.items():
        path = d / f"{version}-{qid}-run{run}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    return d


def test_load_results_single_run():
    """load_results correctly loads a single run."""
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


def test_load_results_missing_file():
    """load_results gracefully handles missing result files."""
    config = {
        "versions": ["v0.4"],
        "query_ids": ["q1"],
        "runs_per_query": 3,
    }
    data = _make_result_dir({
        ("v0.4", "q1", 1): {"evidence_metrics": {"evidence_cards": 20, "extracted_sources": 12}},
    })
    results = load_results(data, config)
    # Only run 1 exists, runs 2 and 3 are missing
    assert len(results["v0.4"]["q1"]) == 1


def test_compute_test_a_claims_per_source():
    """Test A correctly computes claims/source ratio."""
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
    # corroboration_rate: v0.3.1 = 8/8 = 1.0, v0.4 = 16/24 = 0.667
    assert results["v0.3.1"]["corroboration_rate"] == 1.0
    assert results["v0.4"]["corroboration_rate"] == round(16/24, 3)


def test_compute_test_b_score_stats():
    """Test B correctly computes score statistics."""
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


def test_compute_test_b_no_data():
    """Test B returns N/A when no scores are available."""
    data = {"v0.4": {}}
    results = compute_test_b(data)
    assert results["v0.4"]["n_scores"] == 0
    assert results["v0.4"]["score_mean"] == "N/A"


def test_compute_test_c_rewrites():
    """Test C correctly counts rewrites and computes metrics."""
    data = {
        "v0.5.2": {
            "q5": [{"review_rewritten": True, "review": {"score": 78}, "evidence_metrics": {"evidence_cards": 5, "extracted_sources": 3}}],
            "q1": [{"review_rewritten": False, "review": {"score": 85}, "evidence_metrics": {"evidence_cards": 26, "extracted_sources": 15}}],
        },
    }
    results = compute_test_c(data)
    assert results["v0.5.2"]["rewrites_triggered"] == 1
    assert results["v0.5.2"]["avg_score"] == 81.5
    assert results["v0.5.2"]["claims_per_source"] == round(31/18, 2)
