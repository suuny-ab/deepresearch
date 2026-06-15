"""Tavily search tool — wraps the existing TavilySearchClient."""

from __future__ import annotations

from deepresearch.clients.tavily import SearchClient
from deepresearch.tools.base import Tool, ToolResult


class TavilySearchTool:
    """Search the web via Tavily API."""

    name = "tavily_search"
    description = (
        "Search the web for recent information using the Tavily search engine. "
        "Best for current events, factual lookups, and finding diverse sources. "
        "Returns titles, URLs, and content snippets."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Use specific, keyword-rich queries for best results.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def __init__(self, search_client: SearchClient):
        self._client = search_client

    def execute(self, query: str, max_results: int = 5) -> ToolResult:
        try:
            results = self._client.search(
                query,
                subquestion_id="react",
                max_results=max_results,
            )
        except Exception as exc:
            return ToolResult(error=f"Tavily search failed: {exc}")

        if not results:
            return ToolResult(content="No results found for this query.")

        lines = []
        urls = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.title}**")
            lines.append(f"   URL: {r.url}")
            if r.content:
                lines.append(f"   {r.content[:300]}")
            lines.append("")
            urls.append(r.url)

        return ToolResult(
            content="\n".join(lines),
            urls=urls,
            metadata={"count": len(results)},
        )
