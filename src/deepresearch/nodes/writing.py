from deepresearch.citations import CitationFailureReason, CitationValidationResult, validate_citations
from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.writing import build_writing_prompt
from deepresearch.state import ResearchState


def _format_urls(urls: list[str]) -> str:
    return "\n".join(f"- {url}" for url in urls) if urls else "- None"


def _format_numbers(numbers: set[int]) -> str:
    return ", ".join(str(number) for number in sorted(numbers)) if numbers else "None"


def _failure_section(title: str, failure: CitationValidationResult) -> str:
    invalid_urls = _invalid_urls_for_reason(
        failure.reason,
        failure.invalid_source_urls,
        failure.bare_body_urls,
    )
    return (
        f"## {title}\n\n"
        f"{failure.message}\n\n"
        "### 非法来源 URL\n\n"
        f"{_format_urls(invalid_urls)}\n\n"
    )


def _diagnostic_section(attempt_number: int, failure: CitationValidationResult) -> str:
    source_urls = [f"[{number}] {url}" for number, url in sorted(failure.source_urls.items())]
    return (
        f"### 第 {attempt_number} 次诊断\n\n"
        f"- reason: {failure.reason}\n"
        f"- body citations: {_format_numbers(failure.body_citations)}\n"
        f"- source citations: {_format_numbers(failure.source_citations)}\n"
        f"- undefined citations: {_format_numbers(failure.undefined_citations)}\n"
        f"- unused sources: {_format_numbers(failure.unused_sources)}\n"
        f"- invalid source URLs: {', '.join(failure.invalid_source_urls) if failure.invalid_source_urls else 'None'}\n"
        f"- bare body URLs: {', '.join(failure.bare_body_urls) if failure.bare_body_urls else 'None'}\n"
        f"- available source URLs: {', '.join(failure.allowed_urls) if failure.allowed_urls else 'None'}\n"
        f"- parsed source URLs: {', '.join(source_urls) if source_urls else 'None'}\n\n"
    )


def _validation_failure_report(question: str, failures: CitationValidationResult | list[CitationValidationResult]) -> str:
    failure_list = failures if isinstance(failures, list) else [failures]
    if len(failure_list) == 1:
        failure_sections = _failure_section("失败原因", failure_list[0])
    else:
        failure_sections = "".join(
            _failure_section(title, failure)
            for title, failure in zip(["第一次失败原因", "第二次失败原因"], failure_list)
        )

    diagnostics = "".join(
        _diagnostic_section(attempt_number, failure)
        for attempt_number, failure in enumerate(failure_list, start=1)
    )
    allowed_urls = failure_list[-1].allowed_urls if failure_list else []
    return (
        "# 研究报告生成失败\n\n"
        f"本次报告没有发布，因为生成内容未通过来源校验。\n\n"
        f"{failure_sections}"
        "## 详细诊断\n\n"
        f"{diagnostics}"
        "## 可用来源 URL\n\n"
        "以下 URL 来自本次 Tavily 搜索结果，报告只能引用这些来源：\n\n"
        f"{_format_urls(allowed_urls)}\n\n"
        "## 你可以怎么做\n\n"
        "- 重新运行一次同样的问题。\n"
        "- 使用更具体的研究问题。\n"
        "- 增加 `--results-per-query` 以提供更多可用来源。\n"
        "- 使用 `--verbose` 查看子问题、搜索 query 和搜索结果数量。\n"
    )


def _invalid_urls_for_reason(reason: CitationFailureReason, validation_invalid_urls: list[str], bare_body_urls: list[str]) -> list[str]:
    if reason == "invalid_source_urls":
        return validation_invalid_urls
    if reason == "bare_urls_in_body":
        return bare_body_urls
    return []



def _allowed_source_urls(state: ResearchState) -> set[str]:
    evidence_cards = state.get("evidence_cards", [])
    if evidence_cards:
        return {card.source_url for card in evidence_cards}
    return {result.url for result in state.get("search_results", [])}


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
        if not results:
            report = (
                f"# Research could not be completed\n\n"
                f"The question was: {state['question']}\n\n"
                "Insufficient search results were available, so no source-backed report was generated.\n"
            )
            return {
                **state,
                "report_markdown": report,
                "report_status": "failed_validation",
                "rewrite_attempted": False,
                "validation_attempts": 0,
                "validation_failures": [],
            }

        allowed_urls = _allowed_source_urls(state)
        review_feedback = state.get("review_feedback")
        is_review_rewrite = review_feedback is not None
        prompt = build_writing_prompt(
            state["question"],
            state.get("subquestions", []),
            results,
            evidence_cards=state.get("evidence_cards", []),
            allowed_source_urls=allowed_urls,
            review_feedback=review_feedback,
        )
        errors = list(state.get("errors", []))
        try:
            report = llm.complete(prompt)
        except Exception as exc:
            errors.append(f"LLM call failed in write_report: {exc}")
            return {
                **state,
                "report_markdown": "Report generation failed due to an LLM error.",
                "report_status": "failed_validation",
                "rewrite_attempted": False,
                "validation_attempts": 0,
                "validation_failures": [],
                "errors": errors,
            }
        first_validation = validate_citations(report, allowed_urls)
        if first_validation.passed:
            return {
                **state,
                "report_markdown": report,
                "report_status": "success",
                "rewrite_attempted": False,
                "validation_attempts": 1,
                "validation_failures": [],
                **({} if not is_review_rewrite else {"review_feedback": None, "review_rewritten": True}),
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
        try:
            rewritten_report = llm.complete(rewrite_prompt)
        except Exception as exc:
            errors.append(f"LLM call failed in write_report rewrite: {exc}")
            failure_report = _validation_failure_report(state["question"], [first_validation])
            return {
                **state,
                "report_markdown": failure_report,
                "errors": errors,
                "report_status": "failed_validation",
                "rewrite_attempted": True,
                "validation_attempts": 1,
                "validation_failures": [first_validation.to_dict()],
                **({} if not is_review_rewrite else {"review_feedback": None, "review_rewritten": True}),
            }
        second_validation = validate_citations(rewritten_report, allowed_urls)

        if second_validation.passed:
            return {
                **state,
                "report_markdown": rewritten_report,
                "errors": errors,
                "report_status": "success",
                "rewrite_attempted": True,
                "validation_attempts": 2,
                "validation_failures": [first_validation.to_dict()],
                **({} if not is_review_rewrite else {"review_feedback": None, "review_rewritten": True}),
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
        failure_report = _validation_failure_report(state["question"], [first_validation, second_validation])
        return {
            **state,
            "report_markdown": failure_report,
            "errors": errors,
            "report_status": "failed_validation",
            "rewrite_attempted": True,
            "validation_attempts": 2,
            "validation_failures": [first_validation.to_dict(), second_validation.to_dict()],
            **({} if not is_review_rewrite else {"review_feedback": None, "review_rewritten": True}),
        }

    return write_report
