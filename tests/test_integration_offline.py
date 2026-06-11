from tests.conftest import FakeLLMClient

from deepresearch.graph import create_research_app
from deepresearch.nodes.planning import make_plan_research_node
from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.nodes.saving import make_save_report_node
from deepresearch.nodes.synthesizing import make_synthesize_notes_node
from deepresearch.nodes.writing import make_write_report_node
from deepresearch.state import SearchResult


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

    app = create_research_app(
        plan_research=make_plan_research_node(llm, max_subquestions=5),
        search_web=make_search_web_node(search, results_per_query=5),
        synthesize_notes=make_synthesize_notes_node(llm),
        write_report=make_write_report_node(llm),
        review_report=make_review_report_node(llm),
        save_report=make_save_report_node(tmp_path),
    )

    result = app.invoke({"question": "AI search", "errors": []})

    assert result["output_path"]
    assert result["review"].score == 90
    assert result["report_status"] == "success"
    assert "# AI Search" in result["report_markdown"]
