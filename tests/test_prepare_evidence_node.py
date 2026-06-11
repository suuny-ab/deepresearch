from tests.conftest import FakeLLMClient

from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node, _validate_corroboration
from deepresearch.state import EvidenceCard, ExtractedSource, SearchResult, SubQuestion


class FakeSearchClient:
    def __init__(self, fail_extract=False, extracted_sources=None):
        self.extract_calls = []
        self.fail_extract = fail_extract
        self.extracted_sources = extracted_sources or []

    @property
    def extracted_urls(self):
        return [url for call in self.extract_calls for url in call["urls"]]

    def extract(self, urls, *, subquestion_id):
        self.extract_calls.append({"urls": list(urls), "subquestion_id": subquestion_id})
        if self.fail_extract:
            raise Exception("extract failed")
        return self.extracted_sources


def test_prepare_evidence_dedupes_and_selects_by_relevance():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"RAG remains important.","source_url":"https://example.com/report.pdf","source_title":"Report","supporting_snippet":"RAG remains important.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}'
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(
                subquestion_id="q1",
                title="Report",
                url="https://example.com/report.pdf",
                raw_content="RAG remains important.",
            )
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    state = {
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q1", title="Report", url="https://example.com/report.pdf", content="Summary", score=0.9),
            SearchResult(subquestion_id="q1", query="q2", title="Report duplicate", url="https://www.example.com/report.pdf?utm_source=x", content="Summary duplicate", score=0.8),
        ],
        "errors": [],
    }

    result = node(state)

    assert len(search.extracted_urls) == 1
    assert result["evidence_cards"][0].id == "e1"
    assert result["evidence_metrics"]["raw_search_results"] == 2
    assert result["evidence_metrics"]["deduped_sources"] == 1
    assert result["evidence_metrics"]["duplicates_removed"] == 1
    assert result["evidence_metrics"]["extracted_sources"] == 1
    assert result["evidence_metrics"]["evidence_cards"] == 1
    assert "corroboration" in result["evidence_metrics"]


def test_prepare_evidence_selects_diverse_domains():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Gov perspective.","source_url":"https://www.gov.cn/policy","source_title":"Policy","supporting_snippet":"Gov perspective.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"},{"id":"e2","subquestion_id":"q1","claim":"Blog perspective.","source_url":"https://example.com/blog","source_title":"Blog","supporting_snippet":"Blog perspective.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"medium"}]}'
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(subquestion_id="q1", title="Policy", url="https://www.gov.cn/policy", raw_content="Gov perspective."),
            ExtractedSource(subquestion_id="q1", title="Blog", url="https://example.com/blog", raw_content="Blog perspective."),
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=2)

    state = {
        "question": "AI policy",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q", title="Policy", url="https://www.gov.cn/policy", content="Gov perspective.", score=0.95),
            SearchResult(subquestion_id="q1", query="q", title="Policy copy", url="https://www.gov.cn/policy?page=2", content="Same gov perspective.", score=0.7),
            SearchResult(subquestion_id="q1", query="q", title="Blog", url="https://example.com/blog", content="Blog perspective.", score=0.6),
        ],
        "errors": [],
    }

    result = node(state)

    assert len(search.extracted_urls) == 2
    selected_urls = search.extract_calls[0]["urls"]
    from urllib.parse import urlparse
    domains = set()
    for url in selected_urls:
        host = urlparse(url).hostname or ""
        if host.startswith("www."):
            host = host[4:]
        domains.add(host.lower())
    assert len(domains) == 2


def test_prepare_evidence_preserves_same_normalized_url_per_subquestion():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Shared source supports q1.","source_url":"https://example.com/report","source_title":"Report","supporting_snippet":"Shared source supports q1.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"medium"},{"id":"e2","subquestion_id":"q2","claim":"Shared source supports q2.","source_url":"https://www.example.com/report?utm_source=feed","source_title":"Report copy","supporting_snippet":"Shared source supports q2.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"medium"}]}'
    ])
    search = FakeSearchClient(fail_extract=True)
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    result = node({
        "question": "AI search",
        "subquestions": [
            SubQuestion(id="q1", question="What changed?", search_query="q1", search_queries=["q1"], rationale="r1"),
            SubQuestion(id="q2", question="Why now?", search_query="q2", search_queries=["q2"], rationale="r2"),
        ],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q1", title="Report", url="https://example.com/report", content="Shared source supports q1."),
            SearchResult(subquestion_id="q2", query="q2", title="Report copy", url="https://www.example.com/report?utm_source=feed", content="Shared source supports q2."),
        ],
        "errors": [],
    })

    assert {card.subquestion_id for card in result["evidence_cards"]} == {"q1", "q2"}
    assert result["evidence_metrics"]["deduped_sources"] == 2
    assert result["evidence_metrics"]["duplicates_removed"] == 0


def test_prepare_evidence_falls_back_to_search_content_when_extract_fails():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Fallback claim.","source_url":"https://example.com/a","source_title":"A","supporting_snippet":"Summary","content_type":"search_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"low"}]}'
    ])
    search = FakeSearchClient(fail_extract=True)
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [SearchResult(subquestion_id="q1", query="q", title="A", url="https://example.com/a", content="Summary")],
        "errors": [],
    })

    assert result["evidence_cards"][0].content_type == "search_content"
    assert result["errors"]


def test_prepare_evidence_rejects_invalid_card_urls():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"bad","subquestion_id":"q1","claim":"Unsupported.","source_url":"https://evil.example/bad","source_title":"Bad","supporting_snippet":"Unsupported.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"medium"},{"id":"good","subquestion_id":"q1","claim":"Valid claim.","source_url":"https://www.gov.cn/policy","source_title":"Policy","supporting_snippet":"Valid claim.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}'
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(subquestion_id="q1", title="Policy", url="https://www.gov.cn/policy", raw_content="Valid claim."),
            ExtractedSource(subquestion_id="q1", title="SEO", url="https://seo.com/blog/ai-search", raw_content="SEO claim."),
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=2)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q", title="SEO", url="https://seo.com/blog/ai-search", content="SEO summary", score=0.9),
            SearchResult(subquestion_id="q1", query="q", title="Policy", url="https://www.gov.cn/policy", content="Policy summary", score=0.5),
            SearchResult(subquestion_id="q1", query="q", title="Unknown", url="https://example.com/unknown", content="Unknown summary", score=0.3),
        ],
        "errors": [],
    })

    assert [card.id for card in result["evidence_cards"]] == ["good"]
    assert any("invalid source_url" in error for error in result["errors"])


def test_validate_corroboration_drops_fabricated_urls():
    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="Claim.",
        source_url="https://example.com/a",
        source_title="A",
        supporting_snippet="Claim.",
        content_type="extracted_content",
        corroboration_level="weakly_corroborated",
        corroborating_sources=["https://fabricated.example/not-real", "https://real.example/b"],
        confidence="high",
    )

    extracted_urls = {"https://example.com/a", "https://real.example/b"}
    extracted_content_types = {"https://example.com/a": "extracted_content", "https://real.example/b": "extracted_content"}

    validated = _validate_corroboration(card, extracted_urls, extracted_content_types)

    assert "https://fabricated.example/not-real" not in validated.corroborating_sources
    assert "https://real.example/b" in validated.corroborating_sources


def test_validate_corroboration_rejects_same_domain():
    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="Claim.",
        source_url="https://example.com/a",
        source_title="A",
        supporting_snippet="Claim.",
        content_type="extracted_content",
        corroboration_level="weakly_corroborated",
        corroborating_sources=["https://example.com/b"],
        confidence="high",
    )

    extracted_urls = {"https://example.com/a", "https://example.com/b"}
    extracted_content_types = {"https://example.com/a": "extracted_content", "https://example.com/b": "extracted_content"}

    validated = _validate_corroboration(card, extracted_urls, extracted_content_types)

    assert validated.corroboration_level == "single_source"
    assert validated.corroborating_sources == []


def test_validate_corroboration_demotes_strongly_when_insufficient_full_text():
    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="Claim.",
        source_url="https://example.com/a",
        source_title="A",
        supporting_snippet="Claim.",
        content_type="extracted_content",
        corroboration_level="strongly_corroborated",
        corroborating_sources=["https://other1.example/x", "https://other2.example/y"],
        confidence="high",
    )

    extracted_urls = {"https://example.com/a", "https://other1.example/x", "https://other2.example/y"}
    extracted_content_types = {
        "https://example.com/a": "extracted_content",
        "https://other1.example/x": "extracted_content",
        "https://other2.example/y": "search_content",
    }

    validated = _validate_corroboration(card, extracted_urls, extracted_content_types)

    assert validated.corroboration_level == "weakly_corroborated"
