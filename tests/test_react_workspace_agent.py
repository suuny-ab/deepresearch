"""Tests for ReAct V3 agent with Workspace-based architecture."""

import json
from unittest.mock import MagicMock

from deepresearch.agents.react_workspace import (
    AgentResult,
    AgentStep,
    ReActV2Agent,
    ResearchNote,
    TopicState,
    Workspace,
    _extract_action_json,
    build_action_prompt,
    build_plan_prompt,
)
from deepresearch.state import TokenUsage, UsageInfo
from deepresearch.tools.base import ToolResult
from deepresearch.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fake tools
# ---------------------------------------------------------------------------


class FakeSearchTool:
    name = "tavily_search"
    description = "Search the web."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    def __init__(self):
        self.calls: list[dict] = []

    def execute(self, query: str, max_results: int = 5) -> ToolResult:
        self.calls.append({"query": query, "max_results": max_results})
        return ToolResult(
            content=f"Search results for '{query}':\n1. **Result A**\n   URL: https://example.com/a\n   Content about {query}.\n\n2. **Result B**\n   URL: https://other.org/b\n   Content about {query}.",
            urls=["https://example.com/a", "https://other.org/b"],
            metadata={"count": 2},
        )


class FailingLLMClient:
    def complete(self, prompt: str) -> tuple[str, UsageInfo]:
        raise RuntimeError("Simulated LLM failure")


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _plan_json(topics: list[dict] | None = None) -> str:
    if topics is None:
        topics = [
            {"id": "t1", "topic": "市场概况"},
            {"id": "t2", "topic": "主要参与者"},
            {"id": "t3", "topic": "未来展望"},
        ]
    return json.dumps({"summary": "研究策略", "topics": topics})


def _search_action(query: str = "market size 2026", topic_id: str = "t1") -> str:
    return json.dumps({
        "reasoning": f"搜索 {query} 以获取数据",
        "action": "search",
        "topic_id": topic_id,
        "input": {"query": query, "max_results": 5},
    })


def _set_topic_action(topic_id: str = "t1", status: str = "saturated", summary: str = "已有足够数据") -> str:
    return json.dumps({
        "reasoning": f"标记 {topic_id} 为 {status}",
        "action": "set_topic",
        "topic_id": topic_id,
        "input": {"status": status, "findings_summary": summary},
    })


def _synthesize_action() -> str:
    return json.dumps({"reasoning": "信息足够，写报告", "action": "synthesize"})


def _evidence_cards_json() -> str:
    return json.dumps({
        "evidence_cards": [{
            "id": "c1", "subquestion_id": "react-v3",
            "claim": "The market is growing at 15% annually.",
            "source_url": "https://example.com/a",
            "source_title": "Example Report",
            "supporting_snippet": "The market has grown 15% year over year.",
            "content_type": "search_content",
            "corroboration_level": "single_source",
            "corroborating_sources": [],
            "confidence": "medium",
        }],
    })


def _valid_report(question: str = "Test question") -> str:
    return (
        f"# {question}\n\n## Abstract\n\nThis report examines the question [1].\n\n"
        "## Key Findings\n\n- The market is growing rapidly [1].\n\n"
        "## Analysis\n\nDetailed analysis [1].\n\n"
        "## Conclusion\n\nEvidence supports findings [1].\n\n"
        "## Sources\n\n- [1]: https://example.com/a\n"
    )


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


def test_topic_state_defaults():
    t = TopicState(id="t1", topic="Test")
    assert t.status == "active"
    assert t.findings_summary == ""


def test_workspace_topic_by_id():
    ws = Workspace(topics=[
        TopicState(id="t1", topic="First"),
        TopicState(id="t2", topic="Second"),
    ])
    assert ws.topic_by_id("t1") is not None
    assert ws.topic_by_id("t3") is None


def test_workspace_format_includes_topic_statuses():
    ws = Workspace(topics=[
        TopicState(id="t1", topic="Topic 1", status="active"),
        TopicState(id="t2", topic="Topic 2", status="saturated", findings_summary="Done"),
    ])
    formatted = ws.format_for_prompt()
    assert "active" in formatted
    assert "saturated" in formatted
    assert "Topic 1" in formatted
    assert "Done" in formatted


def test_agent_step_fields():
    s = AgentStep(iteration=1, action="search", reasoning="test")
    assert s.action == "search"
    assert s.iteration == 1


def test_agent_result_defaults():
    r = AgentResult()
    assert r.report == ""
    assert r.steps == []


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


def test_build_plan_prompt_contains_question():
    prompt = build_plan_prompt("AI trends")
    assert "AI trends" in prompt
    assert "topics" in prompt.lower()


def test_build_action_prompt_shows_workspace():
    ws = Workspace(topics=[
        TopicState(id="t1", topic="Topic 1", status="active"),
        TopicState(id="t2", topic="Topic 2", status="saturated", findings_summary="Done"),
    ])
    ws.notes = [
        ResearchNote(topic_id="t1", content="Finding about T1",
                     source_url="https://x.com", source_title="X"),
    ]
    prompt = build_action_prompt(
        question="Q", workspace=ws,
        iteration=1, max_iterations=10, recent_steps=[],
    )
    assert "Topic 1" in prompt
    assert "saturated" in prompt
    assert "Done" in prompt
    assert "synthesize" in prompt


def test_build_action_prompt_includes_recent_steps():
    ws = Workspace(topics=[TopicState(id="t1", topic="T1")])
    steps = [AgentStep(iteration=1, action="search", reasoning="我需要数据")]
    prompt = build_action_prompt(
        question="Q", workspace=ws,
        iteration=2, max_iterations=10, recent_steps=steps,
    )
    assert "search" in prompt
    assert "需要数据" in prompt


# ---------------------------------------------------------------------------
# JSON parsing tests
# ---------------------------------------------------------------------------


def test_extract_action_json_raw():
    result = _extract_action_json('{"action": "search", "topic_id": "t1"}')
    assert result["action"] == "search"
    assert result["topic_id"] == "t1"


def test_extract_action_json_fenced():
    result = _extract_action_json('```json\n{"action": "set_topic"}\n```')
    assert result["action"] == "set_topic"


def test_extract_action_json_invalid():
    assert _extract_action_json("not json") == {}


def test_extract_action_json_with_input():
    raw = '{"reasoning": "test", "action": "search", "topic_id": "t1", "input": {"query": "market size"}}'
    result = _extract_action_json(raw)
    assert result["action"] == "search"
    assert result["input"]["query"] == "market size"


# ---------------------------------------------------------------------------
# Agent lifecycle tests
# ---------------------------------------------------------------------------


def test_v3_agent_plans_and_searches_and_synthesizes():
    """Full cycle: plan → search → set_topic → synthesize."""
    responses = [
        _plan_json(),                                              # Phase 0
        _search_action("AI market trends", "t1"),                  # Iter 1
        _set_topic_action("t1", "saturated", "Market data found"),  # Iter 2
        _synthesize_action(),                                      # Iter 3
        _evidence_cards_json(),                                    # Synthesis
        _valid_report("AI market trends"),                         # Report
    ]

    llm = MagicMock()
    usage = UsageInfo(prompt_tokens=100, completion_tokens=50, estimated_cost=0.0001)
    llm.complete = MagicMock(side_effect=[(r, usage) for r in responses])
    llm.complete_stream = MagicMock(side_effect=[
        iter([(responses[5], usage)]),  # Report streaming (will fail on second call)
    ])

    tools = ToolRegistry([FakeSearchTool()])
    agent = ReActV2Agent(llm=llm, tools=tools, max_iterations=10)

    # Use run() which collects from run_stream()
    # Since we can't easily mock complete_stream for validation, test run_stream directly
    events = list(agent.run_stream("AI market trends"))

    # Verify event types
    types = {e["type"] for e in events}
    assert "phase" in types
    assert "step" in types
    assert "done" in types

    # Verify steps
    steps = [e for e in events if e["type"] == "step"]
    assert len(steps) >= 3  # plan, search, set_topic, synthesize


def test_v3_agent_handles_plan_failure():
    llm = FailingLLMClient()
    tools = ToolRegistry([FakeSearchTool()])
    agent = ReActV2Agent(llm=llm, tools=tools)

    events = list(agent.run_stream("Test"))
    errors = [e for e in events if e["type"] == "error"]
    assert len(errors) >= 1


def test_v3_agent_deduplicates_searches():
    query = "exact same query"
    responses = [
        _plan_json(),
        _search_action(query, "t1"),
        _search_action(query, "t1"),
        _search_action(query, "t1"),
        _search_action(query, "t1"),  # 4th duplicate → 3 dry rounds → break
        _evidence_cards_json(),
        _valid_report(),
    ]

    llm = MagicMock()
    usage = UsageInfo()
    llm.complete = MagicMock(side_effect=[(r, usage) for r in responses])
    # Mock stream for synthesis
    llm.complete_stream = MagicMock(return_value=iter([]))

    search_tool = FakeSearchTool()
    tools = ToolRegistry([search_tool])
    agent = ReActV2Agent(llm=llm, tools=tools, max_iterations=10)

    events = list(agent.run_stream("Test"))
    # Only 1 real search call
    assert len(search_tool.calls) == 1


def test_v3_agent_stops_on_max_iterations():
    responses = [_plan_json()]
    for _ in range(5):
        responses.append(_search_action(f"q{_}", "t1"))
    responses.append(_evidence_cards_json())
    responses.append(_valid_report())

    llm = MagicMock()
    usage = UsageInfo()
    llm.complete = MagicMock(side_effect=[(r, usage) for r in responses])
    llm.complete_stream = MagicMock(return_value=iter([]))

    tools = ToolRegistry([FakeSearchTool()])
    agent = ReActV2Agent(llm=llm, tools=tools, max_iterations=3)

    events = list(agent.run_stream("Test"))
    done = [e for e in events if e["type"] == "done"]
    assert len(done) >= 1
    assert done[-1]["data"]["iterations"] <= 3 + 1


def test_v3_agent_handles_action_llm_failure():
    call_count = [0]
    usage = UsageInfo()

    def side_effect(prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return _plan_json(), usage
        raise RuntimeError("Simulated LLM failure")

    llm = MagicMock()
    llm.complete = MagicMock(side_effect=side_effect)
    llm.complete_stream = MagicMock(return_value=iter([]))

    tools = ToolRegistry([FakeSearchTool()])
    agent = ReActV2Agent(llm=llm, tools=tools, max_iterations=10)

    events = list(agent.run_stream("Test"))
    errors = [e for e in events if e["type"] == "error"]
    assert len(errors) >= 1


# ---------------------------------------------------------------------------
# Runner integration test
# ---------------------------------------------------------------------------


_MOCK_REACT_V2_RESPONSES = [
    _plan_json([{"id": "t1", "topic": "AI trends"}]),
    _search_action("AI trends 2026", "t1"),
    _set_topic_action("t1", "saturated", "Found data"),
    _synthesize_action(),
    _evidence_cards_json(),
    _valid_report("AI search trends"),
]


 