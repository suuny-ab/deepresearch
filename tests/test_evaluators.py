"""Tests for deterministic (zero-LLM) evaluators."""

import pytest


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _report(*, body: str, sources: str, with_sources_heading: bool = True) -> str:
    """Build a markdown report string with optional ## Sources section."""
    if with_sources_heading:
        return f"{body}\n\n## Sources\n\n{sources}"
    return body


def _outputs(*, report: str, search_urls: list[str] | None = None, evidence_cards: list[dict] | None = None) -> dict:
    """Build the outputs dict that make_target produces."""
    return {
        "report": report,
        "search_results": [{"url": url, "title": "S", "content": "c"} for url in (search_urls or [])],
        "evidence_cards": evidence_cards or [],
    }


# ---------------------------------------------------------------------------
# citation_compliance
# ---------------------------------------------------------------------------


def test_citation_compliance_pass():
    """A well-formed report with valid citations passes."""
    from deepresearch.evaluators import citation_compliance

    report = _report(
        body="RAG improves relevance.[1]",
        sources="[1] https://example.com/s",
    )
    outputs = _outputs(report=report, search_urls=["https://example.com/s"])

    result = citation_compliance(outputs)
    assert result["key"] == "citation_compliance"
    assert result["score"] == 1.0
    assert result["comment"]


def test_citation_compliance_fail_missing_sources():
    """Report without ## Sources section fails."""
    from deepresearch.evaluators import citation_compliance

    report = _report(
        body="RAG improves relevance.[1]",
        sources="[1] https://example.com/s",
        with_sources_heading=False,
    )
    outputs = _outputs(report=report, search_urls=["https://example.com/s"])

    result = citation_compliance(outputs)
    assert result["score"] == 0.0
    assert "missing_sources_section" in result["comment"]


def test_citation_compliance_fail_bare_url():
    """Report with bare URL in body fails."""
    from deepresearch.evaluators import citation_compliance

    report = _report(
        body="Check https://example.com/s now.[1]",
        sources="[1] https://example.com/s",
    )
    outputs = _outputs(report=report, search_urls=["https://example.com/s"])

    result = citation_compliance(outputs)
    assert result["score"] == 0.0
    assert "bare_urls_in_body" in result["comment"]


# ---------------------------------------------------------------------------
# source_utilization
# ---------------------------------------------------------------------------


def test_source_utilization_full():
    """Every available source URL is cited."""
    from deepresearch.evaluators import source_utilization

    report = _report(
        body="Claim one.[1] Claim two.[2]",
        sources="[1] https://example.com/a\n[2] https://example.com/b",
    )
    outputs = _outputs(report=report, search_urls=["https://example.com/a", "https://example.com/b"])

    result = source_utilization(outputs)
    assert result["key"] == "source_utilization"
    assert result["score"] == 1.0


def test_source_utilization_partial():
    """Only half the sources are cited."""
    from deepresearch.evaluators import source_utilization

    report = _report(
        body="Claim one.[1]",
        sources="[1] https://example.com/a",
    )
    outputs = _outputs(
        report=report,
        search_urls=["https://example.com/a", "https://example.com/b"],
    )

    result = source_utilization(outputs)
    assert result["score"] == 0.5


def test_source_utilization_zero_when_no_search_results():
    """If there are zero search results, utilization is 0 to avoid div-by-zero."""
    from deepresearch.evaluators import source_utilization

    report = _report(body="No sources.", sources="", with_sources_heading=False)
    outputs = _outputs(report=report, search_urls=[])

    result = source_utilization(outputs)
    assert result["score"] == 0.0


# ---------------------------------------------------------------------------
# cross_validation_usage
# ---------------------------------------------------------------------------


def test_cross_validation_usage_all_strong_cited():
    """Every strongly_corroborated card's URL appears as a citation."""
    from deepresearch.evaluators import cross_validation_usage

    report = _report(
        body="Claim one.[1] Claim two.[2]",
        sources="[1] https://example.com/a\n[2] https://example.com/b",
    )
    outputs = _outputs(
        report=report,
        evidence_cards=[
            {"source_url": "https://example.com/a", "corroboration_level": "strongly_corroborated"},
            {"source_url": "https://example.com/b", "corroboration_level": "strongly_corroborated"},
        ],
    )

    result = cross_validation_usage(outputs)
    assert result["key"] == "cross_validation_usage"
    assert result["score"] == 1.0


def test_cross_validation_usage_partial():
    """Only 2 of 3 strong cards are cited."""
    from deepresearch.evaluators import cross_validation_usage

    report = _report(
        body="Claim one.[1]",
        sources="[1] https://example.com/a",
    )
    outputs = _outputs(
        report=report,
        evidence_cards=[
            {"source_url": "https://example.com/a", "corroboration_level": "strongly_corroborated"},
            {"source_url": "https://example.com/b", "corroboration_level": "strongly_corroborated"},
            {"source_url": "https://example.com/c", "corroboration_level": "strongly_corroborated"},
        ],
    )

    result = cross_validation_usage(outputs)
    assert result["score"] == pytest.approx(1.0 / 3.0)


def test_cross_validation_usage_no_strong_cards():
    """No strongly_corroborated cards → applicable=False."""
    from deepresearch.evaluators import cross_validation_usage

    report = _report(body="Claim.[1]", sources="[1] https://example.com/a")
    outputs = _outputs(
        report=report,
        evidence_cards=[
            {"source_url": "https://example.com/a", "corroboration_level": "single_source"},
        ],
    )

    result = cross_validation_usage(outputs)
    assert result["score"] == 0.0
    assert result.get("applicable") is False


def test_cross_validation_usage_ignores_weak_and_single():
    """Only strongly_corroborated cards count; weak/single are ignored."""
    from deepresearch.evaluators import cross_validation_usage

    report = _report(body="Claim.[1]", sources="[1] https://example.com/strong")
    outputs = _outputs(
        report=report,
        evidence_cards=[
            {"source_url": "https://example.com/strong", "corroboration_level": "strongly_corroborated"},
            {"source_url": "https://example.com/weak", "corroboration_level": "weakly_corroborated"},
            {"source_url": "https://example.com/single", "corroboration_level": "single_source"},
        ],
    )

    result = cross_validation_usage(outputs)
    # 1 strong card, it is cited → 1.0
    assert result["score"] == 1.0


# ---------------------------------------------------------------------------
# Schema conformance
# ---------------------------------------------------------------------------


def test_all_evaluators_return_expected_schema():
    """Every evaluator must return {key, score, comment}."""
    from deepresearch.evaluators import (
        citation_compliance,
        citation_density,
        claims_per_source,
        corroboration_strong_ratio,
        corroboration_weak_ratio,
        cross_validation_usage,
        domain_diversity,
        evidence_card_count,
        extracted_claim_count,
        extraction_retention,
        report_length,
        search_query_count,
        search_result_count,
        source_utilization,
        subquestion_count,
    )

    report = _report(
        body="Claim.[1]",
        sources="[1] https://example.com/a",
    )
    outputs = _outputs(
        report=report,
        search_urls=["https://example.com/a"],
        evidence_cards=[
            {"source_url": "https://example.com/a", "corroboration_level": "strongly_corroborated"},
        ],
    )

    for name, fn in [
        ("citation_compliance", citation_compliance),
        ("source_utilization", source_utilization),
        ("cross_validation_usage", cross_validation_usage),
        ("search_result_count", search_result_count),
        ("domain_diversity", domain_diversity),
        ("evidence_card_count", evidence_card_count),
        ("corroboration_strong_ratio", corroboration_strong_ratio),
        ("corroboration_weak_ratio", corroboration_weak_ratio),
        ("report_length", report_length),
        ("citation_density", citation_density),
        ("subquestion_count", subquestion_count),
        ("search_query_count", search_query_count),
        ("extracted_claim_count", extracted_claim_count),
        ("claims_per_source", claims_per_source),
        ("extraction_retention", extraction_retention),
    ]:
        result = fn(outputs)
        assert isinstance(result, dict), f"{name} must return dict"
        assert result["key"] == name, f"{name} key mismatch"
        assert "score" in result, f"{name} missing score"
        assert "comment" in result, f"{name} missing comment"
        assert isinstance(result["score"], (int, float)), f"{name} score must be numeric"
        assert isinstance(result["comment"], str), f"{name} comment must be str"


# ---------------------------------------------------------------------------
# search_result_count
# ---------------------------------------------------------------------------


def test_search_result_count():
    from deepresearch.evaluators import search_result_count

    outputs = _outputs(report="# T", search_urls=["https://a.com", "https://b.com", "https://c.com"])
    result = search_result_count(outputs)
    assert result["score"] == 3


def test_search_result_count_zero():
    from deepresearch.evaluators import search_result_count

    outputs = _outputs(report="# T", search_urls=[])
    result = search_result_count(outputs)
    assert result["score"] == 0


# ---------------------------------------------------------------------------
# domain_diversity
# ---------------------------------------------------------------------------


def test_domain_diversity_counts_unique():
    from deepresearch.evaluators import domain_diversity

    outputs = _outputs(
        report="# T",
        search_urls=["https://a.com/1", "https://a.com/2", "https://b.com/x"],
    )
    result = domain_diversity(outputs)
    assert result["score"] == 2  # a.com + b.com


# ---------------------------------------------------------------------------
# evidence_card_count
# ---------------------------------------------------------------------------


def test_evidence_card_count():
    from deepresearch.evaluators import evidence_card_count

    outputs = _outputs(
        report="# T",
        evidence_cards=[
            {"corroboration_level": "strongly_corroborated"},
            {"corroboration_level": "single_source"},
        ],
    )
    result = evidence_card_count(outputs)
    assert result["score"] == 2


# ---------------------------------------------------------------------------
# corroboration ratios
# ---------------------------------------------------------------------------


def test_corroboration_strong_ratio():
    from deepresearch.evaluators import corroboration_strong_ratio

    outputs = _outputs(
        report="# T",
        evidence_cards=[
            {"corroboration_level": "strongly_corroborated"},
            {"corroboration_level": "strongly_corroborated"},
            {"corroboration_level": "weakly_corroborated"},
            {"corroboration_level": "single_source"},
        ],
    )
    result = corroboration_strong_ratio(outputs)
    assert result["score"] == 0.5  # 2/4


def test_corroboration_weak_ratio():
    from deepresearch.evaluators import corroboration_weak_ratio

    outputs = _outputs(
        report="# T",
        evidence_cards=[
            {"corroboration_level": "strongly_corroborated"},
            {"corroboration_level": "weakly_corroborated"},
            {"corroboration_level": "weakly_corroborated"},
            {"corroboration_level": "single_source"},
        ],
    )
    result = corroboration_weak_ratio(outputs)
    assert result["score"] == 0.5  # 2/4


def test_corroboration_ratio_zero_when_no_cards():
    from deepresearch.evaluators import corroboration_strong_ratio, corroboration_weak_ratio

    outputs = _outputs(report="# T", evidence_cards=[])
    assert corroboration_strong_ratio(outputs)["score"] == 0.0
    assert corroboration_weak_ratio(outputs)["score"] == 0.0


# ---------------------------------------------------------------------------
# report_length
# ---------------------------------------------------------------------------


def test_report_length_counts_body_only():
    """report_length excludes ## Sources section."""
    from deepresearch.evaluators import report_length

    report = _report(
        body="Claim one.[1] Claim two.",
        sources="[1] https://example.com/a",
    )
    outputs = _outputs(report=report, search_urls=["https://example.com/a"])

    result = report_length(outputs)
    # body = "Claim one.[1] Claim two." = 25 chars
    # Sources section should be excluded
    assert 24 <= result["score"] <= 28  # body ~25 chars, Sources excluded


# ---------------------------------------------------------------------------
# citation_density
# ---------------------------------------------------------------------------


def test_citation_density():
    """citation_density = citations per 1000 chars of body."""
    from deepresearch.evaluators import citation_density

    # body with exactly 500 chars and 3 citations → 3 / 0.5 = 6.0/千字
    body = "A" * 500 + "[1] [2] [3]"
    report = _report(body=body, sources="[1] https://a.com\n[2] https://b.com\n[3] https://c.com")
    outputs = _outputs(report=report, search_urls=["https://a.com", "https://b.com", "https://c.com"])

    result = citation_density(outputs)
    assert 5.5 < result["score"] < 6.5  # ≈ 6 citations per 1000 chars


def test_citation_density_zero_when_no_citations():
    from deepresearch.evaluators import citation_density

    body = "A" * 1000  # No citations
    report = _report(body=body, sources="", with_sources_heading=False)
    outputs = _outputs(report=report)

    result = citation_density(outputs)
    assert result["score"] == 0.0


# ---------------------------------------------------------------------------
# subquestion_count
# ---------------------------------------------------------------------------


def test_subquestion_count():
    from deepresearch.evaluators import subquestion_count

    outputs = {"subquestions": [{"id": "q1"}, {"id": "q2"}, {"id": "q3"}]}
    result = subquestion_count(outputs)
    assert result["score"] == 3


# ---------------------------------------------------------------------------
# search_query_count
# ---------------------------------------------------------------------------


def test_search_query_count():
    from deepresearch.evaluators import search_query_count

    outputs = {
        "subquestions": [
            {"search_queries": ["中文 query", "English query", "report query"]},
            {"search_queries": ["固态电池 进展", "solid state battery"]},
        ]
    }
    result = search_query_count(outputs)
    assert result["score"] == 5


# ---------------------------------------------------------------------------
# extracted_claim_count
# ---------------------------------------------------------------------------


def test_extracted_claim_count():
    from deepresearch.evaluators import extracted_claim_count

    outputs = {"extracted_claims": [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]}
    result = extracted_claim_count(outputs)
    assert result["score"] == 3


# ---------------------------------------------------------------------------
# claims_per_source
# ---------------------------------------------------------------------------


def test_claims_per_source():
    from deepresearch.evaluators import claims_per_source

    outputs = {
        "extracted_claims": [
            {"source_url": "https://a.com/page"},
            {"source_url": "https://a.com/page"},
            {"source_url": "https://b.com/other"},
        ]
    }
    result = claims_per_source(outputs)
    assert result["score"] == 1.5  # 3 claims from 2 unique URLs


# ---------------------------------------------------------------------------
# extraction_retention
# ---------------------------------------------------------------------------


def test_extraction_retention():
    from deepresearch.evaluators import extraction_retention

    outputs = {
        "extracted_claims": [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}, {"id": "e4"}],
        "evidence_cards": [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}],
    }
    result = extraction_retention(outputs)
    assert result["score"] == 0.75  # 3/4


def test_extraction_retention_no_claims():
    from deepresearch.evaluators import extraction_retention

    result = extraction_retention({"extracted_claims": [], "evidence_cards": []})
    assert result["score"] == 1.0  # nothing to lose
