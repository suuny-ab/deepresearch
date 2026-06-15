"""ReAct (Reasoning + Acting) research agent with tool-calling loop.

Unlike the fixed-pipeline agent, the ReAct agent autonomously decides:
- When to search vs. when to fetch a page
- When it has enough information to write the report
- When to stop (information saturation or iteration limit)

Key constraints:
- ``max_iterations``: prevents infinite loops (default 15)
- Search deduplication: re-searching the same query returns cached results
- Saturation detection: if 2 consecutive rounds yield no new information, stop
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from deepresearch.agents.coordinator import coordinate
from deepresearch.agents.subquestion_agent import AgentResult
from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.writing import build_writing_prompt
from deepresearch.state import (
    EvidenceCard, ExtractedClaim, SearchResult, SubQuestion, TokenUsage,
)
from deepresearch.tools.base import ToolResult
from deepresearch.tools.registry import ToolRegistry


@dataclass
class ReActStep:
    """One iteration of the ReAct loop."""
    iteration: int
    reasoning: str = ""
    action: str = ""  # search | fetch | write_report | stop
    action_input: dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    new_urls: list[str] = field(default_factory=list)


@dataclass
class ReActResult:
    """Output from a ReAct agent run."""
    report: str = ""
    evidence_cards: list[EvidenceCard] = field(default_factory=list)
    search_results: list[SearchResult] = field(default_factory=list)
    steps: list[ReActStep] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    token_usage: list[TokenUsage] = field(default_factory=list)
    iterations: int = 0


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_react_system_prompt(registry: ToolRegistry, question: str) -> str:
    """Build the ReAct agent's system prompt with tool catalog."""
    tool_desc = registry.describe_tools()
    return f"""You are an autonomous research agent. Your task is to research the following question thoroughly and then write a comprehensive report.

## Research Question
{question}

## Available Tools
{tool_desc}

## Available Actions

Respond in JSON with exactly one action per turn:

### search
Search the web for information.
```json
{{"reasoning": "I need to find information about X...", "action": "search", "tool": "tavily_search", "input": {{"query": "your search query", "max_results": 5}}}}
```

### fetch
Fetch and read a specific web page in full.
```json
{{"reasoning": "This result looks promising, let me read it...", "action": "fetch", "tool": "web_fetch", "input": {{"url": "https://..."}}}}
```

### write_report
When you have gathered sufficient information, write the final report.
```json
{{"reasoning": "I have enough information to answer the question...", "action": "write_report"}}
```

### stop
If you cannot find any useful information after several attempts, stop.
```json
{{"reasoning": "Multiple searches yielded no useful results...", "action": "stop"}}
```

## Research Guidelines
- Start with a broad search, then narrow down based on what you find
- Fetch at least 2-3 promising pages to get detailed information
- Look for information from diverse, independent sources
- When sources disagree, note the disagreement rather than choosing sides
- You have a maximum of 15 iterations — use them wisely
- If you have enough information to write a good report, do it — don't keep searching
- If 2 consecutive searches return substantially the same information, you have saturation — write the report

## Output Format
Respond ONLY with a JSON object containing "reasoning", "action", and optionally "tool" and "input".
"""  # noqa: E501


def build_react_step_prompt(
    question: str,
    iteration: int,
    max_iterations: int,
    previous_steps: list[ReActStep],
    collected_urls: list[str],
    collected_findings: str,
) -> str:
    """Build the prompt for one ReAct iteration."""
    steps_text = ""
    if previous_steps:
        steps_text = "\n## Previous Steps\n\n"
        for step in previous_steps[-4:]:  # Last 4 steps for context
            steps_text += f"### Iteration {step.iteration}\n"
            steps_text += f"Action: {step.action}\n"
            if step.action_input:
                steps_text += f"Input: {json.dumps(step.action_input)}\n"
            if step.observation:
                # Truncate long observations
                obs = step.observation
                if len(obs) > 600:
                    obs = obs[:600] + "..."
                steps_text += f"Observation: {obs}\n"
            steps_text += "\n"

    urls_text = ""
    if collected_urls:
        urls_text = f"\n## URLs Collected So Far ({len(collected_urls)})\n"
        for url in collected_urls[-10:]:
            urls_text += f"- {url}\n"

    findings_text = ""
    if collected_findings:
        findings_text = f"\n## Key Findings So Far\n{collected_findings[:2000]}\n"

    return f"""## Current State
Iteration: {iteration}/{max_iterations}
{urls_text}
{findings_text}
{steps_text}
## Instruction
Decide your next action. If you have enough information to answer the research question, write the report.
Respond with a JSON object containing "reasoning" and "action" keys.
Remember: iteration {iteration} of {max_iterations}."""


# ---------------------------------------------------------------------------
# JSON extraction for ReAct action parsing
# ---------------------------------------------------------------------------

def _extract_action_json(text: str) -> dict[str, Any]:
    """Extract the ReAct action JSON from LLM output."""
    # Try raw JSON first
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    # Try fenced code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try to find the first JSON object
    match = re.search(r"\{[^{}]*\"action\"[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


# ---------------------------------------------------------------------------
# ReAct Agent
# ---------------------------------------------------------------------------

class ReActAgent:
    """Autonomous research agent using the ReAct pattern.

    The agent loops: observe → think → act → observe → ...
    It uses a tool registry for search and fetch capabilities,
    and decides autonomously when to write the final report.
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        *,
        max_iterations: int = 15,
    ):
        self._llm = llm
        self._tools = tools
        self._max_iterations = max_iterations

    def run(self, question: str) -> ReActResult:
        """Execute the ReAct loop and return the final result."""
        errors: list[str] = []
        usage: list[TokenUsage] = []
        steps: list[ReActStep] = []
        collected_urls: list[str] = []
        search_results: list[SearchResult] = []
        # Store findings as raw tool output strings
        findings_buffer: list[str] = []
        # Track search queries to avoid duplicates
        searched_queries: set[str] = set()
        # Track consecutive rounds with no new information
        dry_rounds = 0

        system_prompt = build_react_system_prompt(self._tools, question)

        for iteration in range(1, self._max_iterations + 1):
            # Build step prompt
            step_prompt = build_react_step_prompt(
                question=question,
                iteration=iteration,
                max_iterations=self._max_iterations,
                previous_steps=steps,
                collected_urls=collected_urls,
                collected_findings="\n".join(findings_buffer[-5:]),
            )

            full_prompt = system_prompt + "\n\n" + step_prompt

            # Get action from LLM
            try:
                text, llm_usage = self._llm.complete(full_prompt)
                usage.append(TokenUsage(
                    node="react_agent",
                    prompt_tokens=llm_usage.prompt_tokens,
                    completion_tokens=llm_usage.completion_tokens,
                    estimated_cost=llm_usage.estimated_cost,
                ))
            except Exception as exc:
                errors.append(f"ReAct iteration {iteration} LLM call failed: {exc}")
                break

            action_data = _extract_action_json(text)
            if not action_data:
                errors.append(f"ReAct iteration {iteration}: could not parse action JSON from: {text[:200]}")
                # Default to searching the original question
                action_data = {"reasoning": "JSON parse failed, defaulting to search", "action": "search", "tool": "tavily_search", "input": {"query": question}}

            reasoning = action_data.get("reasoning", "")
            action = action_data.get("action", "stop")
            tool_name = action_data.get("tool", "")
            action_input = action_data.get("input", {})

            step = ReActStep(
                iteration=iteration,
                reasoning=reasoning,
                action=action,
                action_input=action_input,
            )

            # --- Execute action ---
            if action == "search":
                query = action_input.get("query", question)
                max_results = action_input.get("max_results", 5)

                # Dedup check
                normalized_q = query.strip().lower()
                if normalized_q in searched_queries:
                    step.observation = f"(Already searched for '{query}'. Try a different query or fetch some results.)"
                    steps.append(step)
                    dry_rounds += 1
                    if dry_rounds >= 2:
                        action = "write_report"  # Force report writing
                else:
                    searched_queries.add(normalized_q)
                    result = self._tools.execute("tavily_search", query=query, max_results=max_results)
                    if result.error:
                        step.observation = f"Search error: {result.error}"
                        errors.append(result.error)
                    else:
                        step.observation = result.content
                        step.new_urls = result.urls
                        collected_urls.extend(result.urls)
                        findings_buffer.append(result.content)
                        dry_rounds = 0

            elif action == "fetch":
                url = action_input.get("url", "")
                if not url:
                    step.observation = "Error: no URL provided for fetch."
                else:
                    result = self._tools.execute("web_fetch", url=url)
                    if result.error:
                        step.observation = f"Fetch error: {result.error}"
                    else:
                        step.observation = result.content
                        findings_buffer.append(result.content)
                        dry_rounds = 0

            elif action == "write_report" or action == "stop":
                steps.append(step)
                break

            else:
                step.observation = f"Unknown action: {action}. Valid actions: search, fetch, write_report, stop."
                errors.append(step.observation)

            steps.append(step)

            # --- Saturation check ---
            if dry_rounds >= 2:
                errors.append("Two consecutive dry rounds — forcing report generation.")
                action = "write_report"
                break

        # --- Generate final report ---
        if findings_buffer:
            report = self._generate_report(
                question=question,
                findings="\n\n".join(findings_buffer),
                urls=collected_urls,
                errors=errors,
                usage=usage,
            )
        else:
            report = f"# {question}\n\nResearch could not find sufficient information.\n"

        return ReActResult(
            report=report,
            steps=steps,
            errors=errors,
            token_usage=usage,
            iterations=iteration,
        )

    def _generate_report(
        self,
        question: str,
        findings: str,
        urls: list[str],
        errors: list[str],
        usage: list[TokenUsage],
    ) -> str:
        """Generate the final report from collected findings."""
        # Build a simple prompt that asks the LLM to synthesize findings
        prompt = f"""Based on the following research findings, write a comprehensive Markdown report.

## Research Question
{question}

## Collected Research Findings
{findings[:6000]}

## Collected Source URLs
{chr(10).join(f'- {url}' for url in urls[:20])}

## Instructions
- Write in Chinese unless the question uses another language
- Structure the report with: Summary, Key Findings, Detailed Analysis, Uncertainties, Conclusion, Sources
- Use numbered citations [1], [2], etc. for every factual claim
- The Sources section must map [N] to URLs from the collected URLs above
- If findings are insufficient for certain aspects, honestly state the limitations

Return ONLY the Markdown report, no JSON wrapper."""

        try:
            text, llm_usage = self._llm.complete(prompt)
            usage.append(TokenUsage(
                node="react_agent",
                prompt_tokens=llm_usage.prompt_tokens,
                completion_tokens=llm_usage.completion_tokens,
                estimated_cost=llm_usage.estimated_cost,
            ))
            return text
        except Exception as exc:
            errors.append(f"Report generation failed: {exc}")
            return f"# {question}\n\nReport generation failed: {exc}\n\n## Raw Findings\n\n{findings[:2000]}"
