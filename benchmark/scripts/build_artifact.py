"""Build a RunArtifact from a raw state dict JSON dump.

Usage: uv run python benchmark/scripts/build_artifact.py <state.json> <version> <question> <output.json>

Reads a full state dict (JSON) produced by an old version's replay run,
computes StandardMetrics using the current metrics.py, and wraps everything
in a standard RunArtifact.
"""

import json
import sys
from datetime import datetime, timezone

from deepresearch import __version__
from deepresearch.metrics import compute_standard_metrics
from deepresearch.state import (
    EvidenceCard,
    ExtractedClaim,
    ReviewResult,
    RunArtifact,
    RunMeta,
    SearchResult,
)


def _reconstruct_models(state: dict) -> dict:
    """Reconstruct Pydantic model instances from plain dicts in JSON-loaded state."""
    if state.get("evidence_cards"):
        state["evidence_cards"] = [EvidenceCard(**c) for c in state["evidence_cards"]]
    if state.get("search_results"):
        state["search_results"] = [SearchResult(**s) for s in state["search_results"]]
    if state.get("extracted_claims"):
        state["extracted_claims"] = [ExtractedClaim(**c) for c in state["extracted_claims"]]
    if state.get("subquestions"):
        from deepresearch.state import SubQuestion

        state["subquestions"] = [SubQuestion(**sq) for sq in state["subquestions"]]
    review = state.get("review")
    if isinstance(review, dict):
        state["review"] = ReviewResult(**review)
    return state


def main(state_path, version, question, output_path):
    with open(state_path, encoding="utf-8") as f:
        raw_state = json.load(f)

    state = _reconstruct_models(raw_state)

    meta = RunMeta(
        app_version=version,
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(),
        mode="replay",
        config={},
    )

    inputs = {
        "question": question,
        "subquestions": [sq.model_dump() for sq in state.get("subquestions", [])],
    }

    pipeline = {
        "search_results": [sr.model_dump() for sr in state.get("search_results", [])],
        "extracted_claims": [c.model_dump() for c in state.get("extracted_claims", [])],
        "evidence_cards": [c.model_dump() for c in state.get("evidence_cards", [])],
        "evidence_metrics": state.get("evidence_metrics", {}),
    }

    standard_metrics = compute_standard_metrics(state)

    review = state.get("review")
    output_section = {
        "report_markdown": state.get("report_markdown", ""),
        "report_status": state.get("report_status"),
        "review": review.model_dump() if review is not None else None,
        "validation_failures": state.get("validation_failures", []),
        "errors": state.get("errors", []),
        "output_path": state.get("output_path"),
    }

    artifact = RunArtifact(
        meta=meta,
        inputs=inputs,
        pipeline=pipeline,
        standard_metrics=standard_metrics,
        output=output_section,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(artifact.model_dump(), f, indent=2, default=str)

    print(f"RunArtifact saved to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(f"Usage: {sys.argv[0]} <state.json> <version> <question> <output.json>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
