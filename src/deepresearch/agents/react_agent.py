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
from deepresearch.citations import validate_citations
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
            # Guard: LLM sometimes returns input as a string instead of a dict
            if isinstance(action_input, str):
                action_input = {"query": action_input} if action == "search" else {"url": action_input}

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
        """Generate the final report via Option C: findings → evidence_cards → write → validate.

        Uses the same build_writing_prompt() + validate_citations() + rewrite
        pipeline as Pipeline/Multi-Agent, ensuring citation format consistency.
        """
        # Step 1: Convert findings to evidence_cards (Option C — 1 LLM call)
        cards, cards_usage = self._findings_to_evidence_cards(findings, urls, errors)
        if cards_usage.prompt_tokens > 0:
            usage.append(TokenUsage(
                node="react_agent",
                prompt_tokens=cards_usage.prompt_tokens,
                completion_tokens=cards_usage.completion_tokens,
                estimated_cost=cards_usage.estimated_cost,
            ))

        allowed_urls = set(urls)
        # Add URLs from evidence cards
        for card in cards:
            allowed_urls.add(card.source_url)
            for cs in card.corroborating_sources:
                allowed_urls.add(cs)

        # Step 2: Build the writing prompt using the standard pipeline function
        from deepresearch.state import SubQuestion
        # Build a synthetic subquestion for the prompt builder
        synth_sq = SubQuestion(
            id="react", question=question, search_query=question,
            search_queries=[question], rationale="ReAct autonomous research",
        )

        prompt = build_writing_prompt(
            question=question,
            subquestions=[synth_sq],
            results=[],  # Empty — evidence_cards provide the source context
            evidence_cards=cards,
            allowed_source_urls=allowed_urls,
            review_feedback=None,
        )

        # Step 3: Write the report
        try:
            report_text, w_usage = self._llm.complete(prompt)
            usage.append(TokenUsage(
                node="react_agent",
                prompt_tokens=w_usage.prompt_tokens,
                completion_tokens=w_usage.completion_tokens,
                estimated_cost=w_usage.estimated_cost,
            ))
        except Exception as exc:
            errors.append(f"Report generation failed: {exc}")
            return f"# {question}\n\nReport generation failed: {exc}\n\n## Raw Findings\n\n{findings[:2000]}"

        # Step 4: Validate citations
        validation = validate_citations(report_text, allowed_urls)
        if validation.passed:
            return report_text

        # Step 5: One rewrite on citation failure
        errors.append(
            f"React report citation validation failed: {validation.reason}: {validation.message}"
        )
        rewrite_prompt = build_writing_prompt(
            question=question,
            subquestions=[synth_sq],
            results=[],
            evidence_cards=cards,
            allowed_source_urls=allowed_urls,
            review_feedback=(
                f"Previous version failed citation validation. "
                f"Reason: {validation.reason}. {validation.message}. "
                f"Ensure every [N] citation in the body maps to a URL in ## Sources, "
                f"and every URL in ## Sources comes from the allowed list."
            ),
        )
        try:
            rewritten, rw_usage = self._llm.complete(rewrite_prompt)
            usage.append(TokenUsage(
                node="react_agent",
                prompt_tokens=rw_usage.prompt_tokens,
                completion_tokens=rw_usage.completion_tokens,
                estimated_cost=rw_usage.estimated_cost,
            ))
            second = validate_citations(rewritten, allowed_urls)
            if second.passed:
                return rewritten
            errors.append(
                f"React report rewrite also failed validation: {second.reason}: {second.message}"
            )
            return rewritten  # Return the rewrite even if it still fails
        except Exception as exc:
            errors.append(f"React report rewrite failed: {exc}")
            return report_text  # Fall back to original

    def _findings_to_evidence_cards(
        self,
        findings: str,
        urls: list[str],
        errors: list[str],
    ) -> tuple[list, TokenUsage]:
        """Option C: Convert search findings into evidence_cards (1 LLM call).

        Takes the raw findings_buffer (search snippets + fetched content)
        and produces structured evidence_cards with corroboration_level
        estimated from finding overlap and domain diversity.
        """
        from deepresearch.state import EvidenceCard, UsageInfo

        url_list = "\n".join(f"- {url}" for url in urls[:30])
        prompt = f"""You are converting research findings into structured evidence cards.

## Collected URLs
{url_list}

## Research Findings (search snippets and fetched content)
{findings[:8000]}

## Task
For each distinct factual finding, create an evidence card.
Estimate corroboration level based on whether multiple independent sources (different domains) report the same fact:
- "strongly_corroborated": ≥2 other sources from different domains independently report this
- "weakly_corroborated": 1 other source from a different domain reports this
- "single_source": only one source mentions this

Be conservative — only mark as corroborated when the same specific fact appears in multiple sources.

Return ONLY this JSON (no markdown, no explanation):
{{"evidence_cards": [
  {{"id": "c1", "subquestion_id": "react", "claim": "factual claim text",
    "source_url": "https://...", "source_title": "Source Title",
    "supporting_snippet": "relevant excerpt from findings",
    "content_type": "search_content",
    "corroboration_level": "single_source|weakly_corroborated|strongly_corroborated",
    "corroborating_sources": ["https://other-source"], "confidence": "high|medium|low"
  }}
]}}"""

        try:
            text, usage = self._llm.complete(prompt)
        except Exception as exc:
            errors.append(f"Option C evidence card extraction failed: {exc}")
            return [], UsageInfo()

        # Parse JSON
        import json, re
        try:
            data = None
            text = text.strip()
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
        except (json.JSONDecodeError, AttributeError):
            errors.append("Option C: failed to parse evidence_cards JSON")
            return [], usage

        raw_cards = data.get("evidence_cards", []) if data else []
        cards = []
        for rc in raw_cards:
            try:
                cards.append(EvidenceCard(
                    id=str(rc.get("id", "")),
                    subquestion_id="react",
                    claim=str(rc.get("claim", "")),
                    source_url=str(rc.get("source_url", "")),
                    source_title=str(rc.get("source_title", "")),
                    supporting_snippet=str(rc.get("supporting_snippet", "")),
                    content_type="search_content",
                    corroboration_level=str(rc.get("corroboration_level", "single_source")),
                    corroborating_sources=list(rc.get("corroborating_sources", [])),
                    confidence=str(rc.get("confidence", "medium")),
                ))
            except Exception:
                pass

        return cards, usage
