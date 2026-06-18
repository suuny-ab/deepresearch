"""ReAct Agent V3: Agent owns its workspace — no external reflection.

Key difference from V2:
- Agent has a unified action space: search, set_topic, add_topic, synthesize.
- The Agent manages its own Workspace (topics + notes) — no separate
  reflection step, no external state manipulation.
- Topic assignment is explicit (topic_id in action JSON), not guessed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterator, Literal

from pydantic import BaseModel

from deepresearch.citations import validate_citations
from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.writing import build_writing_prompt
from deepresearch.state import (
    EvidenceCard,
    SearchResult,
    SubQuestion,
    TokenUsage,
    UsageInfo,
)
from deepresearch.tools.base import ToolResult
from deepresearch.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Data model — the Agent's workspace
# ---------------------------------------------------------------------------


@dataclass
class TopicState:
    """One research direction.  Fully managed by the Agent via actions."""

    id: str
    topic: str
    status: Literal["active", "saturated", "abandoned"] = "active"
    findings_summary: str = ""
    open_questions: list[str] = field(default_factory=list)
    resolved_questions: list[str] = field(default_factory=list)


@dataclass
class ResearchNote:
    """A finding from a search, tagged to a topic by the Agent."""

    topic_id: str
    content: str
    source_url: str
    source_title: str


@dataclass
class Workspace:
    """Mutable research state — the Agent reads and writes this."""

    topics: list[TopicState] = field(default_factory=list)
    notes: list[ResearchNote] = field(default_factory=list)

    def topic_by_id(self, tid: str) -> TopicState | None:
        for t in self.topics:
            if t.id == tid:
                return t
        return None

    def format_for_prompt(self) -> str:
        """Render the workspace as a string for the action prompt."""
        badge = {"active": "🔍", "saturated": "✅", "abandoned": "❌"}
        lines = []
        for t in self.topics:
            b = badge.get(t.status, "🔍")
            notes_for_topic = [n for n in self.notes if n.topic_id == t.id]
            lines.append(
                f"  {b} **{t.id}**: {t.topic} ({t.status}) — "
                f"{len(notes_for_topic)} notes"
            )
            if t.findings_summary:
                lines.append(f"     Summary: {t.findings_summary}")
            # Show question pool
            open_qs = t.open_questions
            resolved_qs = t.resolved_questions
            if open_qs:
                lines.append(f"     📋 Open questions ({len(open_qs)}):")
                for i, q in enumerate(open_qs):
                    lines.append(f"        [{i}] {q}")
            if resolved_qs:
                lines.append(f"     ✅ Resolved questions ({len(resolved_qs)}):")
                for q in resolved_qs[-3:]:  # show last 3 to avoid bloat
                    lines.append(f"        ✓ {q}")
        return "\n".join(lines) if lines else "  (empty)"


@dataclass
class AgentStep:
    """One iteration of the research loop."""

    iteration: int
    action: str
    reasoning: str = ""
    detail: str = ""
    new_urls: list[str] = field(default_factory=list)


@dataclass
class AgentResult:
    """Output from a complete run."""

    report: str = ""
    steps: list[AgentStep] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    token_usage: list[TokenUsage] = field(default_factory=list)
    iterations: int = 0


# ---------------------------------------------------------------------------
# Pydantic models for LLM JSON parsing
# ---------------------------------------------------------------------------


class _PlanResponse(BaseModel):
    summary: str = ""
    topics: list[dict] = []


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def build_plan_prompt(question: str) -> str:
    """Initial research direction — 2-3 starting angles, with open questions."""
    return f"""You are setting an initial research DIRECTION.

## Research Question
{question}

## Task
1. Suggest 2-3 starting angles
2. For EACH angle, list 2-3 open questions that need to be answered to fully cover it
   - Be specific and answerable via web search
   - Include questions about different perspectives, latest data, counter-evidence
3. NO search queries — you will generate those during research

Return JSON ONLY:
{{"summary": "一句话研究策略（中文）",
 "topics": [
   {{"id": "t1", "topic": "方向标签（中文）",
    "open_questions": ["具体问题1？", "具体问题2？"]}}
 ]}}"""


def build_action_prompt(
    question: str,
    workspace: Workspace,
    iteration: int,
    max_iterations: int,
    recent_steps: list[AgentStep],
) -> str:
    """Prompt the Agent to choose its next action based on current workspace state."""
    # Recent history
    steps_text = ""
    for s in recent_steps[-5:]:
        steps_text += f"  [{s.action}] {s.reasoning[:150]}\n"
    if not steps_text:
        steps_text = "  (no steps yet)\n"

    return f"""## Research Question
{question}

## Your Workspace
{workspace.format_for_prompt()}

## Recent Actions
{steps_text}
## Iteration {iteration}/{max_iterations}

## Available Actions

1. **search** — Web search. MUST include topic_id. After searching, report which
   open questions were answered (by index) and any NEW questions discovered.
```json
{{"reasoning": "中文推理", "action": "search", "topic_id": "t1",
 "input": {{"query": "specific search query", "max_results": 10}},
 "resolved_questions": [0, 2],
 "new_questions": ["新发现的问题？"]}}
```

2. **synthesize** — Write the final report when ALL topics have no open questions
   remaining. Only synthesize when the question pool is truly empty.
```json
{{"reasoning": "中文推理", "action": "synthesize"}}
```

## Critical Rules
- Every search MUST report resolved_questions (list of indices from the topic's open questions)
- If no questions were resolved, use an empty list: "resolved_questions": []
- If the search reveals something unexpected, add it as new_questions
- Your GOAL is to empty the question pool — search to answer specific questions
- DO NOT synthesize until ALL topics have zero open questions

REPLY in CHINESE. Respond with JSON ONLY."""


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def _extract_action_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    if text.startswith("["):
        try:
            arr = json.loads(text)
            if isinstance(arr, list) and len(arr) > 0:
                return arr[0]
        except json.JSONDecodeError:
            pass

    # Fenced code block — extract with brace counting for nested objects
    m = re.search(r"```(?:json)?\s*(\{)", text)
    if m:
        start = m.start(1)
        depth = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    # Last resort: find a JSON object with an "action" key
    for m in re.finditer(r"\{", text):
        depth = 0
        start = m.start()
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:i+1]
                    if '"action"' in candidate:
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            pass
                    break
    return {}


def _parse_json_safe(text: str, model_cls: type[BaseModel]) -> dict[str, Any] | None:
    from deepresearch.utils.json import JSONParseError, _extract_json_text

    try:
        raw = _extract_json_text(text)
        data = json.loads(raw)
        return model_cls.model_validate(data).model_dump()
    except (JSONParseError, json.JSONDecodeError, Exception):
        return None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ReActV2Agent:
    """Autonomous research agent — manages its own Workspace via actions."""

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        *,
        max_iterations: int = 15,
        decision_log=None,
    ):
        self._llm = llm
        self._tools = tools
        self._max_iterations = max_iterations
        self._log = decision_log

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, question: str) -> AgentResult:
        """Execute the research pipeline and return a result."""
        errors: list[str] = []
        usage: list[TokenUsage] = []
        steps: list[AgentStep] = []
        report = ""
        iterations = 0

        for event in self.run_stream(question):
            t = event["type"]
            if t == "error":
                errors.append(event["data"]["message"])
            elif t == "step":
                steps.append(AgentStep(
                    iteration=event["data"].get("iteration", 0),
                    action=event["data"].get("action", ""),
                    reasoning=event["data"].get("reasoning", ""),
                    detail=event["data"].get("detail", ""),
                    new_urls=event["data"].get("urls", []),
                ))
            elif t == "done":
                iterations = event["data"].get("iterations", 0)
                r = event["data"].get("report", "")
                if r and not report:
                    report = r

        return AgentResult(
            report=report, steps=steps, errors=errors,
            token_usage=usage, iterations=iterations,
        )

    def run_stream(self, question: str):
        """Execute as a generator, yielding events for SSE streaming."""
        errors: list[str] = []
        usage: list[TokenUsage] = []
        steps: list[AgentStep] = []

        # --- Phase 0: Plan ---
        yield {"type": "phase", "data": {"phase": "plan", "message": "Creating research plan..."}}
        workspace = self._plan(question, steps, usage, errors)
        if workspace is None:
            yield {"type": "error", "data": {"message": "Planning failed"}}
            yield {"type": "done", "data": {"iterations": 0, "token_usage_total": 0}}
            return

        # --- Phase 1: Research Loop ---
        yield {"type": "phase", "data": {"phase": "research", "message": f"Researching {len(workspace.topics)} topics..."}}
        searched_queries: set[str] = set()
        dry_rounds = 0
        iteration = 1

        while iteration <= self._max_iterations:
            # Build prompt from current workspace
            prompt = build_action_prompt(
                question=question, workspace=workspace,
                iteration=iteration, max_iterations=self._max_iterations,
                recent_steps=steps,
            )

            # Get action from LLM
            try:
                text, llm_usage = self._llm.complete(prompt)
                usage.append(TokenUsage(
                    node="react_v3_action",
                    prompt_tokens=llm_usage.prompt_tokens,
                    completion_tokens=llm_usage.completion_tokens,
                    estimated_cost=llm_usage.estimated_cost,
                ))
            except Exception as exc:
                errors.append(f"LLM failed at iter {iteration}: {exc}")
                yield {"type": "error", "data": {"message": str(exc)}}
                break

            action_data = _extract_action_json(text)
            if not action_data:
                action_data = {"reasoning": "JSON parse failed", "action": "synthesize"}

            reasoning = action_data.get("reasoning", "")
            action = action_data.get("action", "synthesize")
            topic_id = action_data.get("topic_id", "")
            inp = action_data.get("input", {})
            if isinstance(inp, str):
                inp = {"query": inp}

            # --- Execute action ---
            if action == "search":
                query = inp.get("query", question)
                max_results = inp.get("max_results", 5)

                norm_q = query.strip().lower()
                if norm_q in searched_queries:
                    yield {
                        "type": "step", "data": {
                            "iteration": iteration, "action": "search",
                            "reasoning": reasoning,
                            "detail": f"Query: {query} (duplicate)",
                        },
                    }
                    steps.append(AgentStep(iteration=iteration, action="search", reasoning=reasoning))
                    dry_rounds += 1
                    iteration += 1
                    if dry_rounds >= 3:
                        errors.append("3 dry rounds — forcing synthesis")
                        break
                    continue

                searched_queries.add(norm_q)
                result = self._tools.execute("tavily_search", query=query, max_results=max_results)

                if result.error:
                    errors.append(result.error)
                    yield {"type": "error", "data": {"message": result.error}}
                    # Count API errors as dry rounds to avoid infinite retries
                    dry_rounds += 1
                elif not result.urls:
                    # Search returned 0 results — don't trust the agent's question claims
                    errors.append(f"Search returned 0 results for: {query}")
                    yield {"type": "error", "data": {"message": f"No results for: {query}"}}
                    dry_rounds += 1
                else:
                    dry_rounds = 0
                    # Ensure topic exists (create if Agent referenced unknown id)
                    if not workspace.topic_by_id(topic_id):
                        topic_id = "general"
                    for url in result.urls:
                        workspace.notes.append(ResearchNote(
                            topic_id=topic_id,
                            content=result.content,
                            source_url=url,
                            source_title="Search result",
                        ))

                    # --- Question pool update ---
                    self._update_question_pool(
                        workspace, topic_id,
                        resolved_indices=action_data.get("resolved_questions", []),
                        new_questions=action_data.get("new_questions", []),
                    )

                    if self._log:
                        self._log.log("action", prompt, text, iteration=iteration,
                                      action="search",
                                      extra={"query": query, "urls_found": len(result.urls),
                                             "observation": result.content})

                # Build detail with question pool info
                resolved_qs = action_data.get("resolved_questions", [])
                new_qs = action_data.get("new_questions", [])
                detail_parts = [f"Query: {query} → {len(result.urls or [])} results → topic {topic_id}"]
                if resolved_qs:
                    detail_parts.append(f"resolved {len(resolved_qs)} questions")
                if new_qs:
                    detail_parts.append(f"+{len(new_qs)} new questions")
                yield {
                    "type": "step", "data": {
                        "iteration": iteration, "action": "search",
                        "reasoning": reasoning,
                        "detail": " | ".join(detail_parts),
                    },
                }
                steps.append(AgentStep(iteration=iteration, action="search", reasoning=reasoning))

            elif action == "set_topic":
                status = inp.get("status", "active")
                summary = inp.get("findings_summary", "")
                topic = workspace.topic_by_id(topic_id)
                if topic:
                    if status in ("active", "saturated", "abandoned"):
                        topic.status = status
                    if summary:
                        topic.findings_summary = summary
                    # Also handle question pool updates if provided
                    self._update_question_pool(
                        workspace, topic_id,
                        resolved_indices=action_data.get("resolved_questions", []),
                        new_questions=action_data.get("new_questions", []),
                    )
                yield {
                    "type": "step", "data": {
                        "iteration": iteration, "action": "set_topic",
                        "reasoning": reasoning,
                        "detail": f"{topic_id} → {status}",
                    },
                }
                steps.append(AgentStep(iteration=iteration, action="set_topic", reasoning=reasoning))
                dry_rounds = 0

            elif action == "add_topic":
                new_topic = inp.get("topic", "New angle")
                new_qs = list(action_data.get("new_questions", []))
                new_id = f"t{len(workspace.topics) + 1}"
                workspace.topics.append(TopicState(
                    id=new_id, topic=new_topic, open_questions=new_qs,
                ))
                yield {
                    "type": "step", "data": {
                        "iteration": iteration, "action": "add_topic",
                        "reasoning": reasoning,
                        "detail": f"Added {new_id}: {new_topic}",
                    },
                }
                steps.append(AgentStep(iteration=iteration, action="add_topic", reasoning=reasoning))
                dry_rounds = 0

            elif action in ("synthesize", "write_report", "stop"):
                if self._log:
                    self._log.log("action", prompt, text, iteration=iteration, action="synthesize")
                yield {
                    "type": "step", "data": {
                        "iteration": iteration, "action": "synthesize",
                        "reasoning": reasoning,
                    },
                }
                steps.append(AgentStep(iteration=iteration, action="synthesize", reasoning=reasoning))
                break

            else:
                errors.append(f"Unknown action: {action}")
                yield {"type": "error", "data": {"message": f"Unknown action: {action}"}}

            # Auto-manage workspace: mark saturated/abandoned heuristically
            changed = self._auto_manage_workspace(workspace)
            if changed and self._log:
                self._log.log("workspace", "", json.dumps([
                    {"id": t.id, "status": t.status, "findings_summary": t.findings_summary}
                    for t in workspace.topics
                ]), iteration=iteration, action="auto_manage",
                extra={"changed_topics": changed})

            iteration += 1

        # --- Phase 2: Synthesize ---
        yield {"type": "phase", "data": {"phase": "synthesize", "message": "Writing report..."}}
        report = ""
        for event in self._synthesize_stream(
            question=question, workspace=workspace,
            steps=steps, errors=errors, usage=usage,
        ):
            if event.get("type") == "token":
                yield event
            elif event.get("type") == "done":
                report = event.get("data", {}).get("report", "")
                yield event  # forward to runner so it can capture the report

        # --- Critic ---
        yield {"type": "phase", "data": {"phase": "critic", "message": "Reviewing report..."}}
        self._critique_report(question, report, errors, usage)

        # --- Done ---
        total_tokens = sum(u.prompt_tokens + u.completion_tokens for u in usage)
        if self._log:
            self._log.log("done", "", json.dumps({
                "iterations": iteration, "token_total": total_tokens,
                "notes_count": len(workspace.notes),
                "topics_final": [{"id": t.id, "status": t.status} for t in workspace.topics],
            }), iteration=iteration, action="done")
        yield {
            "type": "done",
            "data": {"iterations": iteration, "token_usage_total": total_tokens},
        }

    # ------------------------------------------------------------------
    # Question pool management
    # ------------------------------------------------------------------

    @staticmethod
    def _update_question_pool(
        workspace: Workspace,
        topic_id: str,
        resolved_indices: list[int],
        new_questions: list[str],
    ) -> None:
        """Move resolved questions from open_questions to resolved_questions,
        and add any newly discovered questions to open_questions.

        resolved_indices are indices into the topic's open_questions list.
        """
        topic = workspace.topic_by_id(topic_id)
        if not topic:
            return

        # Resolve questions by index
        if resolved_indices:
            # Sort descending to remove from end first (avoid index shifting)
            valid_indices = [i for i in resolved_indices if 0 <= i < len(topic.open_questions)]
            for idx in sorted(valid_indices, reverse=True):
                q = topic.open_questions.pop(idx)
                if q not in topic.resolved_questions:
                    topic.resolved_questions.append(q)

        # Add new questions (deduplicated)
        if new_questions:
            existing_open = set(topic.open_questions)
            existing_resolved = set(topic.resolved_questions)
            for nq in new_questions:
                nq = nq.strip()
                if nq and nq not in existing_open and nq not in existing_resolved:
                    topic.open_questions.append(nq)

    @staticmethod
    def _auto_manage_workspace(workspace: Workspace) -> list[str]:
        """Auto-update topic statuses based on question pool.

        Saturation rule: a topic is saturated when all its open questions
        have been resolved AND no new questions remain.

        Abandonment rule: a topic with >3 resolved questions but >3 open still
        after 5+ searches likely needs a narrower scope — mark abandoned.
        """
        changed = []
        for t in workspace.topics:
            t_notes = [n for n in workspace.notes if n.topic_id == t.id]
            if not t_notes:
                continue  # no searches yet — keep active

            open_count = len(t.open_questions)
            resolved_count = len(t.resolved_questions)

            # Saturated: question pool is empty and we have some resolved
            if open_count == 0 and resolved_count > 0:
                if t.status == "active":
                    t.status = "saturated"
                    t.findings_summary = (
                        f"Research complete: {resolved_count} questions answered, "
                        f"{len(t_notes)} notes from {len(t_notes)} searches"
                    )
                    changed.append(t.id)

            # Abandoned: too many open questions despite substantial searching
            elif open_count > 3 and resolved_count > 3 and len(t_notes) >= 5:
                if t.status == "active":
                    t.status = "abandoned"
                    t.findings_summary = (
                        f"Too broad: {open_count} questions still open after "
                        f"{len(t_notes)} searches — scope may need narrowing"
                    )
                    changed.append(t.id)

        return changed

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    def _plan(self, question, steps, usage, errors) -> Workspace | None:
        prompt = build_plan_prompt(question)
        try:
            text, llm_usage = self._llm.complete(prompt)
            if self._log:
                self._log.log("plan", prompt, text, iteration=0, action="plan")
            usage.append(TokenUsage(
                node="react_v3_plan",
                prompt_tokens=llm_usage.prompt_tokens,
                completion_tokens=llm_usage.completion_tokens,
                estimated_cost=llm_usage.estimated_cost,
            ))
        except Exception as exc:
            errors.append(f"Plan failed: {exc}")
            return None

        parsed = _parse_json_safe(text, _PlanResponse)
        if parsed is None:
            errors.append(f"Plan JSON parse failed: {text[:200]}")
            return Workspace(topics=[
                TopicState(id="t1", topic=question),
            ])

        topics = []
        for i, t in enumerate(parsed.get("topics", [])):
            topics.append(TopicState(
                id=t.get("id", f"t{i + 1}"),
                topic=t.get("topic", f"Topic {i + 1}"),
                open_questions=list(t.get("open_questions", [])),
            ))

        steps.append(AgentStep(
            iteration=0, action="plan",
            reasoning=f"Created plan: {', '.join(f'{t.topic}({len(t.open_questions)}q)' for t in topics)}",
        ))

        return Workspace(topics=topics[:5])

    def _synthesize_stream(self, question, workspace, steps, errors, usage):
        if not workspace.notes:
            msg = f"# {question}\n\nResearch found no substantive information.\n"
            yield {"type": "token", "data": {"text": msg}}
            yield {"type": "done", "data": {"report": msg}}
            return

        # Build findings from all notes
        findings_lines = []
        for t in workspace.topics:
            t_notes = [n for n in workspace.notes if n.topic_id == t.id]
            if not t_notes:
                continue
            findings_lines.append(f"## {t.id}: {t.topic}")
            if t.findings_summary:
                findings_lines.append(f"Summary: {t.findings_summary}")
            for n in t_notes:
                findings_lines.append(
                    f"### [{n.topic_id}] {n.source_title}\n"
                    f"Source: {n.source_url}\n\n{n.content}\n"
                )
        findings_text = "\n".join(findings_lines)

        # Evidence cards
        cards, cards_usage = self._notes_to_evidence_cards(findings_text, workspace, errors)
        if cards_usage.prompt_tokens > 0:
            usage.append(TokenUsage(
                node="react_v3_synthesize",
                prompt_tokens=cards_usage.prompt_tokens,
                completion_tokens=cards_usage.completion_tokens,
                estimated_cost=cards_usage.estimated_cost,
            ))

        allowed_urls = set()
        for n in workspace.notes:
            allowed_urls.add(n.source_url)
        for card in cards:
            allowed_urls.add(card.source_url)
            for cs in card.corroborating_sources:
                allowed_urls.add(cs)

        synth_sq = SubQuestion(
            id="react-v3", question=question, search_query=question,
            search_queries=[question], rationale="ReAct V3 autonomous research",
        )
        write_prompt = build_writing_prompt(
            question=question, subquestions=[synth_sq], results=[],
            evidence_cards=cards, allowed_source_urls=allowed_urls,
        )

        # Generate, validate, stream
        report_text = ""
        try:
            for chunk, chunk_usage in self._llm.complete_stream(write_prompt):
                if chunk:
                    report_text += chunk
                if chunk_usage:
                    usage.append(TokenUsage(
                        node="react_v3_synthesize",
                        prompt_tokens=chunk_usage.prompt_tokens,
                        completion_tokens=chunk_usage.completion_tokens,
                        estimated_cost=chunk_usage.estimated_cost,
                    ))
        except Exception as exc:
            errors.append(f"Report generation failed: {exc}")
            fallback = f"# {question}\n\nReport generation failed: {exc}\n\n## Raw Findings\n\n{findings_text[:2000]}"
            yield {"type": "token", "data": {"text": fallback}}
            yield {"type": "done", "data": {"report": fallback}}
            return

        validation = validate_citations(report_text, allowed_urls)
        if validation.passed:
            yield {"type": "token", "data": {"text": report_text}}
            yield {"type": "done", "data": {"report": report_text}}
            return

        # One rewrite
        errors.append(f"Citation validation failed: {validation.reason}: {validation.message}")
        rewrite_prompt = build_writing_prompt(
            question=question, subquestions=[synth_sq], results=[],
            evidence_cards=cards, allowed_source_urls=allowed_urls,
            review_feedback=f"Previous version failed citation validation. {validation.reason}: {validation.message}",
        )
        try:
            rewritten = ""
            for chunk, chunk_usage in self._llm.complete_stream(rewrite_prompt):
                if chunk:
                    rewritten += chunk
                if chunk_usage:
                    usage.append(TokenUsage(
                        node="react_v3_synthesize",
                        prompt_tokens=chunk_usage.prompt_tokens,
                        completion_tokens=chunk_usage.completion_tokens,
                        estimated_cost=chunk_usage.estimated_cost,
                    ))
            yield {"type": "token", "data": {"text": rewritten}}
            yield {"type": "done", "data": {"report": rewritten}}
        except Exception as exc:
            errors.append(f"Rewrite failed: {exc}")
            yield {"type": "token", "data": {"text": report_text}}
            yield {"type": "done", "data": {"report": report_text}}

    def _notes_to_evidence_cards(self, findings, workspace, errors):
        url_list = "\n".join(f"- {n.source_url}" for n in workspace.notes[:30])
        prompt = f"""Convert research findings into structured evidence cards.

## URLs
{url_list}

## Findings
{findings[:8000]}

Return JSON ONLY:
{{"evidence_cards": [
  {{"id": "c1", "subquestion_id": "react-v3", "claim": "fact",
    "source_url": "https://...", "source_title": "Title",
    "supporting_snippet": "excerpt", "content_type": "search_content",
    "corroboration_level": "single_source", "corroborating_sources": [],
    "confidence": "medium"}}
]}}"""
        try:
            text, usage = self._llm.complete(prompt)
            if self._log:
                self._log.log("evidence_cards", prompt, text, iteration=0, action="extract_cards")
        except Exception as exc:
            errors.append(f"Evidence card extraction failed: {exc}")
            return [], UsageInfo()

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
            return [], usage

        raw_cards = data.get("evidence_cards", []) if data else []
        cards = []
        for rc in raw_cards:
            try:
                corr_raw = rc.get("corroborating_sources", [])
                corr_urls = [cs.get("url", "") if isinstance(cs, dict) else str(cs) for cs in corr_raw]
                cards.append(EvidenceCard(
                    id=str(rc.get("id", "")), subquestion_id="react-v3",
                    claim=str(rc.get("claim", "")),
                    source_url=str(rc.get("source_url", "")),
                    source_title=str(rc.get("source_title", "")),
                    supporting_snippet=str(rc.get("supporting_snippet", "")),
                    content_type="search_content",
                    corroboration_level=str(rc.get("corroboration_level", "single_source")),
                    corroborating_sources=corr_urls,
                    confidence=str(rc.get("confidence", "medium")),
                ))
            except Exception:
                pass
        return cards, usage

    def _critique_report(self, question, report, errors, usage):
        if not report or len(report) < 200 or "could not find" in report[:200]:
            return
        prompt = f"""Assess this report briefly.

## Question
{question}

## Report (excerpt)
{report[:3000]}

Return JSON ONLY:
{{"factual_issues": [], "contradictions": [], "overall_assessment": "1 sentence"}}"""
        try:
            text, llm_usage = self._llm.complete(prompt)
            if self._log:
                self._log.log("critic", prompt, text, iteration=0, action="critic")
            usage.append(TokenUsage(
                node="react_v3_critic",
                prompt_tokens=llm_usage.prompt_tokens,
                completion_tokens=llm_usage.completion_tokens,
                estimated_cost=llm_usage.estimated_cost,
            ))
            data = None
            text = text.strip()
            if text.startswith("{"):
                data = json.loads(text)
            if data:
                for issue in data.get("factual_issues", [])[:3]:
                    errors.append(f"[Critic] Factual: {issue}")
                for issue in data.get("contradictions", [])[:3]:
                    errors.append(f"[Critic] Contradiction: {issue}")
                if data.get("overall_assessment"):
                    errors.append(f"[Critic] {data['overall_assessment']}")
        except Exception:
            pass
