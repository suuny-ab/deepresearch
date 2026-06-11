import pytest

from deepresearch.errors import SearchError
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.state import SearchResult, SubQuestion


class FakeSearchClient:
    def __init__(self, failures: set[str] | None = None):
        self.failures = failures or set()
        self.queries: list[str] = []

    def search(self, query: str, *, subquestion_id: str, max_results: int):
        self.queries.append(query)
        if query in self.failures:
            raise SearchError("search failed")
        return [SearchResult(subquestion_id=subquestion_id, query=query, title="Source", url=f"https://example.com/{subquestion_id}", content="Content")]


def test_search_web_collects_results():
    client = FakeSearchClient()
    node = make_search_web_node(client, results_per_query=5)

    result = node({
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "errors": [],
    })

    assert result["search_results"][0].url == "https://example.com/q1"
    assert client.queries == ["AI search"]


def test_search_web_continues_after_one_failure():
    client = FakeSearchClient(failures={"bad query"})
    node = make_search_web_node(client, results_per_query=5)

    result = node({
        "subquestions": [
            SubQuestion(id="q1", question="Bad", search_query="bad query", rationale="Failure"),
            SubQuestion(id="q2", question="Good", search_query="good query", rationale="Success"),
        ],
        "errors": [],
    })

    assert len(result["search_results"]) == 1
    assert result["errors"]


def test_search_web_raises_when_all_searches_fail():
    client = FakeSearchClient(failures={"bad query"})
    node = make_search_web_node(client, results_per_query=5)

    with pytest.raises(SearchError, match="All searches failed"):
        node({
            "subquestions": [SubQuestion(id="q1", question="Bad", search_query="bad query", rationale="Failure")],
            "errors": [],
        })


def test_search_web_runs_all_search_queries():
    client = FakeSearchClient()
    node = make_search_web_node(client, results_per_query=3)

    result = node({
        "subquestions": [SubQuestion(
            id="q1",
            question="What?",
            search_query="fallback query",
            search_queries=["query one", "query two", "query three"],
            rationale="Coverage",
        )],
        "errors": [],
    })

    assert client.queries == ["query one", "query two", "query three"]
    assert [item.query for item in result["search_results"]] == ["query one", "query two", "query three"]
