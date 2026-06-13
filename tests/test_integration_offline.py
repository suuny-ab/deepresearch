from tests.conftest import FakeLLMClient

from deepresearch.graph import create_research_app
from deepresearch.nodes.planning import make_plan_research_node
from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node
from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.nodes.saving import make_save_report_node
from deepresearch.nodes.writing import make_write_report_node
from deepresearch.state import ExtractedSource, SearchResult


class FakeSearchClient:
    def __init__(self):
        self.extract_calls = []

    def search(self, query: str, *, subquestion_id: str, max_results: int):
        return [SearchResult(subquestion_id=subquestion_id, query=query, title="Source", url="https://example.com/source", content="AI search uses generated answers.")]

    def extract(self, urls: list[str], *, subquestion_id: str):
        self.extract_calls.append({"urls": list(urls), "subquestion_id": subquestion_id})
        return [
            ExtractedSource(
                subquestion_id=subquestion_id,
                title="Source",
                url=url,
                raw_content="AI search uses generated answers.",
            )
            for url in urls
        ]


def test_full_graph_runs_offline(tmp_path):
    llm = FakeLLMClient([
        # plan_research
        '{"subquestions":[{"id":"q1","question":"What is AI search?","search_query":"AI search","rationale":"Background"}]}',
        # Phase 1: extraction
        '{"claims":[{"id":"e1","subquestion_id":"q1","claim":"AI search uses generated answers.","source_url":"https://example.com/source","source_title":"Source","supporting_snippet":"AI search uses generated answers.","content_type":"extracted_content","confidence":"high"}]}',
        # Phase 2 q1: validation
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"AI search uses generated answers.","source_url":"https://example.com/source","source_title":"Source","supporting_snippet":"AI search uses generated answers.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
        # write_report
        '# AI Search\n\nAI search uses generated answers.[1]\n\n## Sources\n\n[1] https://example.com/source',
        # review_report
        '{"passed":true,"score":90,"issues":[],"suggestions":[]}',
    ])
    search = FakeSearchClient()

    app = create_research_app(
        plan_research=make_plan_research_node(llm, max_subquestions=5),
        search_web=make_search_web_node(search, results_per_query=5),
        prepare_evidence=make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3),
        write_report=make_write_report_node(llm),
        review_report=make_review_report_node(llm),
        save_report=make_save_report_node(tmp_path),
    )

    result = app.invoke({"question": "AI search", "errors": []})

    assert result["output_path"]
    assert result["review"].score == 90
    assert result["report_status"] == "success"
    assert result["validation_attempts"] == 1
    assert result["rewrite_attempted"] is False
    assert search.extract_calls == [{"urls": ["https://example.com/source"], "subquestion_id": "q1"}]
    assert result["evidence_cards"][0].supporting_snippet == "AI search uses generated answers."
    assert result["evidence_cards"][0].id == "e1"
    assert result["evidence_cards"][0].content_type == "extracted_content"
    assert "# AI Search" in result["report_markdown"]
