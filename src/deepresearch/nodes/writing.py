import re

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


def _safe_invalid_source_report(question: str, allowed_urls: set[str]) -> str:
    sources = "\n".join(f"- {url}" for url in sorted(allowed_urls)) or "- None"
    return (
        "# Research report not published\n\n"
        f"The question was: {question}\n\n"
        "The report generation failed validation, so no unsupported report was published from that generation.\n"
        "Invalid source URLs were detected in the generated report, so no report was published from that generation.\n\n"
        "Only the following source URLs were available for a valid report:\n\n"
        f"{sources}\n"
    )


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
            return {**state, "report_markdown": report}

        prompt = build_writing_prompt(state["question"], state.get("subquestions", []), notes, results)
        report = llm.complete(prompt)
        allowed_urls = {result.url for result in results}
        report_urls = _extract_urls(report)
        invalid_urls = sorted(url for url in report_urls if url not in allowed_urls)
        errors = list(state.get("errors", []))
        if invalid_urls:
            errors.append(f"Report contains invalid source URL(s) outside search_results: {', '.join(invalid_urls)}")
            report = _safe_invalid_source_report(state["question"], allowed_urls)
            return {**state, "report_markdown": report, "errors": errors}
        if allowed_urls and not report_urls.intersection(allowed_urls):
            errors.append("Report citation validation failed: generated report contains no URLs from search_results.")
            report = _safe_invalid_source_report(state["question"], allowed_urls)
            return {**state, "report_markdown": report, "errors": errors}
        if not _has_sources_section(report):
            errors.append("Report Sources section validation failed: generated report is missing a ## Sources section.")
            report = _safe_invalid_source_report(state["question"], allowed_urls)
            return {**state, "report_markdown": report, "errors": errors}
        body_urls = _extract_urls(_body_before_sources(report))
        if allowed_urls and not body_urls.intersection(allowed_urls):
            errors.append("Report body citation validation failed: no citations before Sources section use URLs from search_results.")
            report = _safe_invalid_source_report(state["question"], allowed_urls)
            return {**state, "report_markdown": report, "errors": errors}
        return {**state, "report_markdown": report}

    return write_report
