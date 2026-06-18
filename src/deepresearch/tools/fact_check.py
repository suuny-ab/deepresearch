"""Fact-check tool — verifies a claim against web search results."""

from __future__ import annotations

from deepresearch.tools.base import ToolResult


class FactCheckTool:
    """Check a factual claim by searching for corroborating and refuting evidence.

    Searches the web for the claim, then evaluates whether the search results
    support, refute, or are inconclusive about the claim.
    """

    name = "fact_check"
    description = (
        "Verify a factual claim by searching for supporting and opposing evidence. "
        "Returns a structured assessment: supported, refuted, or inconclusive. "
        "Use this when you encounter a claim that needs verification before inclusion."
    )
    parameters = {
        "type": "object",
        "properties": {
            "claim": {
                "type": "string",
                "description": "The factual claim to verify (1-2 sentences).",
            },
        },
        "required": ["claim"],
    }

    def __init__(self, search_client=None, llm=None):
        self._search = search_client
        self._llm = llm

    def execute(self, claim: str) -> ToolResult:
        if self._search is None:
            return ToolResult(
                content=f"## Fact Check\n\n**Claim**: {claim}\n\n"
                         "Status: UNCHECKED (no search client available)\n\n"
                         "Cannot verify without search access.",
            )

        # --- Search for supporting evidence ---
        try:
            support_results = self._search.search(
                claim, subquestion_id="fact_check", max_results=3,
            )
        except Exception as exc:
            return ToolResult(error=f"Fact-check search failed: {exc}")

        # --- Search for opposing evidence ---
        opposing_query = f"debunked {claim}" if len(claim) < 80 else f"criticism {claim[:80]}"
        try:
            opposing_results = self._search.search(
                opposing_query, subquestion_id="fact_check", max_results=3,
            )
        except Exception:
            opposing_results = []

        # --- Format results ---
        support_urls = [r.url for r in support_results]
        oppose_urls = [r.url for r in opposing_results] if opposing_results else []

        support_snippets = "\n".join(
            f"- [{r.title}]({r.url}): {r.content[:200]}" for r in support_results
        ) if support_results else "- No supporting evidence found"

        oppose_snippets = "\n".join(
            f"- [{r.title}]({r.url}): {r.content[:200]}" for r in opposing_results
        ) if opposing_results else "- No opposing evidence found"

        # --- Simple heuristic assessment ---
        has_support = len(support_results) >= 1
        has_oppose = len(opposing_results) >= 1

        if has_support and not has_oppose:
            verdict = "LIKELY SUPPORTED — supporting evidence found, no clear opposition"
        elif has_oppose and not has_support:
            verdict = "LIKELY REFUTED — opposing evidence found, no clear support"
        elif has_support and has_oppose:
            verdict = "DISPUTED — both supporting and opposing evidence exist"
        else:
            verdict = "INCONCLUSIVE — insufficient evidence either way"

        result = (
            f"## Fact Check\n\n"
            f"**Claim**: {claim}\n\n"
            f"**Verdict**: {verdict}\n\n"
            f"### Supporting Evidence\n{support_snippets}\n\n"
            f"### Opposing Evidence\n{oppose_snippets}"
        )

        return ToolResult(
            content=result,
            urls=support_urls + oppose_urls,
            metadata={
                "verdict": verdict,
                "support_count": len(support_results),
                "oppose_count": len(opposing_results),
            },
        )
