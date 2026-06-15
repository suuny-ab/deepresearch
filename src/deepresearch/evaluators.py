"""Deterministic (zero-LLM) evaluators for LangSmith experiments.

Each evaluator has the signature ``(outputs: dict) -> dict`` expected by
LangSmith :func:`~langsmith.evaluation.evaluate`.  The return dict must
contain the keys ``key``, ``score``, and ``comment``.

*outputs* is the dict returned by :func:`deepresearch.eval_target.make_target`.
"""

from __future__ import annotations

from typing import Any

from deepresearch.citations import (
    CitationValidationResult,
    extract_source_urls,
    split_sources,
    validate_citations,
)


# ---------------------------------------------------------------------------
# citation_compliance
# ---------------------------------------------------------------------------


def citation_compliance(outputs: dict[str, Any]) -> dict[str, Any]:
    """Check whether the report passes strict ``[N]`` citation validation.

    Returns 1.0 if the report body and ``## Sources`` section are
    internally consistent and only use allowed URLs from search results;
    0.0 otherwise.  The ``comment`` includes the failure reason.
    """
    report: str = outputs.get("report", "")
    search_results: list[dict[str, Any]] = outputs.get("search_results", [])
    allowed_urls = {result["url"] for result in search_results if result.get("url")}

    result: CitationValidationResult = validate_citations(report, allowed_urls)

    if result.passed:
        return {
            "key": "citation_compliance",
            "score": 1.0,
            "comment": "All citation validation checks passed.",
        }

    return {
        "key": "citation_compliance",
        "score": 0.0,
        "comment": f"{result.reason}: {result.message}",
    }


# ---------------------------------------------------------------------------
# source_utilization
# ---------------------------------------------------------------------------


def source_utilization(outputs: dict[str, Any]) -> dict[str, Any]:
    """Measure what fraction of available search-result URLs are cited.

    Score = ``|cited URLs| / |available URLs|``.  Returns 0.0 when
    *search_results* is empty (avoids division by zero).
    """
    report: str = outputs.get("report", "")
    search_results: list[dict[str, Any]] = outputs.get("search_results", [])

    available = {result["url"] for result in search_results if result.get("url")}
    if not available:
        return {
            "key": "source_utilization",
            "score": 0.0,
            "comment": "No search result URLs available for comparison.",
        }

    _body, sources_text = split_sources(report)
    if sources_text is None:
        return {
            "key": "source_utilization",
            "score": 0.0,
            "comment": "Report has no ## Sources section.",
        }

    source_urls = extract_source_urls(sources_text)
    cited = {url for url in source_urls.values() if url in available}

    count_cited = len(cited)
    count_available = len(available)

    return {
        "key": "source_utilization",
        "score": count_cited / count_available,
        "comment": f"{count_cited}/{count_available} source URLs cited.",
    }


# ---------------------------------------------------------------------------
# cross_validation_usage
# ---------------------------------------------------------------------------


def cross_validation_usage(outputs: dict[str, Any]) -> dict[str, Any]:
    """Measure what fraction of *strongly_corroborated* evidence cards are cited.

    Only cards with ``corroboration_level == "strongly_corroborated"`` are
    counted — these represent the most trustworthy claims.  If there are
    no strongly-corroborated cards the score is 1.0 (nothing was missed).
    """
    report: str = outputs.get("report", "")
    evidence_cards: list[dict[str, Any]] = outputs.get("evidence_cards", [])

    strong_cards = [
        card for card in evidence_cards
        if card.get("corroboration_level") == "strongly_corroborated"
    ]
    if not strong_cards:
        return {
            "key": "cross_validation_usage",
            "score": 0.0,
            "comment": "无强印证卡片，指标不适用。",
            "applicable": False,
        }

    _body, sources_text = split_sources(report)
    if sources_text is None:
        cited_urls: set[str] = set()
    else:
        source_urls = extract_source_urls(sources_text)
        cited_urls = set(source_urls.values())

    strong_cited = [
        card for card in strong_cards
        if card.get("source_url") in cited_urls
    ]

    count_cited = len(strong_cited)
    count_total = len(strong_cards)

    return {
        "key": "cross_validation_usage",
        "score": count_cited / count_total,
        "comment": f"{count_cited}/{count_total} strongly-corroborated cards cited.",
    }


# ---------------------------------------------------------------------------
# Pipeline-stage metrics — throughput & diversity
# ---------------------------------------------------------------------------


def search_result_count(outputs: dict[str, Any]) -> dict[str, Any]:
    """Absolute number of search results retrieved for this question."""
    n = len(outputs.get("search_results", []))
    return {"key": "search_result_count", "score": n, "comment": f"{n} search results"}


def domain_diversity(outputs: dict[str, Any]) -> dict[str, Any]:
    """Number of unique domains among search results."""
    from deepresearch.utils.urls import extract_domain

    domains = {
        extract_domain(r["url"])
        for r in outputs.get("search_results", [])
        if r.get("url")
    }
    n = len(domains)
    return {"key": "domain_diversity", "score": n, "comment": f"{n} unique domains"}


def evidence_card_count(outputs: dict[str, Any]) -> dict[str, Any]:
    """Absolute number of evidence cards produced by the pipeline."""
    n = len(outputs.get("evidence_cards", []))
    return {"key": "evidence_card_count", "score": n, "comment": f"{n} evidence cards"}


def corroboration_strong_ratio(outputs: dict[str, Any]) -> dict[str, Any]:
    """Fraction of evidence cards that are strongly corroborated (2+ independent sources)."""
    cards = outputs.get("evidence_cards", [])
    if not cards:
        return {"key": "corroboration_strong_ratio", "score": 0.0, "comment": "No evidence cards"}
    strong = sum(1 for c in cards if c.get("corroboration_level") == "strongly_corroborated")
    ratio = strong / len(cards)
    return {"key": "corroboration_strong_ratio", "score": ratio, "comment": f"{strong}/{len(cards)} strongly corroborated"}


def corroboration_weak_ratio(outputs: dict[str, Any]) -> dict[str, Any]:
    """Fraction of evidence cards that are weakly corroborated (1 other source)."""
    cards = outputs.get("evidence_cards", [])
    if not cards:
        return {"key": "corroboration_weak_ratio", "score": 0.0, "comment": "No evidence cards"}
    weak = sum(1 for c in cards if c.get("corroboration_level") == "weakly_corroborated")
    ratio = weak / len(cards)
    return {"key": "corroboration_weak_ratio", "score": ratio, "comment": f"{weak}/{len(cards)} weakly corroborated"}


# ---------------------------------------------------------------------------
# Output-level structural metrics
# ---------------------------------------------------------------------------


def report_length(outputs: dict[str, Any]) -> dict[str, Any]:
    """Character count of the report body (excluding ``## Sources`` section)."""
    report: str = outputs.get("report", "")
    body, _sources = split_sources(report)
    n = len(body)
    return {"key": "report_length", "score": n, "comment": f"{n} chars in report body"}


def citation_density(outputs: dict[str, Any]) -> dict[str, Any]:
    """Number of ``[N]`` citations per 1 000 characters of body text.

    Returns 0.0 when the body is empty (avoids division by zero).
    """
    from deepresearch.citations import extract_body_citations

    report: str = outputs.get("report", "")
    body, _sources = split_sources(report)
    if not body:
        return {"key": "citation_density", "score": 0.0, "comment": "Report body is empty."}

    citations = extract_body_citations(body)
    density = len(citations) / (len(body) / 1000)
    return {
        "key": "citation_density",
        "score": density,
        "comment": f"{len(citations)} citations, {density:.1f}/千字",
    }


# ---------------------------------------------------------------------------
# Pipeline-stage metrics — planning & extraction
# ---------------------------------------------------------------------------


def subquestion_count(outputs: dict[str, Any]) -> dict[str, Any]:
    """Number of subquestions generated by the planner."""
    n = len(outputs.get("subquestions", []))
    return {"key": "subquestion_count", "score": n, "comment": f"{n} subquestions"}


def search_query_count(outputs: dict[str, Any]) -> dict[str, Any]:
    """Total number of search queries across all subquestions."""
    total = 0
    for sq in outputs.get("subquestions", []):
        queries = sq.get("search_queries", [])
        total += len(queries) if queries else 1
    return {"key": "search_query_count", "score": total, "comment": f"{total} search queries"}


def extracted_claim_count(outputs: dict[str, Any]) -> dict[str, Any]:
    """Number of raw claims extracted during Phase 1."""
    n = len(outputs.get("extracted_claims", []))
    return {"key": "extracted_claim_count", "score": n, "comment": f"{n} extracted claims"}


def claims_per_source(outputs: dict[str, Any]) -> dict[str, Any]:
    """Average number of claims extracted per unique source URL."""
    claims = outputs.get("extracted_claims", [])
    if not claims:
        return {"key": "claims_per_source", "score": 0.0, "comment": "No extracted claims"}
    sources = {c["source_url"] for c in claims if c.get("source_url")}
    if not sources:
        return {"key": "claims_per_source", "score": 0.0, "comment": "No unique source URLs"}
    ratio = len(claims) / len(sources)
    return {"key": "claims_per_source", "score": ratio, "comment": f"{ratio:.1f} claims per source"}


def extraction_retention(outputs: dict[str, Any]) -> dict[str, Any]:
    """Ratio of evidence cards to extracted claims (Phase 2 retention).

    Returns 1.0 when there are no extracted claims (nothing was lost).
    """
    claims = outputs.get("extracted_claims", [])
    cards = outputs.get("evidence_cards", [])
    if not claims:
        return {"key": "extraction_retention", "score": 1.0, "comment": "No extracted claims to track"}
    ratio = len(cards) / len(claims)
    return {"key": "extraction_retention", "score": ratio, "comment": f"{len(cards)} cards / {len(claims)} claims"}


# ---------------------------------------------------------------------------
# Evaluator registry — single source of truth for which metrics exist
# ---------------------------------------------------------------------------

# Registry: (key, callable) — single source of truth for which metrics exist.
# Keys are stable; the _ALL_PER_QUESTION_KEYS and _ALL_AGGREGATE_KEYS lists
# in compare.py are derived from this.
ALL_EVALUATORS: list[tuple[str, callable]] = [
    # Pipeline: planning
    ("subquestion_count", subquestion_count),
    ("search_query_count", search_query_count),
    # Pipeline: search
    ("search_result_count", search_result_count),
    ("domain_diversity", domain_diversity),
    # Pipeline: extraction
    ("extracted_claim_count", extracted_claim_count),
    ("claims_per_source", claims_per_source),
    # Pipeline: validation
    ("evidence_card_count", evidence_card_count),
    ("extraction_retention", extraction_retention),
    ("corroboration_strong_ratio", corroboration_strong_ratio),
    ("corroboration_weak_ratio", corroboration_weak_ratio),
    # Output
    ("citation_compliance", citation_compliance),
    ("cross_validation_usage", cross_validation_usage),
    ("source_utilization", source_utilization),
    ("report_length", report_length),
    ("citation_density", citation_density),
]

# Keys that are always present in per-question entries (not from evaluators)
_FIXED_PER_QUESTION_KEYS = ["citation_passed", "review_score"]
