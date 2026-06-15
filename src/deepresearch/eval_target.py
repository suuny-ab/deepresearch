"""Function that wraps a research agent for use with langsmith.evaluate()."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def make_target(
    agent: Callable[[str], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Wrap a ``build_agent()`` result as a LangSmith evaluate target.

    Parameters
    ----------
    agent:
        A callable ``(question: str) -> ResearchState`` as returned by
        :func:`deepresearch.runner.build_agent`.

    Returns
    -------
    Callable
        A function with the ``(inputs: dict) -> dict`` signature that
        :func:`langsmith.evaluate` expects.  ``inputs`` must contain a
        ``"question"`` key.
    """

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        question: str = inputs["question"]
        state = agent(question)

        review = state.get("review")
        evidence_cards = state.get("evidence_cards", [])
        search_results = state.get("search_results", [])
        subquestions = state.get("subquestions", [])
        extracted_claims = state.get("extracted_claims", [])

        return {
            "question": question,
            "report": state.get("report_markdown", ""),
            "evidence_cards": [card.model_dump() for card in evidence_cards],
            "search_results": [result.model_dump() for result in search_results],
            "subquestions": [sq.model_dump() for sq in subquestions],
            "extracted_claims": [claim.model_dump() for claim in extracted_claims],
            "citation_passed": state.get("report_status") == "success",
            "review_score": review.score if review else 0,
            "review_issues": review.issues if review else [],
            "review_suggestions": review.suggestions if review else [],
            "errors": state.get("errors", []),
            "output_path": state.get("output_path", ""),
        }

    return target
