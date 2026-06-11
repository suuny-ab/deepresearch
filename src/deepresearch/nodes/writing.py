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


def _failure_section(title: str, failure: ReportValidationFailure) -> str:
    return (
        f"## {title}\n\n"
        f"{failure.message}\n\n"
        "### 非法来源 URL\n\n"
        f"{_format_urls(failure.invalid_urls)}\n\n"
    )


def _validation_failure_report(question: str, failures: ReportValidationFailure | list[ReportValidationFailure]) -> str:
    failure_list = failures if isinstance(failures, list) else [failures]
    if len(failure_list) == 1:
        failure_sections = _failure_section("失败原因", failure_list[0])
    else:
        failure_sections = "".join(
            _failure_section(title, failure)
            for title, failure in zip(["第一次失败原因", "第二次失败原因"], failure_list)
        )

    allowed_urls = failure_list[-1].allowed_urls if failure_list else []
    return (
        "# 研究报告生成失败\n\n"
        f"本次报告没有发布，因为生成内容未通过来源校验。\n\n"
        f"{failure_sections}"
        "## 可用来源 URL\n\n"
        "以下 URL 来自本次 Tavily 搜索结果，报告只能引用这些来源：\n\n"
        f"{_format_urls(allowed_urls)}\n\n"
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


def _build_rewrite_prompt(question: str, draft: str, validation: CitationValidationResult, allowed_urls: set[str]) -> str:
    return f"""
你刚才生成的报告未通过引用校验。

失败类型：{validation.reason}
失败原因：{validation.message}

请重新生成完整 Markdown 报告。
必须遵守：
- 正文关键论点使用 [1]、[2] 编号引用。
- 正文不允许出现裸 URL。
- URL 只能出现在 ## Sources 部分。
- Sources 中每个编号都必须在正文中使用。
- 只能使用 allowed URLs。

Original question:
{question}

Invalid draft:
{draft}

Allowed URLs:
{sorted(allowed_urls)}
""".strip()


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
        first_validation = validate_citations(report, allowed_urls)
        errors = list(state.get("errors", []))
        if first_validation.passed:
            return {
                **state,
                "report_markdown": report,
                "report_status": "success",
                "rewrite_attempted": False,
                "validation_attempts": 1,
                "validation_failures": [],
            }

        first_invalid_urls = _invalid_urls_for_reason(
            first_validation.reason,
            first_validation.invalid_source_urls,
            first_validation.bare_body_urls,
        )
        first_invalid_url_detail = f" Invalid URL(s): {', '.join(first_invalid_urls)}" if first_invalid_urls else ""
        errors.append(
            f"Report citation validation failed on attempt 1: {first_validation.reason}: "
            f"{first_validation.message}{first_invalid_url_detail}"
        )
        rewrite_prompt = _build_rewrite_prompt(state["question"], report, first_validation, allowed_urls)
        rewritten_report = llm.complete(rewrite_prompt)
        second_validation = validate_citations(rewritten_report, allowed_urls)

        if second_validation.passed:
            return {
                **state,
                "report_markdown": rewritten_report,
                "errors": errors,
                "report_status": "success",
                "rewrite_attempted": True,
                "validation_attempts": 2,
                "validation_failures": [_failure_to_dict(first_validation)],
            }

        second_invalid_urls = _invalid_urls_for_reason(
            second_validation.reason,
            second_validation.invalid_source_urls,
            second_validation.bare_body_urls,
        )
        second_invalid_url_detail = f" Invalid URL(s): {', '.join(second_invalid_urls)}" if second_invalid_urls else ""
        errors.append(
            f"Report citation validation failed on attempt 2: {second_validation.reason}: "
            f"{second_validation.message}{second_invalid_url_detail}"
        )
        first_failure = ReportValidationFailure(
            reason=first_validation.reason,
            message=first_validation.message,
            invalid_urls=first_invalid_urls,
            allowed_urls=sorted(allowed_urls),
        )
        second_failure = ReportValidationFailure(
            reason=second_validation.reason,
            message=second_validation.message,
            invalid_urls=second_invalid_urls,
            allowed_urls=sorted(allowed_urls),
        )
        failure_report = _validation_failure_report(state["question"], [first_failure, second_failure])
        return {
            **state,
            "report_markdown": failure_report,
            "errors": errors,
            "report_status": "failed_validation",
            "rewrite_attempted": True,
            "validation_attempts": 2,
            "validation_failures": [_failure_to_dict(first_validation), _failure_to_dict(second_validation)],
        }

    return write_report
