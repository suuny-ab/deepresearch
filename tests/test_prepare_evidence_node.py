from tests.conftest import FakeLLMClient

from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node
from deepresearch.state import ExtractedSource, SearchResult, SubQuestion


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


def test_prepare_evidence_dedupes_scores_extracts_and_builds_cards():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"RAG remains important.","source_url":"https://example.com/report.pdf","source_title":"Report","supporting_snippet":"RAG remains important.","content_type":"extracted_content","source_type":"industry_report","source_quality_score":85,"evidence_reliability":"high","confidence":"high"}]}'
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(
                subquestion_id="q1",
                title="Report",
                url="https://example.com/report.pdf",
                raw_content="RAG remains important.",
                source_type="industry_report",
                source_quality_score=85,
                source_quality_reason="Report-like source",
            )
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    state = {
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q1", title="Report", url="https://example.com/report.pdf", content="Summary"),
            SearchResult(subquestion_id="q1", query="q2", title="Report duplicate", url="https://www.example.com/report.pdf?utm_source=x", content="Summary duplicate"),
        ],
        "errors": [],
    }

    result = node(state)

    assert len(search.extracted_urls) == 1
    assert result["search_results"][0].source_type == "industry_report"
    assert result["evidence_cards"][0].id == "e1"
    assert result["evidence_metrics"]["raw_search_results"] == 2
    assert result["evidence_metrics"]["deduped_sources"] == 1
    assert result["evidence_metrics"]["duplicates_removed"] == 1
    assert result["evidence_metrics"]["extracted_sources"] == 1
    assert result["evidence_metrics"]["evidence_cards"] == 1
    assert result["evidence_metrics"]["source_quality"] == {"industry_report": 1}
    assert result["evidence_metrics"]["evidence_reliability"] == {"high": 1}


def test_prepare_evidence_preserves_same_normalized_url_per_subquestion():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Shared source supports q1.","source_url":"https://example.com/report","source_title":"Report","supporting_snippet":"Shared source supports q1.","content_type":"extracted_content","source_type":"unknown","source_quality_score":50,"evidence_reliability":"medium","confidence":"medium"},{"id":"e2","subquestion_id":"q2","claim":"Shared source supports q2.","source_url":"https://www.example.com/report?utm_source=feed","source_title":"Report copy","supporting_snippet":"Shared source supports q2.","content_type":"extracted_content","source_type":"unknown","source_quality_score":50,"evidence_reliability":"medium","confidence":"medium"}]}'
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

    assert [source.subquestion_id for source in result["extracted_sources"]] == ["q1", "q2"]
    assert [search_result.subquestion_id for search_result in result["search_results"]] == ["q1", "q2"]
    assert {card.subquestion_id for card in result["evidence_cards"]} == {"q1", "q2"}
    assert result["evidence_metrics"]["deduped_sources"] == 2
    assert result["evidence_metrics"]["duplicates_removed"] == 0


def test_prepare_evidence_does_not_mutate_input_search_results():
    llm = FakeLLMClient(['{"evidence_cards":[]}'])
    search = FakeSearchClient(fail_extract=True)
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)
    original = SearchResult(subquestion_id="q1", query="q", title="Policy", url="https://www.gov.cn/policy", content="Summary")

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [original],
        "errors": [],
    })

    assert original.source_type == "unknown"
    assert original.source_quality_score == 50
    assert original.source_quality_reason == ""
    assert result["search_results"][0].source_type == "official"
    assert result["search_results"][0] is not original


def test_prepare_evidence_falls_back_to_search_content_when_extract_fails():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Fallback claim.","source_url":"https://example.com/a","source_title":"A","supporting_snippet":"Summary","content_type":"search_content","source_type":"unknown","source_quality_score":50,"evidence_reliability":"low","confidence":"low"}]}'
    ])
    search = FakeSearchClient(fail_extract=True)
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [SearchResult(subquestion_id="q1", query="q", title="A", url="https://example.com/a", content="Summary")],
        "errors": [],
    })

    assert result["extracted_sources"][0].raw_content == "Summary"
    assert result["evidence_cards"][0].content_type == "search_content"
    assert result["evidence_cards"][0].evidence_reliability == "low"
    assert result["evidence_metrics"]["evidence_reliability"] == {"low": 1}
    assert result["errors"]


def test_prepare_evidence_prioritizes_quality_and_rejects_invalid_card_urls():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"bad","subquestion_id":"q1","claim":"Unsupported.","source_url":"https://evil.example/bad","source_title":"Bad","supporting_snippet":"Unsupported.","content_type":"extracted_content","source_type":"unknown","source_quality_score":50,"evidence_reliability":"medium","confidence":"medium"},{"id":"good","subquestion_id":"q1","claim":"Official claim.","source_url":"https://www.gov.cn/policy","source_title":"Policy","supporting_snippet":"Official claim.","content_type":"extracted_content","source_type":"official","source_quality_score":95,"evidence_reliability":"high","confidence":"high"}]}'
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(subquestion_id="q1", title="Policy", url="https://www.gov.cn/policy", raw_content="Official claim."),
            ExtractedSource(subquestion_id="q1", title="SEO", url="https://seo.com/blog/ai-search", raw_content="SEO claim."),
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=2)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q", title="SEO", url="https://seo.com/blog/ai-search", content="SEO summary"),
            SearchResult(subquestion_id="q1", query="q", title="Policy", url="https://www.gov.cn/policy", content="Policy summary"),
            SearchResult(subquestion_id="q1", query="q", title="Unknown", url="https://example.com/unknown", content="Unknown summary"),
        ],
        "errors": [],
    })

    assert search.extract_calls[0]["urls"] == ["https://www.gov.cn/policy", "https://example.com/unknown"]
    assert [card.id for card in result["evidence_cards"]] == ["good"]
    assert any("invalid source_url" in error for error in result["errors"])
