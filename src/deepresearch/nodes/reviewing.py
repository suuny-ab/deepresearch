from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.reviewing import build_reviewing_prompt
from deepresearch.state import ResearchState, ReviewResult
from deepresearch.utils.json import JSONParseError, parse_json_object


def _format_review_feedback(review: ReviewResult) -> str:
    """Format review issues and suggestions into actionable feedback for rewrite."""
    parts = []
    if review.issues:
        parts.append("Issues identified in previous review:")
        for issue in review.issues:
            parts.append(f"- {issue}")
    if review.suggestions:
        parts.append("Suggestions for improvement:")
        for suggestion in review.suggestions:
            parts.append(f"- {suggestion}")
    return "\n".join(parts)


def make_review_report_node(llm: LLMClient):
    def review_report(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        prompt = build_reviewing_prompt(state["question"], state.get("report_markdown", ""), state.get("evidence_cards", []))
        try:
            text = llm.complete(prompt)
        except Exception as exc:
            errors.append(f"LLM call failed in review_report: {exc}")
            return {**state, "review": ReviewResult(passed=False, score=0, issues=["LLM call failed"], suggestions=[]), "errors": errors}
        try:
            review = parse_json_object(text, ReviewResult)
        except JSONParseError as exc:
            errors.append(f"Review JSON parse failed: {exc}")
            review = ReviewResult(passed=False, score=0, issues=["Review parsing failed"], suggestions=["Inspect the report manually"])

        is_error_review = review.issues and review.issues[0] in ("LLM call failed", "Review parsing failed")

        review_feedback = None
        if review.score < 70 and not state.get("review_rewritten", False) and not is_error_review:
            review_feedback = _format_review_feedback(review)

        return {**state, "review": review, "review_feedback": review_feedback, "errors": errors}

    return review_report
