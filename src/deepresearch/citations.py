import re
from dataclasses import dataclass, field
from typing import Literal

CitationFailureReason = Literal[
    "missing_sources_section",
    "missing_body_citations",
    "undefined_citations",
    "unused_sources",
    "invalid_source_urls",
    "duplicate_source_citations",
    "bare_urls_in_body",
]

_SOURCES_HEADING_RE = re.compile(r"^##\s+Sources\s*$", re.IGNORECASE | re.MULTILINE)
_CITATION_RE = re.compile(r"\[(\d+)\]")
_SOURCE_LINE_RE = re.compile(r"^\s*-?\s*\[(\d+)\]\s*:??\s+(https?://\S+)", re.MULTILINE)
_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


@dataclass(frozen=True)
class CitationValidationResult:
    passed: bool
    reason: CitationFailureReason | None = None
    message: str = ""
    body_citations: set[int] = field(default_factory=set)
    source_citations: set[int] = field(default_factory=set)
    source_urls: dict[int, str] = field(default_factory=dict)
    undefined_citations: set[int] = field(default_factory=set)
    unused_sources: set[int] = field(default_factory=set)
    invalid_source_urls: list[str] = field(default_factory=list)
    duplicated_source_citations: set[int] = field(default_factory=set)
    bare_body_urls: list[str] = field(default_factory=list)
    allowed_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "message": self.message,
            "body_citations": sorted(self.body_citations),
            "source_citations": sorted(self.source_citations),
            "source_urls": dict(sorted(self.source_urls.items())),
            "undefined_citations": sorted(self.undefined_citations),
            "unused_sources": sorted(self.unused_sources),
            "invalid_source_urls": self.invalid_source_urls,
            "duplicated_source_citations": sorted(self.duplicated_source_citations),
            "bare_body_urls": self.bare_body_urls,
            "allowed_urls": self.allowed_urls,
        }


def _clean_url(url: str) -> str:
    cleaned = url.rstrip(".,;:")
    matching_open = {")": "(",
        "]": "[",
        "}": "{",
    }
    while cleaned and cleaned[-1] in matching_open:
        closing = cleaned[-1]
        opening = matching_open[closing]
        if cleaned.count(opening) >= cleaned.count(closing):
            break
        cleaned = cleaned[:-1]
    return cleaned


def split_sources(report: str) -> tuple[str, str | None]:
    match = _SOURCES_HEADING_RE.search(report)
    if not match:
        return report, None
    return report[: match.start()], report[match.end() :]


def extract_body_citations(body: str) -> set[int]:
    return {int(match) for match in _CITATION_RE.findall(body)}


def extract_source_urls(sources: str) -> dict[int, str]:
    parsed: dict[int, str] = {}
    for number, url in _SOURCE_LINE_RE.findall(sources):
        parsed[int(number)] = _clean_url(url)
    return parsed


def extract_duplicate_source_citations(sources: str) -> set[int]:
    seen: set[int] = set()
    duplicated: set[int] = set()
    for number, _url in _SOURCE_LINE_RE.findall(sources):
        citation_number = int(number)
        if citation_number in seen:
            duplicated.add(citation_number)
        seen.add(citation_number)
    return duplicated


def extract_urls(text: str) -> list[str]:
    return [_clean_url(match) for match in _URL_RE.findall(text)]


def validate_citations(report: str, allowed_urls: set[str]) -> CitationValidationResult:
    body, sources = split_sources(report)
    allowed = sorted(allowed_urls)

    if sources is None:
        return CitationValidationResult(
            passed=False,
            reason="missing_sources_section",
            message="报告缺少 ## Sources 来源部分。",
            allowed_urls=allowed,
        )

    bare_body_urls = extract_urls(body)
    if bare_body_urls:
        return CitationValidationResult(
            passed=False,
            reason="bare_urls_in_body",
            message="正文中出现裸 URL，URL 只能出现在 ## Sources 部分。",
            bare_body_urls=bare_body_urls,
            allowed_urls=allowed,
        )

    body_citations = extract_body_citations(body)
    duplicated_source_citations = extract_duplicate_source_citations(sources)
    source_urls = extract_source_urls(sources)
    source_citations = set(source_urls)

    if duplicated_source_citations:
        return CitationValidationResult(
            passed=False,
            reason="duplicate_source_citations",
            message=f"Sources 中存在重复编号：{sorted(duplicated_source_citations)}。",
            body_citations=body_citations,
            source_citations=source_citations,
            source_urls=source_urls,
            duplicated_source_citations=duplicated_source_citations,
            allowed_urls=allowed,
        )

    if not body_citations:
        return CitationValidationResult(
            passed=False,
            reason="missing_body_citations",
            message="正文没有使用编号引用，例如 [1]、[2]。",
            body_citations=body_citations,
            source_citations=source_citations,
            source_urls=source_urls,
            allowed_urls=allowed,
        )

    undefined = body_citations - source_citations
    if undefined:
        return CitationValidationResult(
            passed=False,
            reason="undefined_citations",
            message=f"正文引用了未在 Sources 中定义的编号：{sorted(undefined)}。",
            body_citations=body_citations,
            source_citations=source_citations,
            source_urls=source_urls,
            undefined_citations=undefined,
            allowed_urls=allowed,
        )

    invalid_urls = sorted(url for url in source_urls.values() if url not in allowed_urls)
    if invalid_urls:
        return CitationValidationResult(
            passed=False,
            reason="invalid_source_urls",
            message="Sources 中存在未被搜索结果支持的 URL。",
            body_citations=body_citations,
            source_citations=source_citations,
            source_urls=source_urls,
            invalid_source_urls=invalid_urls,
            allowed_urls=allowed,
        )

    unused = source_citations - body_citations
    if unused:
        return CitationValidationResult(
            passed=False,
            reason="unused_sources",
            message=f"Sources 中存在未被正文引用的编号：{sorted(unused)}。",
            body_citations=body_citations,
            source_citations=source_citations,
            source_urls=source_urls,
            unused_sources=unused,
            allowed_urls=allowed,
        )

    return CitationValidationResult(
        passed=True,
        body_citations=body_citations,
        source_citations=source_citations,
        source_urls=source_urls,
        allowed_urls=allowed,
    )
