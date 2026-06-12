from tests.conftest import FakeLLMClient

from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node, _run_assertions
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
            from deepresearch.errors import SearchError
            raise SearchError("extract failed")
        return self.extracted_sources

    def search(self, query, *, subquestion_id, max_results):
        raise NotImplementedError("FakeSearchClient for evidence tests does not implement search")


def test_two_phase_evidence_pipeline():
    llm = FakeLLMClient([
        '{"claims":[{"id":"e1","subquestion_id":"q1","claim":"RAG is important.","source_url":"https://example.com/report.pdf","source_title":"Report","supporting_snippet":"RAG is important.","content_type":"extracted_content","confidence":"high"}]}',
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"RAG is important.","source_url":"https://example.com/report.pdf","source_title":"Report","supporting_snippet":"RAG is important.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(subquestion_id="q1", title="Report", url="https://example.com/report.pdf", raw_content="RAG is important."),
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    state = {
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [SearchResult(subquestion_id="q1", query="q", title="Report", url="https://example.com/report.pdf", content="Summary", score=0.9)],
        "errors": [],
    }

    result = node(state)

    assert result["evidence_cards"][0].id == "e1"
    assert result["evidence_cards"][0].corroboration_level == "single_source"
    assert "extracted_claims" in result
    assert result["evidence_metrics"]["evidence_cards"] == 1
    assert "corroboration" in result["evidence_metrics"]


def test_extract_fallback_when_phase1_fails():
    llm = FakeLLMClient(['{"claims":[]}'])
    search = FakeSearchClient(fail_extract=True)
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [SearchResult(subquestion_id="q1", query="q", title="A", url="https://example.com/a", content="Summary")],
        "errors": [],
    })

    assert result["evidence_cards"] == []
    assert result["errors"]


def test_phase2_called_per_subquestion():
    sq1 = SubQuestion(id="q1", question="Q1?", search_query="q1", search_queries=["q1"], rationale="r1")
    sq2 = SubQuestion(id="q2", question="Q2?", search_query="q2", search_queries=["q2"], rationale="r2")

    llm = FakeLLMClient([
        '{"claims":[{"id":"e1","subquestion_id":"q1","claim":"Claim q1.","source_url":"https://a.example/x","source_title":"A","supporting_snippet":"Claim q1.","content_type":"extracted_content","confidence":"high"},{"id":"e2","subquestion_id":"q2","claim":"Claim q2.","source_url":"https://b.example/y","source_title":"B","supporting_snippet":"Claim q2.","content_type":"extracted_content","confidence":"high"}]}',
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Claim q1.","source_url":"https://a.example/x","source_title":"A","supporting_snippet":"Claim q1.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
        '{"evidence_cards":[{"id":"e2","subquestion_id":"q2","claim":"Claim q2.","source_url":"https://b.example/y","source_title":"B","supporting_snippet":"Claim q2.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(subquestion_id="q1", url="https://a.example/x", title="A", raw_content="Claim q1."),
            ExtractedSource(subquestion_id="q2", url="https://b.example/y", title="B", raw_content="Claim q2."),
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    result = node({
        "question": "AI search",
        "subquestions": [sq1, sq2],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q1", title="A", url="https://a.example/x", content="Claim q1.", score=0.9),
            SearchResult(subquestion_id="q2", query="q2", title="B", url="https://b.example/y", content="Claim q2.", score=0.8),
        ],
        "errors": [],
    })

    assert len(result["evidence_cards"]) == 2
    assert {c.subquestion_id for c in result["evidence_cards"]} == {"q1", "q2"}


def test_assertion_source_utilization_warns_on_zero_claim_source():
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://a.example/x", title="A", raw_content="Content"),
        ExtractedSource(subquestion_id="q1", url="https://b.example/y", title="B", raw_content="Content"),
    ]

    results = _run_assertions([], sources, [])
    assert len(results) > 0
    assert any("0 claims" in r for r in results)


def test_assertion_corroboration_rate_warns_below_60_percent():
    cards = [
        EvidenceCard(id="e1", subquestion_id="q1", claim="C1", source_url="https://a.example/x", source_title="A",
                     supporting_snippet="C1", content_type="extracted_content",
                     corroboration_level="single_source", corroborating_sources=[], confidence="medium"),
        EvidenceCard(id="e2", subquestion_id="q1", claim="C2", source_url="https://a.example/x", source_title="A",
                     supporting_snippet="C2", content_type="extracted_content",
                     corroboration_level="single_source", corroborating_sources=[], confidence="medium"),
    ]
    results = _run_assertions([], [], cards)
    assert any("corroboration rate" in r.lower() for r in results)


def test_assertion_passes_with_good_data():
    from deepresearch.state import ExtractedClaim
    claims = [
        ExtractedClaim(id="e1", subquestion_id="q1", claim="C1", source_url="https://a.example/x", source_title="A",
                       supporting_snippet="C1", content_type="extracted_content", confidence="high"),
    ]
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://a.example/x", title="A", raw_content="Content"),
    ]
    cards = [
        EvidenceCard(id="e1", subquestion_id="q1", claim="C1", source_url="https://a.example/x", source_title="A",
                     supporting_snippet="C1", content_type="extracted_content",
                     corroboration_level="strongly_corroborated", corroborating_sources=["https://b.example/y", "https://c.example/z"], confidence="high"),
    ]
    results = _run_assertions(claims, sources, cards)
    assert len([r for r in results if "[FAIL]" in r]) == 0
