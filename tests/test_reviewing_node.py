from tests.conftest import FakeLLMClient

from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.state import SearchResult


def test_review_report_parses_review():
    llm = FakeLLMClient([
        '{"passed":true,"score":88,"issues":[],"suggestions":["Add more market data"]}'
    ])
    node = make_review_report_node(llm)

    result = node({
        "question": "AI search",
        "report_markdown": "# Report\n\nSource: https://example.com",
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "errors": [],
    })

    assert result["review"].passed is True
    assert result["review"].score == 88
