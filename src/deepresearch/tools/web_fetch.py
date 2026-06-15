"""Web fetch tool — downloads and extracts the text content of a URL."""

from __future__ import annotations

import re

from deepresearch.tools.base import Tool, ToolResult


class WebFetchTool:
    """Fetch and extract the main text content from a web page."""

    name = "web_fetch"
    description = (
        "Fetch and extract the main text content from a given URL. "
        "Use this to read a specific page in full after finding it via search. "
        "Returns the extracted text content (up to 8000 characters)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL of the page to fetch.",
            },
        },
        "required": ["url"],
    }

    def __init__(self, timeout: float = 15.0):
        self._timeout = timeout

    def execute(self, url: str) -> ToolResult:
        # Try httpx first, fall back to urllib
        try:
            import httpx

            response = httpx.get(
                url,
                timeout=self._timeout,
                headers={"User-Agent": "DeepResearchAgent/1.0"},
                follow_redirects=True,
            )
            response.raise_for_status()
            html = response.text
        except ImportError:
            try:
                from urllib.request import Request, urlopen

                req = Request(url, headers={"User-Agent": "DeepResearchAgent/1.0"})
                with urlopen(req, timeout=self._timeout) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
            except Exception as exc:
                return ToolResult(error=f"Failed to fetch {url}: {exc}")
        except Exception as exc:
            return ToolResult(error=f"Failed to fetch {url}: {exc}")

        # Extract text
        text = self._extract_text(html)
        if not text.strip():
            return ToolResult(content=f"(No extractable text content from {url})")

        # Truncate
        if len(text) > 8000:
            text = text[:8000] + "\n\n... (truncated)"

        return ToolResult(
            content=text,
            urls=[url],
            metadata={"char_count": len(text)},
        )

    @staticmethod
    def _extract_text(html: str) -> str:
        """Extract readable text from HTML, removing scripts, styles, and tags."""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        # Decode common entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        return text.strip()
