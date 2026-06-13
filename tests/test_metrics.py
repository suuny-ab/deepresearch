from deepresearch.metrics import compute_standard_metrics
from deepresearch.state import EvidenceCard, ReviewResult


def test_compute_standard_metrics_empty_state():
    """空 state 返回全零/null 的 metrics。"""
    result = compute_standard_metrics({})

    assert result.evidence_card_count == 0
    assert result.claims_per_source == 0.0
    assert result.source_utilization == 0.0
    assert result.corroboration_strong == 0
    assert result.corroboration_weak == 0
    assert result.corroboration_single == 0
    assert result.domain_diversity == 0
    assert result.review_score is None
    assert result.review_passed is None
    assert result.rewrite_triggered is False
    assert result.citation_coverage is None
    assert result.source_citation_rate is None
    assert result.orphan_url_count is None
    assert result.validation_first_pass is None


def test_compute_standard_metrics_with_evidence_cards():
    """有 evidence_cards 时正确统计数量和分布。"""
    cards = [
        EvidenceCard(
            id="c1", subquestion_id="sq1", claim="Claim A",
            source_url="https://example.com/a",
            source_title="Source A", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="strongly_corroborated",
            corroborating_sources=["https://other.com/1", "https://other.com/2"],
            confidence="high",
        ),
        EvidenceCard(
            id="c2", subquestion_id="sq1", claim="Claim B",
            source_url="https://example.com/b",
            source_title="Source B", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="weakly_corroborated",
            corroborating_sources=["https://other.com/3"],
            confidence="medium",
        ),
        EvidenceCard(
            id="c3", subquestion_id="sq2", claim="Claim C",
            source_url="https://example.com/a",
            source_title="Source A", supporting_snippet="...",
            content_type="extracted_content",
            corroboration_level="single_source",
            corroborating_sources=[],
            confidence="low",
        ),
    ]
    state = {"evidence_cards": cards}

    result = compute_standard_metrics(state)

    assert result.evidence_card_count == 3
    assert result.corroboration_strong == 1
    assert result.corroboration_weak == 1
    assert result.corroboration_single == 1


def test_compute_standard_metrics_claims_per_source():
    """claims_per_source = evidence_cards / search_results。"""
    cards = [
        EvidenceCard(
            id="c1", subquestion_id="sq1", claim="Claim",
            source_url="https://a.com/1",
            source_title="T", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="single_source",
            corroborating_sources=[], confidence="medium",
        ),
        EvidenceCard(
            id="c2", subquestion_id="sq1", claim="Claim",
            source_url="https://b.com/1",
            source_title="T", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="single_source",
            corroborating_sources=[], confidence="medium",
        ),
    ]
    from deepresearch.state import SearchResult
    sources = [
        SearchResult(subquestion_id="sq1", title="A", url="https://a.com/1", content="..."),
        SearchResult(subquestion_id="sq1", title="B", url="https://b.com/1", content="..."),
    ]
    state = {"evidence_cards": cards, "search_results": sources}

    result = compute_standard_metrics(state)

    assert result.evidence_card_count == 2
    assert result.claims_per_source == 1.0  # 2 cards / 2 sources


def test_compute_standard_metrics_source_utilization():
    """source_utilization = 被 evidence_cards 使用的搜索来源比例。"""
    from deepresearch.state import SearchResult
    cards = [
        EvidenceCard(
            id="c1", subquestion_id="sq1", claim="Claim",
            source_url="https://used.com/1",
            source_title="T", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="single_source",
            corroborating_sources=[], confidence="medium",
        ),
    ]
    sources = [
        SearchResult(subquestion_id="sq1", title="Used", url="https://used.com/1", content="..."),
        SearchResult(subquestion_id="sq1", title="Unused", url="https://unused.com/1", content="..."),
    ]
    state = {"evidence_cards": cards, "search_results": sources}

    result = compute_standard_metrics(state)

    assert result.source_utilization == 0.5  # 1 used / 2 total


def test_compute_standard_metrics_domain_diversity():
    """domain_diversity = 搜索结果的独立域名数。"""
    from deepresearch.state import SearchResult
    sources = [
        SearchResult(subquestion_id="sq1", title="A", url="https://example.com/1", content="..."),
        SearchResult(subquestion_id="sq1", title="B", url="https://other.org/1", content="..."),
        SearchResult(subquestion_id="sq2", title="C", url="https://example.com/2", content="..."),
    ]
    state = {"search_results": sources}

    result = compute_standard_metrics(state)

    assert result.domain_diversity == 2  # example.com + other.org


def test_compute_standard_metrics_with_review():
    """有 review 时正确捕获评分和状态。"""
    review = ReviewResult(passed=True, score=85, issues=[], suggestions=[])
    state = {"review": review}

    result = compute_standard_metrics(state)

    assert result.review_score == 85
    assert result.review_passed is True
    assert result.rewrite_triggered is False


def test_compute_standard_metrics_rewrite_triggered():
    """review_rewritten 为 True 时 rewrite_triggered 为 True。"""
    review = ReviewResult(passed=True, score=65, issues=["missing depth"], suggestions=["add more"])
    state = {"review": review, "review_rewritten": True}

    result = compute_standard_metrics(state)

    assert result.rewrite_triggered is True


def test_compute_standard_metrics_citation_validation():
    """有 report_markdown 时计算 citation 相关指标。"""
    from deepresearch.state import SearchResult
    report = (
        "Report body with citation.[1]\n\n"
        "## Sources\n"
        "[1] https://example.com/source-a\n"
    )
    sources = [
        SearchResult(subquestion_id="sq1", title="A", url="https://example.com/source-a", content="..."),
    ]
    state = {
        "report_markdown": report,
        "search_results": sources,
        "report_status": "success",
        "validation_failures": [],
    }

    result = compute_standard_metrics(state)

    assert result.citation_coverage == 1.0
    assert result.source_citation_rate == 1.0
    assert result.orphan_url_count == 0
    assert result.validation_first_pass is True


def test_compute_standard_metrics_citation_with_orphan_url():
    """Sources 中的 URL 不在搜索结果中 → orphan_url_count > 0。"""
    from deepresearch.state import SearchResult
    report = (
        "Report body.[1]\n\n"
        "## Sources\n"
        "[1] https://not-in-results.com/fake\n"
    )
    sources = [
        SearchResult(subquestion_id="sq1", title="A", url="https://example.com/real", content="..."),
    ]
    state = {
        "report_markdown": report,
        "search_results": sources,
        "report_status": "failed_validation",
        "validation_failures": [{"reason": "invalid_source_urls"}],
    }

    result = compute_standard_metrics(state)

    assert result.orphan_url_count == 1
    assert result.validation_first_pass is False


def test_compute_standard_metrics_handles_missing_url():
    """当 search_result 的 url 为空字符串时不会崩溃。"""
    from deepresearch.state import SearchResult
    sources = [
        SearchResult(subquestion_id="sq1", title="A", url="", content="..."),
    ]
    cards = [
        EvidenceCard(
            id="c1", subquestion_id="sq1", claim="Claim",
            source_url="https://example.com/a",
            source_title="T", supporting_snippet="...",
            content_type="search_content",
            corroboration_level="single_source",
            corroborating_sources=[], confidence="medium",
        ),
    ]
    state = {"evidence_cards": cards, "search_results": sources}

    result = compute_standard_metrics(state)
    # 不应崩溃，source_utilization 和 domain_diversity 应为 0
    assert result.source_utilization == 0.0
    assert result.domain_diversity == 0
