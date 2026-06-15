"""Tool Protocol — the interface every tool must satisfy.

Tools are what give an Agent its capabilities.  Each tool:
- Has a **name** (unique identifier used in the ReAct action JSON)
- Has a **description** (the LLM reads this to decide *when* to use the tool)
- Has a **parameter schema** (JSON Schema — the LLM uses this to know *how* to call it)
- Is **callable** — ``execute(**kwargs) -> ToolResult``

This is deliberately minimal.  A tool doesn't know about the Agent or the
conversation context — it just does one thing and returns structured output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolResult:
    """Structured output from a tool execution."""
    content: str = ""
    urls: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class Tool(Protocol):
    """Protocol that every tool must implement."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema

    def execute(self, **kwargs: Any) -> ToolResult:
        """Run the tool with the given keyword arguments."""
        ...
