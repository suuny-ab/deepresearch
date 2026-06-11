from tests.conftest import FakeLLMClient

from deepresearch.graph import create_research_app
from deepresearch.nodes.planning import make_plan_research_node
from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.nodes.saving import make_save_report_node
from deepresearch.nodes.synthesizing import make_synthesize_notes_node
from deepresearch.nodes.writing import make_write_report_node
from deepresearch.state import EvidenceCard, SearchResult


class FakeSearchClient:
    def search(self, query: str, *, subquestion_id: str, max_results: int):
        return [SearchResult(subquestion_id=subquestion_id, title="Source", url="https://example.com/source", content="AI search uses generated answers.")]


def test_full_graph_runs_offline(tmp_path):
    llm = FakeLLMClient([
        '{"subquestions":[{"id":"q1","question":"What is AI search?","search_query":"AI search","rationale":"Background"}]}',
        '{"notes":[{"subquestion_id":"q1","key_findings":["AI search uses generated answers."],"source_urls":["https://example.com/source"],"confidence":"high"}]}',
        '# AI Search\n\nAI search uses generated answers.[1]\n\n## Sources\n\n[1] https://example.com/source',
        '{"passed":true,"score":90,"issues":[],"suggestions":[]}',
    ])
    search = FakeSearchClient()

    def fake_prepare_evidence(state):
        return {
            **state,
            "evidence_cards": [
                EvidenceCard(
                    id="e1",
                    subquestion_id="q1",
                    claim="AI search uses generated answers.",
                    source_url="https://example.com/source",
                    source_title="Source",
                    supporting_snippet="AI search uses generated answers.",
                    content_type="search_content",
                    source_type="unknown",
                    source_quality_score=50,
                    evidence_reliability="medium",
                    confidence="high",
                )
            ],
            "evidence_metrics": {
                "raw_search_results": 1,
                "deduped_sources": 1,
                "duplicates_removed": 0,
                "extracted_sources": 1,
                "evidence_cards": 1,
                "source_quality": {"unknown": 1},
                "evidence_reliability": {"medium": 1},
            },
        }

    app = create_research_app(
        plan_research=make_plan_research_node(llm, max_subquestions=5),
        search_web=make_search_web_node(search, results_per_query=5),
        prepare_evidence=fake_prepare_evidence,
        synthesize_notes=make_synthesize_notes_node(llm),
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
    assert result["evidence_cards"][0].id == "e1"
    assert result["evidence_metrics"]["evidence_cards"] == 1
    assert "# AI Search" in result["report_markdown"]
