from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.reviewing import build_reviewing_prompt
from deepresearch.state import ResearchState, ReviewResult
from deepresearch.utils.json import JSONParseError, parse_json_object


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
        return {**state, "review": review, "errors": errors}

    return review_report
