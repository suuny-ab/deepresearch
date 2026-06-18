"""Compare sources tool — cross-validates claims across multiple URLs."""

from __future__ import annotations

from deepresearch.tools.base import ToolResult


class CompareSourcesTool:
    """Fetch and compare multiple sources on a specific topic.

    Fetches up to 3 URLs, then calls the LLM to analyze where the sources
    agree, conflict, and which is more authoritative on a given claim.
    """

    name = "compare_sources"
    description = (
        "Fetch 2-3 URLs and compare their claims on a specific topic. "
        "Identifies areas of agreement, conflict, and relative authority. "
        "Use this when you have multiple sources and want to cross-validate a claim."
    )
    parameters = {
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-3 URLs to fetch and compare.",
                "minItems": 2,
                "maxItems": 3,
            },
            "topic": {
                "type": "string",
                "description": "The specific topic or claim to compare across sources.",
            },
        },
        "required": ["urls", "topic"],
    }

    def __init__(self, llm=None, timeout: float = 15.0):
        self._llm = llm
        self._timeout = timeout

    def execute(self, urls: list[str], topic: str) -> ToolResult:
        # --- Fetch all URLs ---
        contents: list[dict] = []
        for url in urls[:3]:
            text = self._fetch(url)
            if text:
                contents.append({"url": url, "text": text[:2000]})
            else:
                contents.append({"url": url, "text": "(Failed to fetch)"})

        if not any(c["text"] and "(Failed" not in c["text"] for c in contents):
            return ToolResult(error="Could not fetch any of the provided URLs.")

        # --- LLM comparison ---
        if self._llm is not None:
            return self._llm_compare(topic, contents)
        else:
            return self._simple_compare(topic, contents)

    def _fetch(self, url: str) -> str:
        """Fetch URL content — mirrors WebFetchTool pattern."""
        try:
            import httpx
            response = httpx.get(
                url, timeout=self._timeout,
                headers={"User-Agent": "DeepResearchAgent/1.0"},
                follow_redirects=True,
            )
            response.raise_for_status()
            return self._extract_text(response.text)
        except Exception:
            try:
                from urllib.request import Request, urlopen
                req = Request(url, headers={"User-Agent": "DeepResearchAgent/1.0"})
                with urlopen(req, timeout=self._timeout) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
                return self._extract_text(html)
            except Exception:
                return ""

    @staticmethod
    def _extract_text(html: str) -> str:
        import re
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        text = text.strip()
        return text[:4000] if len(text) > 4000 else text

    def _llm_compare(self, topic: str, contents: list[dict]) -> ToolResult:
        """Use LLM to produce a structured comparison."""
        sources_text = ""
        for i, c in enumerate(contents, 1):
            sources_text += f"\n### Source {i}: {c['url']}\n{c['text'][:1500]}\n"

        prompt = f"""Compare these sources on the following topic.

## Topic
{topic}

## Sources
{sources_text}

Return JSON ONLY:
{{"agreement": "What these sources agree on (or 'No clear agreement')",
 "conflicts": ["Specific point of disagreement", "..."],
 "most_authoritative": "URL of the most authoritative source on this topic",
 "summary": "1-paragraph synthesis of what these sources collectively say about the topic"
}}"""

        try:
            import json
            import re
            text, _usage = self._llm.complete(prompt)
            text = text.strip()
            data = None
            if text.startswith("{"):
                data = json.loads(text)
            else:
                m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
                if m:
                    data = json.loads(m.group(1))
            if not data:
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    data = json.loads(m.group(0))
        except Exception:
            return self._simple_compare(topic, contents)

        if data is None:
            return self._simple_compare(topic, contents)

        agreement = data.get("agreement", "No analysis available")
        conflicts = data.get("conflicts", [])
        authoritative = data.get("most_authoritative", "")
        summary = data.get("summary", "")

        conflict_text = "\n".join(f"- {c}" for c in conflicts) if conflicts else "- None detected"
        result = (
            f"## Source Comparison: {topic}\n\n"
            f"**Most authoritative**: {authoritative}\n\n"
            f"### Agreement\n{agreement}\n\n"
            f"### Conflicts\n{conflict_text}\n\n"
            f"### Synthesis\n{summary}"
        )
        return ToolResult(content=result, urls=[c["url"] for c in contents])

    def _simple_compare(self, topic: str, contents: list[dict]) -> ToolResult:
        """Fallback comparison without LLM."""
        lines = [f"## Source Comparison: {topic}\n"]
        for i, c in enumerate(contents, 1):
            lines.append(f"### Source {i}: {c['url']}")
            lines.append(c["text"][:500])
            lines.append("")
        return ToolResult(
            content="\n".join(lines),
            urls=[c["url"] for c in contents],
        )
