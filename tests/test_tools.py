"""Tests for tool system."""

from deepresearch.tools.base import ToolResult
from deepresearch.tools.registry import ToolRegistry
from deepresearch.tools.web_fetch import WebFetchTool


class FakeTool:
    name = "fake_tool"
    description = "A fake tool for testing."
    parameters = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}

    def __init__(self):
        self.calls: list[dict] = []

    def execute(self, x: int) -> ToolResult:
        self.calls.append({"x": x})
        return ToolResult(content=f"Result: {x}", metadata={"x": x})


class FailingTool:
    name = "failing_tool"
    description = "Always fails."
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> ToolResult:
        raise RuntimeError("Intentional failure")


def test_tool_registry_register_and_get():
    """Tools can be registered and looked up."""
    registry = ToolRegistry()
    tool = FakeTool()
    registry.register(tool)
    assert registry.get("fake_tool") is tool
    assert registry.get("nonexistent") is None


def test_tool_registry_execute():
    """Registry.execute calls the tool and returns result."""
    registry = ToolRegistry([FakeTool()])
    result = registry.execute("fake_tool", x=42)
    assert result.content == "Result: 42"
    assert result.metadata["x"] == 42


def test_tool_registry_unknown_tool():
    """Registry.execute returns error for unknown tools."""
    registry = ToolRegistry()
    result = registry.execute("nonexistent")
    assert result.error
    assert "Unknown tool" in result.error


def test_tool_registry_handles_tool_failure():
    """Registry.execute catches tool exceptions."""
    registry = ToolRegistry([FailingTool()])
    result = registry.execute("failing_tool")
    assert result.error
    assert "Intentional failure" in result.error


def test_tool_registry_describe_tools():
    """describe_tools generates the tool catalog text."""
    registry = ToolRegistry([FakeTool()])
    desc = registry.describe_tools()
    assert "fake_tool" in desc
    assert "A fake tool" in desc


def test_web_fetch_extracts_text():
    """WebFetchTool extracts text from HTML."""
    tool = WebFetchTool()
    html = "<html><body><h1>Hello</h1><p>World</p><script>alert('x')</script></body></html>"
    text = tool._extract_text(html)
    assert "Hello" in text
    assert "World" in text
    assert "alert" not in text


def test_web_fetch_handles_entities():
    """WebFetchTool decodes HTML entities."""
    tool = WebFetchTool()
    html = "<p>Hello &amp; welcome to &#39;Research&#39;</p>"
    text = tool._extract_text(html)
    assert "&" in text
    assert "'Research'" in text
