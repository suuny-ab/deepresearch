"""Local evaluation runner and diff-computation utilities.

These operate on the output of :func:`eval_target.make_target` — no
LangSmith API calls are required.  Use :func:`evaluate_all` to run
every benchmark question through all deterministic evaluators and
produce a summary file.  Use :func:`compute_diff` to compare two
such summaries.
"""

from __future__ import annotations

from typing import Any

from deepresearch.evaluators import ALL_EVALUATORS, _FIXED_PER_QUESTION_KEYS

# Derive key lists from the evaluator registry — single source of truth
_ALL_PER_QUESTION_KEYS = [key for key, _fn in ALL_EVALUATORS] + list(_FIXED_PER_QUESTION_KEYS)

_ALL_AGGREGATE_KEYS = ["citation_pass_rate", "avg_review_score"] + [
    f"avg_{k}" for k in _ALL_PER_QUESTION_KEYS
    if k not in _FIXED_PER_QUESTION_KEYS
]


# ---------------------------------------------------------------------------
# evaluate_all
# ---------------------------------------------------------------------------


def evaluate_all(
    target: callable,
    questions: list[dict[str, Any]],
    *,
    version: str,
) -> dict[str, Any]:
    """Run *target* against every question and return a structured summary.

    Parameters
    ----------
    target:
        A ``(inputs: dict) -> dict`` function as returned by
        :func:`~deepresearch.eval_target.make_target`.
    questions:
        Benchmark question list (loaded from ``questions.json``).
    version:
        Human-readable label for this run (e.g. ``"v0.5.3-baseline"``).

    Returns
    -------
    dict
        A summary with keys ``version``, ``questions``, and ``aggregates``.
    """
    entries: list[dict[str, Any]] = []
    for q in questions:
        outputs = target({"question": q["question"]})

        # Run all evaluators via the registry
        scores: dict[str, Any] = {}
        for key, fn in ALL_EVALUATORS:
            result = fn(outputs)
            scores[key] = result["score"]
            # Preserve cross_validation_usage applicability flag
            if key == "cross_validation_usage":
                scores["_cv_applicable"] = result.get("applicable", True)

        entries.append({
            "id": q["id"],
            "question": q["question"],
            "citation_passed": outputs["citation_passed"],
            "review_score": outputs["review_score"],
            "errors": outputs.get("errors", []),
            **scores,
        })

    n = len(entries)
    pass_rate = sum(1 for e in entries if e["citation_passed"]) / n if n else 0.0

    aggregates: dict[str, float] = {
        "citation_pass_rate": pass_rate,
        "avg_review_score": _mean(e["review_score"] for e in entries),
    }
    for key in _ALL_PER_QUESTION_KEYS:
        if key not in _FIXED_PER_QUESTION_KEYS:
            aggregates[f"avg_{key}"] = _mean(e[key] for e in entries)

    return {
        "version": version,
        "questions": entries,
        "aggregates": aggregates,
    }


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


def compute_diff(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Compare two :func:`evaluate_all` summaries and return a structured diff.

    Returns
    -------
    dict
        ``baseline_version``, ``candidate_version``, ``per_question`` (list
        of per-metric before/after/delta dicts), ``aggregates``
        (same shape), ``missing_in_candidate``, ``missing_in_baseline``.
    """
    base_map = {q["id"]: q for q in baseline["questions"]}
    cand_map = {q["id"]: q for q in candidate["questions"]}

    base_ids = set(base_map)
    cand_ids = set(cand_map)

    per_question: list[dict[str, Any]] = []
    for qid in sorted(base_ids | cand_ids):
        b = base_map.get(qid, {})
        c = cand_map.get(qid, {})
        base_name = b.get("question", c.get("question", qid))

        entry: dict[str, Any] = {"id": qid, "question": base_name}
        for key in _ALL_PER_QUESTION_KEYS:
            bv = b.get(key) if b else None
            cv = c.get(key) if c else None

            # Skip cross_validation_usage when neither side has applicable data
            if key == "cross_validation_usage":
                b_ok = (b or {}).get("_cv_applicable", True)
                c_ok = (c or {}).get("_cv_applicable", True)
                if not b_ok and not c_ok:
                    entry["_cv_na"] = True
                    continue

            if key == "citation_passed":
                b_num = 1.0 if bv else 0.0
                c_num = 1.0 if cv else 0.0
            else:
                b_num = float(bv) if bv is not None else 0.0
                c_num = float(cv) if cv is not None else 0.0
            entry[key] = {"before": b_num, "after": c_num, "delta": _delta(b_num, c_num)}
        entry["missing"] = not b or not c
        per_question.append(entry)

    def _agg(summary: dict[str, Any], key: str, default: float = 0.0) -> float:
        """Read an aggregate value, computing from per-question data if absent."""
        agg_dict = summary.get("aggregates")
        if agg_dict and key in agg_dict:
            return float(agg_dict[key])
        per_q = summary.get("questions", [])
        if not per_q:
            return default
        if key == "citation_pass_rate":
            return sum(1 for q in per_q if q.get("citation_passed")) / len(per_q)
        if key.startswith("avg_"):
            metric = key[4:]
            return _mean(q.get(metric, 0.0) for q in per_q)
        return default

    aggregates: dict[str, Any] = {}
    for key in _ALL_AGGREGATE_KEYS:
        bv = _agg(baseline, key)
        cv = _agg(candidate, key)
        aggregates[key] = {"before": bv, "after": cv, "delta": _delta(bv, cv)}

    return {
        "baseline_version": baseline.get("version", "unknown"),
        "candidate_version": candidate.get("version", "unknown"),
        "per_question": per_question,
        "aggregates": aggregates,
        "missing_in_candidate": sorted(base_ids - cand_ids),
        "missing_in_baseline": sorted(cand_ids - base_ids),
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _mean(values: Any) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


def _delta(before: float, after: float) -> float:
    return round(after - before, 4)
