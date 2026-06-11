from tests.conftest import FakeLLMClient
from deepresearch.nodes.planning import make_plan_research_node


def test_plan_research_parses_subquestions():
    llm = FakeLLMClient([
        '{"subquestions":[{"id":"q1","question":"What is AI search?","search_query":"AI search definition","rationale":"Background"}]}'
    ])
    node = make_plan_research_node(llm, max_subquestions=5)

    result = node({"question": "AI search trends", "errors": []})

    assert result["subquestions"][0].id == "q1"
    assert result["errors"] == []


def test_plan_research_fallback_on_bad_json():
    llm = FakeLLMClient(["not json"])
    node = make_plan_research_node(llm, max_subquestions=5)

    result = node({"question": "AI search trends", "errors": []})

    assert result["subquestions"][0].question == "AI search trends"
    assert result["subquestions"][0].search_query == "AI search trends"
    assert result["errors"]
