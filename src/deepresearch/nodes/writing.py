from dataclasses import dataclass

from deepresearch.citations import CitationFailureReason, CitationValidationResult, validate_citations
from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.writing import build_writing_prompt
from deepresearch.state import ResearchState


@dataclass(frozen=True)
class ReportValidationFailure:
    reason: CitationFailureReason
    message: str
    invalid_urls: list[str]
    allowed_urls: list[str]


def _format_urls(urls: list[str]) -> str:
    return "\n".join(f"- {url}" for url in urls) if urls else "- None"


def _validation_failure_report(question: str, failure: ReportValidationFailure) -> str:
    return (
        "# 研究报告生成失败\n\n"
        f"本次报告没有发布，因为生成内容未通过来源校验。\n\n"
        "## 失败原因\n\n"
        f"{failure.message}\n\n"
        "## 非法来源 URL\n\n"
        f"{_format_urls(failure.invalid_urls)}\n\n"
        "## 可用来源 URL\n\n"
        "以下 URL 来自本次 Tavily 搜索结果，报告只能引用这些来源：\n\n"
        f"{_format_urls(failure.allowed_urls)}\n\n"
        "## 你可以怎么做\n\n"
        "- 重新运行一次同样的问题。\n"
        "- 使用更具体的研究问题。\n"
        "- 增加 `--results-per-query` 以提供更多可用来源。\n"
        "- 使用 `--verbose` 查看子问题、搜索 query 和搜索结果数量。\n"
    )


def _make_failure(
    question: str,
    reason: CitationFailureReason,
    message: str,
    invalid_urls: list[str],
    allowed_urls: set[str],
) -> str:
    failure = ReportValidationFailure(
        reason=reason,
        message=message,
        invalid_urls=invalid_urls,
        allowed_urls=sorted(allowed_urls),
    )
    return _validation_failure_report(question, failure)


def _invalid_urls_for_reason(reason: CitationFailureReason, validation_invalid_urls: list[str], bare_body_urls: list[str]) -> list[str]:
    if reason == "invalid_source_urls":
        return validation_invalid_urls
    if reason == "bare_urls_in_body":
        return bare_body_urls
    return []


def _failure_to_dict(result: CitationValidationResult) -> dict[str, object]:
    return result.to_dict()


def make_write_report_node(llm: LLMClient):
    def write_report(state: ResearchState) -> ResearchState:
        results = state.get("search_results", [])
        notes = state.get("notes", [])
        if not results or not notes:
            report = (
                f"# Research could not be completed\n\n"
                f"The question was: {state['question']}\n\n"
                "Insufficient search results or notes were available, so no source-backed report was generated.\n"
            )
            return {
                **state,
                "report_markdown": report,
                "report_status": "failed_validation",
                "rewrite_attempted": False,
                "validation_attempts": 0,
                "validation_failures": [],
            }

        prompt = build_writing_prompt(state["question"], state.get("subquestions", []), notes, results)
        report = llm.complete(prompt)
        allowed_urls = {result.url for result in results}
        validation = validate_citations(report, allowed_urls)
        errors = list(state.get("errors", []))
        if not validation.passed:
            invalid_urls = _invalid_urls_for_reason(
                validation.reason,
                validation.invalid_source_urls,
                validation.bare_body_urls,
            )
            invalid_url_detail = f" Invalid URL(s): {', '.join(invalid_urls)}" if invalid_urls else ""
            errors.append(f"Report citation validation failed ({validation.reason}): {validation.message}{invalid_url_detail}")
            report = _make_failure(
                state["question"],
                validation.reason,
                validation.message,
                invalid_urls,
                allowed_urls,
            )
            return {
                **state,
                "report_markdown": report,
                "errors": errors,
                "report_status": "failed_validation",
                "rewrite_attempted": False,
                "validation_attempts": 1,
                "validation_failures": [_failure_to_dict(validation)],
            }
        return {
            **state,
            "report_markdown": report,
            "report_status": "success",
            "rewrite_attempted": False,
            "validation_attempts": 1,
            "validation_failures": [],
        }

    return write_report
