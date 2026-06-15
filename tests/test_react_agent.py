"""Tests for ReAct agent."""

from deepresearch.agents.react_agent import (
    ReActAgent,
    ReActResult,
    ReActStep,
    _extract_action_json,
    build_react_system_prompt,
)
from deepresearch.tools.base import ToolResult
from deepresearch.tools.registry import ToolRegistry
from tests.conftest import FakeLLMClient


class FakeSearchTool:
    name = "tavily_search"
    description = "Search the web."
    parameters = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    def __init__(self):
        self.calls: list[dict] = []

    def execute(self, query: str, max_results: int = 5) -> ToolResult:
        self.calls.append({"query": query, "max_results": max_results})
        return ToolResult(
            content=f"Search results for '{query}':\n1. **Result A**\n   URL: https://example.com/a\n   Content snippet about {query}.",
            urls=["https://example.com/a"],
            metadata={"count": 1},
        )


class FakeFetchTool:
    name = "web_fetch"
    description = "Fetch a webpage."
    parameters = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}

    def __init__(self):
        self.calls: list[dict] = []

    def execute(self, url: str) -> ToolResult:
        self.calls.append({"url": url})
        return ToolResult(
            content=f"Full content from {url}: AI search engines use RAG and neural ranking to improve relevance.",
            urls=[url],
        )


def test_react_agent_completes_full_cycle():
    """ReAct agent: search → fetch → write_report (with Option C + citation validation)."""
    # 5 LLM calls: search, fetch, write_report decision, Option C cards, write report
    llm = FakeLLMClient([
        '{"reasoning": "I need to search first.", "action": "search", "tool": "tavily_search", "input": {"query": "AI search trends"}}',
        '{"reasoning": "Good results, let me read one.", "action": "fetch", "tool": "web_fetch", "input": {"url": "https://example.com/a"}}',
        '{"reasoning": "I have enough information.", "action": "write_report"}',
        # Option C: findings → evidence_cards
        '{"evidence_cards": [{"id": "c1", "subquestion_id": "react", "claim": "AI search uses RAG.", "source_url": "https://example.com/a", "source_title": "Source A", "supporting_snippet": "AI uses RAG.", "content_type": "search_content", "corroboration_level": "single_source", "corroborating_sources": [], "confidence": "high"}]}',
        # write_report via build_writing_prompt → citation-valid output
        '# AI Search Trends Report\n\nAI search is evolving.[1]\n\n## Sources\n\n[1] https://example.com/a',
    ])

    tools = ToolRegistry([FakeSearchTool(), FakeFetchTool()])
    agent = ReActAgent(llm=llm, tools=tools, max_iterations=10)

    result = agent.run("AI search trends")

    assert result.iterations == 3  # search, fetch, write_report
    assert len(result.steps) == 3
    assert "AI Search" in result.report
    assert result.steps[0].action == "search"
    assert result.steps[1].action == "fetch"
    assert result.steps[2].action == "write_report"


def test_react_agent_stops_on_max_iterations():
    """ReAct agent stops when max_iterations reached."""
    # All responses say "search" — agent will run until max_iterations
    responses = [
        '{"reasoning": "Searching...", "action": "search", "tool": "tavily_search", "input": {"query": f"query {i}"}}'
        for i in range(12)
    ]
    llm = FakeLLMClient(responses)

    tools = ToolRegistry([FakeSearchTool()])
    agent = ReActAgent(llm=llm, tools=tools, max_iterations=3)

    result = agent.run("test")
    assert result.iterations <= 3


def test_react_agent_deduplicates_searches():
    """ReAct agent skips duplicate searches."""
    llm = FakeLLMClient([
        '{"reasoning": "Searching...", "action": "search", "tool": "tavily_search", "input": {"query": "AI trends"}}',
        '{"reasoning": "Let me search again...", "action": "search", "tool": "tavily_search", "input": {"query": "AI trends"}}',
        '{"reasoning": "Duplicate, stopping.", "action": "stop"}',
    ])

    search_tool = FakeSearchTool()
    tools = ToolRegistry([search_tool])
    agent = ReActAgent(llm=llm, tools=tools, max_iterations=5)

    result = agent.run("test")
    # First search executed, second skipped (dedup), third is stop
    assert len(search_tool.calls) == 1


def test_react_agent_handles_llm_failure():
    """ReAct agent handles LLM exceptions gracefully."""
    class FailingLLM:
        def complete(self, prompt):
            raise Exception("LLM unavailable")

    tools = ToolRegistry([FakeSearchTool()])
    agent = ReActAgent(llm=FailingLLM(), tools=tools, max_iterations=5)

    result = agent.run("test")
    assert len(result.errors) > 0
    assert result.iterations >= 1
    assert "LLM unavailable" in result.errors[0]


def test_extract_action_json_raw():
    """Parse raw JSON action."""
    text = '{"reasoning": "test", "action": "search", "tool": "t", "input": {"query": "q"}}'
    result = _extract_action_json(text)
    assert result["action"] == "search"
    assert result["input"]["query"] == "q"


def test_extract_action_json_fenced():
    """Parse fenced JSON action."""
    text = 'Some text\n```json\n{"reasoning": "r", "action": "fetch", "tool": "f", "input": {"url": "http://x.com"}}\n```\nMore text'
    result = _extract_action_json(text)
    assert result["action"] == "fetch"
    assert result["input"]["url"] == "http://x.com"


def test_extract_action_json_invalid():
    """Invalid JSON returns empty dict."""
    result = _extract_action_json("just some random text")
    assert result == {}


def test_build_react_system_prompt():
    """System prompt includes question and tool catalog."""
    registry = ToolRegistry([FakeSearchTool()])
    prompt = build_react_system_prompt(registry, "What is AI?")
    assert "What is AI?" in prompt
    assert "tavily_search" in prompt
    assert "Search the web" in prompt
