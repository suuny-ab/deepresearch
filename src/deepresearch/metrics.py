"""纯函数度量计算模块。

从 ResearchState dict 中提取质量指标，不依赖 LLM 或外部服务。
与业务节点解耦：节点不 import 本模块，本模块不 import 节点。
"""

from collections import Counter

from deepresearch.citations import validate_citations
from deepresearch.state import StandardMetrics
from deepresearch.utils.urls import extract_domain, normalize_url


def compute_standard_metrics(state: dict) -> StandardMetrics:
    """从 state dict 计算全部标准质量指标。

    Args:
        state: ResearchState 的 dict 形式（graph.invoke() 的返回值）。

    Returns:
        StandardMetrics: 所有可计算的质量指标。缺失数据对应的字段为 None 或 0。
    """
    cards = state.get("evidence_cards", [])
    search_results = state.get("search_results", [])
    review = state.get("review")
    report = state.get("report_markdown", "")

    # --- 证据维度 ---

    evidence_card_count = len(cards)
    claims_per_source = evidence_card_count / len(search_results) if search_results else 0.0

    # source_utilization: 被 evidence_cards 使用的搜索来源比例
    card_urls = {normalize_url(c.source_url) for c in cards if c.source_url}
    source_urls = {normalize_url(s.url) for s in search_results if s.url}
    used_sources = card_urls & source_urls if source_urls else set()
    source_utilization = len(used_sources) / max(len(source_urls), 1)

    # corroboration 分布
    corr_counter = Counter(c.corroboration_level for c in cards)
    corroboration_strong = corr_counter.get("strongly_corroborated", 0)
    corroboration_weak = corr_counter.get("weakly_corroborated", 0)
    corroboration_single = corr_counter.get("single_source", 0)

    # domain_diversity: 搜索结果的独立域名数
    domains = {extract_domain(s.url) for s in search_results if s.url}
    domain_diversity = len(domains)

    # --- 审查维度 ---

    review_score = review.score if review is not None else None
    review_passed = review.passed if review is not None else None
    rewrite_triggered = bool(state.get("review_rewritten", False))

    # --- 结构正确性维度（依赖 citation 验证） ---

    citation_coverage = None
    source_citation_rate = None
    orphan_url_count = None
    validation_first_pass = None

    if report:
        allowed_urls = {normalize_url(s.url) for s in search_results if s.url}
        validation = validate_citations(report, allowed_urls)

        total_body = len(validation.body_citations)
        if total_body > 0:
            undefined = len(validation.undefined_citations)
            citation_coverage = round((total_body - undefined) / total_body, 3)

        total_sources = len(validation.source_citations)
        if total_sources > 0:
            unused = len(validation.unused_sources)
            source_citation_rate = round((total_sources - unused) / total_sources, 3)

        orphan_url_count = len(validation.invalid_source_urls)

    # validation_first_pass: 首次就通过 citation 校验
    failures = state.get("validation_failures", [])
    report_status = state.get("report_status")
    if report_status is not None:
        validation_first_pass = report_status == "success" and len(failures) == 0

    return StandardMetrics(
        evidence_card_count=evidence_card_count,
        claims_per_source=round(claims_per_source, 2),
        source_utilization=round(source_utilization, 2),
        corroboration_strong=corroboration_strong,
        corroboration_weak=corroboration_weak,
        corroboration_single=corroboration_single,
        domain_diversity=domain_diversity,
        review_score=review_score,
        review_passed=review_passed,
        rewrite_triggered=rewrite_triggered,
        citation_coverage=citation_coverage,
        source_citation_rate=source_citation_rate,
        orphan_url_count=orphan_url_count,
        validation_first_pass=validation_first_pass,
    )
