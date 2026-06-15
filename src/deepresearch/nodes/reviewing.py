from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.reviewing import build_reviewing_prompt
from deepresearch.state import ResearchState, ReviewResult, TokenUsage
from deepresearch.utils.json import JSONParseError, parse_json_object
from deepresearch.utils.report_writer import _format_bullets

REVIEW_REWRITE_THRESHOLD = 70


def _format_review_feedback(review: ReviewResult) -> str:
    """Format review issues and suggestions into actionable feedback for rewrite."""
    parts = []
    if review.issues:
        parts.append("Issues identified in previous review:")
        parts.append(_format_bullets(review.issues))
    if review.suggestions:
        parts.append("Suggestions for improvement:")
        parts.append(_format_bullets(review.suggestions))
    return "\n".join(parts)


def make_review_report_node(llm: LLMClient):
    def review_report(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        usage_entries: list[TokenUsage] = list(state.get("token_usage", []))
        prompt = build_reviewing_prompt(state["question"], state.get("report_markdown", ""), state.get("evidence_cards", []))
        try:
            text, usage = llm.complete(prompt)
            usage_entries.append(TokenUsage(node="review_report", prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens, estimated_cost=usage.estimated_cost))
        except Exception as exc:
            errors.append(f"LLM call failed in review_report: {exc}")
            return {**state, "review": ReviewResult(passed=False, score=0, issues=["LLM call failed"], suggestions=[]), "errors": errors, "token_usage": usage_entries}
        try:
            review = parse_json_object(text, ReviewResult)
        except JSONParseError as exc:
            errors.append(f"Review JSON parse failed: {exc}")
            review = ReviewResult(passed=False, score=0, issues=["Review parsing failed"], suggestions=["Inspect the report manually"])

        # Distinguish real reviews from error fallbacks.
        # LLM failures return early (line 29), so only JSON parse errors reach here.
        is_error_review = review.issues and review.issues[0] == "Review parsing failed"

        review_feedback = None
        if review.score < REVIEW_REWRITE_THRESHOLD and not state.get("review_rewritten", False) and not is_error_review:
            review_feedback = _format_review_feedback(review)

        return {**state, "review": review, "review_feedback": review_feedback, "errors": errors, "token_usage": usage_entries}

    return review_report
