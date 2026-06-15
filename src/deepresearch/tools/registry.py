"""Tool registry — manages the tool catalog available to an Agent."""

from __future__ import annotations

from deepresearch.tools.base import Tool, ToolResult


class ToolRegistry:
    """Container for tools that an Agent can use.

    Provides lookup by name and generates the tool-description text
    that the ReAct Agent's system prompt uses to decide which tool to call.
    """

    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: Tool) -> None:
        """Add a tool to the registry."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Look up a tool by name."""
        return self._tools.get(name)

    def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool by name, returning its result or an error."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(error=f"Unknown tool: {name}. Available: {sorted(self._tools.keys())}")
        try:
            return tool.execute(**kwargs)
        except Exception as exc:
            return ToolResult(error=f"Tool '{name}' failed: {exc}")

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def describe_tools(self) -> str:
        """Generate the tool-catalog text for the Agent's system prompt."""
        if not self._tools:
            return "No tools available."

        lines = ["Available tools:"]
        for name in sorted(self._tools):
            tool = self._tools[name]
            lines.append(f"\n## {name}")
            lines.append(f"Description: {tool.description}")
            lines.append(f"Parameters: {tool.parameters}")
        return "\n".join(lines)
