import re
from dataclasses import dataclass
from typing import Literal

from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.writing import build_writing_prompt
from deepresearch.state import ResearchState


_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
_SOURCES_HEADING_RE = re.compile(r"^##\s+Sources\s*$", re.IGNORECASE | re.MULTILINE)


def _extract_urls(text: str) -> set[str]:
    return {match.rstrip(".,;:") for match in _URL_RE.findall(text)}


def _has_sources_section(text: str) -> bool:
    return bool(_SOURCES_HEADING_RE.search(text))


def _body_before_sources(text: str) -> str:
    match = _SOURCES_HEADING_RE.search(text)
    if not match:
        return text
    return text[: match.start()]


@dataclass(frozen=True)
class ReportValidationFailure:
    reason: Literal[
        "invalid_urls",
        "no_citations",
        "missing_sources_section",
        "missing_body_citations",
    ]
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
    reason: Literal[
        "invalid_urls",
        "no_citations",
        "missing_sources_section",
        "missing_body_citations",
    ],
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
            return {**state, "report_markdown": report, "report_status": "failed_validation"}

        prompt = build_writing_prompt(state["question"], state.get("subquestions", []), notes, results)
        report = llm.complete(prompt)
        allowed_urls = {result.url for result in results}
        report_urls = _extract_urls(report)
        invalid_urls = sorted(url for url in report_urls if url not in allowed_urls)
        errors = list(state.get("errors", []))
        if invalid_urls:
            errors.append(f"Report contains invalid source URL(s) outside search_results: {', '.join(invalid_urls)}")
            report = _make_failure(
                state["question"],
                "invalid_urls",
                "模型生成的报告包含未被搜索结果支持的来源 URL，因此系统拒绝保存该报告正文。",
                invalid_urls,
                allowed_urls,
            )
            return {**state, "report_markdown": report, "errors": errors, "report_status": "failed_validation"}
        if allowed_urls and not report_urls.intersection(allowed_urls):
            errors.append("Report citation validation failed: generated report contains no URLs from search_results.")
            report = _make_failure(
                state["question"],
                "no_citations",
                "模型生成的报告没有在正文中引用任何可用来源。",
                [],
                allowed_urls,
            )
            return {**state, "report_markdown": report, "errors": errors, "report_status": "failed_validation"}
        if not _has_sources_section(report):
            errors.append("Report Sources section validation failed: generated report is missing a ## Sources section.")
            report = _make_failure(
                state["question"],
                "missing_sources_section",
                "模型生成的报告缺少 ## Sources 来源部分。",
                [],
                allowed_urls,
            )
            return {**state, "report_markdown": report, "errors": errors, "report_status": "failed_validation"}
        body_urls = _extract_urls(_body_before_sources(report))
        if allowed_urls and not body_urls.intersection(allowed_urls):
            errors.append("Report body citation validation failed: no citations before Sources section use URLs from search_results.")
            report = _make_failure(
                state["question"],
                "missing_body_citations",
                "模型生成的报告只在 Sources 部分列出来源，但正文关键论点没有引用来源。",
                [],
                allowed_urls,
            )
            return {**state, "report_markdown": report, "errors": errors, "report_status": "failed_validation"}
        return {**state, "report_markdown": report, "report_status": "success"}

    return write_report
