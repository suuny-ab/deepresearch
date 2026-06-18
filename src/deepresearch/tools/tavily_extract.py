"""Tavily extract tool — fetches full page content via Tavily's API.

Tavily's extract endpoint handles JS rendering, paywalls, and anti-bot
measures that raw HTTP fetch cannot.  Returns clean markdown content.
"""

from __future__ import annotations

from deepresearch.tools.base import ToolResult


class TavilyExtractTool:
    """Fetch full page content using Tavily's extract API.

    Unlike raw HTTP fetch, Tavily's extract handles JavaScript rendering
    and provides clean markdown output.  Requires a search client that
    supports the ``extract()`` method.
    """

    name = "tavily_extract"
    description = (
        "Fetch the full content of one or more URLs using Tavily's extraction API. "
        "Returns clean markdown text (up to 4000 chars per URL). "
        "Use this to read a specific page in full after finding it via search. "
        "Prefer this over web_fetch for news articles and complex pages."
    )
    parameters = {
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "One or more URLs to extract full content from (max 3).",
                "minItems": 1,
                "maxItems": 3,
            },
        },
        "required": ["urls"],
    }

    def __init__(self, search_client=None):
        self._client = search_client

    def execute(self, urls: list[str]) -> ToolResult:
        if self._client is None:
            return ToolResult(error="No search client available for extraction")

        try:
            sources = self._client.extract(
                urls[:3], subquestion_id="extract",
            )
        except Exception as exc:
            return ToolResult(error=f"Tavily extract failed: {exc}")

        if not sources:
            return ToolResult(content="(No extractable content from these URLs)")

        lines = []
        all_urls = []
        for s in sources:
            lines.append(f"### {s.title}")
            lines.append(f"URL: {s.url}")
            lines.append("")
            content = s.raw_content[:4000] if s.raw_content else "(empty)"
            lines.append(content)
            lines.append("")
            all_urls.append(s.url)

        return ToolResult(
            content="\n".join(lines),
            urls=all_urls,
            metadata={"count": len(sources)},
        )
