# React V3 Architecture Design

> **Version:** v1.0
> **Status:** Final -- Passed 1 round of design review (Griller review v1, 15 issues resolved)
> **Date:** 2026-06-18
> **Designer:** React V3 Architecture Team
> **Audience:** Engineering team implementing the V3 multi-agent research pipeline

---

## Executive Summary

React V3 is a **multi-agent research architecture** that replaces V2's fixed LangGraph pipeline with 8 specialized agents orchestrated by a thread-safe, budget-aware Supervisor. The design was subjected to a structured grill review that identified 15 issues, all of which have been resolved in this revision.

**Key improvements over V2 (graph_v2):**

| Dimension | V2 Limitation | V3 Solution |
|-----------|--------------|-------------|
| Query handling | Raw question string passed everywhere | **ResearchBrief** context compression with business-rule validation |
| Clarification | None | **Triage + Clarifier agents** with interactive and auto-resolve modes |
| Parallel safety | Fire-and-forget ThreadPoolExecutor | **Thread-safe Supervisor** with `threading.Lock`, timeouts, budget enforcement |
| Report review | Passive critic log, no rewrite | **5-dimension rubric** (70% threshold, up to 2 rewrites) |
| Quality gates | None before writing | **Pre-write validation gate** blocks on critical contradictions |
| Cost control | Implicit (iteration limits) | **Explicit budget**: `total_llm_call_budget`, `per_subagent_timeout`, `pipeline_timeout` |
| API compatibility | CLI-only | **Non-interactive fallback** for Clarifier enables server-mode operation |

**LLM call budget:** 8--28 calls per run (tiered by depth mode: quick / standard / deep), enforced by pre-pipeline cost projection and runtime budget watch. Estimated cost at DeepSeek pricing: $0.003--$0.024 per run.

**Implementation:** 6 phases over 5 weeks, beginning with a prerequisite refactoring of `runner.py` build_agent() into a strategy/plugin registry. V2 and V3 coexist via `--architecture` CLI flag.

**Risk profile:** All 7 identified risks have mitigations. The two critical risks (Supervisor race conditions, Clarifier blocking in API mode) are fixed in this revision. The highest remaining risk is LLM call cost in deep mode, addressed by budget gates and enforced depth-tier limits.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Agent Definitions](#2-agent-definitions)
3. [Complete Workflow](#3-complete-workflow)
4. [Key Design Decisions and Trade-offs](#4-key-design-decisions-and-trade-offs)
5. [Tool System Design](#5-tool-system-design)
6. [State Management](#6-state-management)
7. [Context Engineering Strategy](#7-context-engineering-strategy)
8. [Structured Output Definitions](#8-structured-output-definitions)
9. [Comparison Matrix: V2 vs V3](#9-comparison-matrix-v2-vs-v3)
10. [Implementation Path](#10-implementation-path)
11. [Revision Log](#11-revision-log)

---

## 1. Architecture Overview

### Topology

```
                                User Query
                                     |
                                     v
               ┌─────────────────────────────────────────┐
               │           [1] Triage Agent               │
               │  Determines: clarity, scope, format,     │
               │  urgency, routing decision               │
               │  Output: TriageDecision(route, flags)    │
               └────────────────┬────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    v                       v
        ┌─────────────────────┐   ┌──────────────────────┐
        │ Needs Clarification │   │   Clear Enough        │
        └─────────────────────┘   └──────────────────────┘
                    |                       |
                    v                       v
  ┌──────────────────────────────┐ ┌──────────────────────────────┐
  │  [2] Clarifier Agent          │ │  [3] Instruction Builder     │
  │  Multi-turn dialog OR         │ │  Compresses clarified query │
  │  auto-resolve fallback        │ │  into ResearchBrief          │
  │  Max 3 rounds / auto-default  │ │  + Business-rule validation  │
  └──────────────────────────────┘ └──────────────────────────────┘
                    |                       |
                    └───────────┬───────────┘
                                v
               ┌──────────────────────────────────────────────────┐
               │           ResearchBrief (validated)               │
               │  Business-rule checks: non-empty questions,       │
               │  valid time_range, depth consistency,             │
               │  budget-consistent                                │
               │  Retry on validation failure (max 1), abort       │
               │  on second failure -> fallback to safe defaults   │
               └──────────────────────────────────────────────────┘
                                |
                                v
               ┌──────────────────────────────────────────────────┐
               │      [4] Research Supervisor Agent                │
               │  Interprets ResearchBrief, creates                │
               │  SubQuestionRegistry (thread-safe)                │
               │  Assigns subquestions, monitors progress,         │
               │  decides termination                              │
               │  Enforces: per_subagent_timeout,                  │
               │  total_search_budget, LLM call budget             │
               │  Thread safety: threading.Lock on registry        │
               └────────────────┬─────────────────────────────────┘
                                |
                    ┌───────────┼───────────┐
                    v           v           v
        ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
        │ [5] Sub-Research │ │ [5] Sub-Research │ │ [5] Sub-Research │
        │     Agent 1      │ │     Agent 2      │ │     Agent 3      │
        │ (subquestion q1) │ │ (subquestion q2) │ │ (subquestion q3) │
        │                   │ │                   │ │                   │
        │ search_web()      │ │ search_web()      │ │ search_web()      │
        │ fetch()           │ │ fetch()           │ │ fetch()           │
        │ fact_check()      │ │ fact_check()      │ │ fact_check()      │
        │ extract()         │ │ extract()         │ │ extract()         │
        │                   │ │                   │ │                   │
        │ Output:            │ │ Output:            │ │ Output:            │
        │ AgentResult        │ │ AgentResult        │ │ AgentResult        │
        │ (SearchResult[] +  │ │ (SearchResult[] +  │ │ (SearchResult[] +  │
        │ EvidenceCard[] +   │ │ EvidenceCard[] +   │ │ EvidenceCard[] +   │
        │ TokenUsage[] +     │ │ TokenUsage[] +     │ │ TokenUsage[] +     │
        │ contradictions[])  │ │ contradictions[])  │ │ contradictions[])  │
        └───────────────────┘ └───────────────────┘ └───────────────────┘
                    |                   |                   |
                    └───────────────────┼───────────────────┘
                                        v
               ┌──────────────────────────────────────────────────┐
               │     [6] Evidence Consolidator Agent               │
               │  Input: AgentResult[] from all sub-agents         │
               │  Does: 1) Semantic dedup of evidence cards        │
               │        2) Cross-subquestion corroboration         │
               │        3) Contradiction detection                 │
               │        4) Evidence quality scoring                │
               │        5) Pre-write validation gate:              │
               │           - Unresolved contradictions -> warnings │
               │           - Subquestion < 2 cards -> coverage gap │
               │           - Critical contradictions -> block      │
               │  Output: ConsolidatedEvidence                     │
               └──────────────────────────────────────────────────┘
                                        |
                                        v
               ┌──────────────────────────────────────────────────┐
               │      [7] Writing Agent                            │
               │  Input: ConsolidatedEvidence + ResearchBrief      │
               │  + pre_write_warnings                             │
               │  One-shot report generation with [N] citations    │
               │  Citation validation (bypass on second attempt)   │
               │  Output: Report (markdown string)                 │
               └──────────────────────────────────────────────────┘
                                        |
                                        v
               ┌──────────────────────────────────────────────────┐
               │    [8] Multi-Dimension Review Agent               │
               │  Evaluate report on 5 dimensions (0-100 each):    │
               │  - Factual Accuracy (FA)  30% weight              │
               │  - Coverage/Completeness (CO)  25%                │
               │  - Reasoning Quality (RQ)  20%                    │
               │  - Citation Quality (CI)  15%                     │
               │  - Clarity/Structure (CS)  10%                    │
               │  Composite >= 70 pass; else rewrite (max 2)       │
               └────────────────┬─────────────────────────────────┘
                                |
                     ┌──────────┴──────────┐
                     v                     v
                 (pass)               (fail + retries < 2)
                     |                     |
                     v                     v
          ┌─────────────────────┐ ┌─────────────────────┐
          │  Final Report        │ │  Writing Agent       │
          │  + Review Summary    │<│  (with review        │
          │                     │ │   feedback)           │
          └─────────────────────┘ └─────────────────────┘
```

### Budget Enforcement Gates

```
                    ┌──────────────────────────────────────┐
                    │   Pipeline Budget Check                │
                    │   Before Phase 2: projected_cost       │
                    │   <= budget?                           │
                    │   YES -> proceed                       │
                    │   NO  -> abort with warning             │
                    └──────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │   Supervisor Budget Watch              │
                    │   Every sub-agent completion:          │
                    │   total_llm_calls <= budget?           │
                    │   NO -> finalize remaining             │
                    └──────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │   Per-SubAgent Timeout                 │
                    │   concurrent.futures.timeout           │
                    │   on future.result(timeout)            │
                    │   Timeout -> mark saturated             │
                    │   -> release slot                      │
                    └──────────────────────────────────────┘
```

### Data Flow Summary

```
User -> [Triage] -> [Clarify | Build] -> ResearchBrief (validated)
  -> [Supervisor with budget watch]
  -> [SubAgent x N with TokenUsage tracking + timeout]
  -> AgentResult[] -> [Consolidator with pre-write gate]
  -> ConsolidatedEvidence -> [Writer] -> Report -> [Reviewer] -> FinalReport
```

---

## 2. Agent Definitions

### 2.1 Triage Agent

```python
class TriageInput(BaseModel):
    query: str
    conversation_history: list[dict] = []
    user_context: dict = {}          # from ResearchMemory
    interactive: bool = True         # whether user can respond to clarifications


class TriageDecision(BaseModel):
    route: Literal["clarify", "direct_to_research"]
    clarity_flags: list[str] = []
    # Flags indicating what's unclear:
    #   "ambiguous_scope", "missing_constraints", "format_unclear",
    #   "multiple_interpretations", "needs_time_range", "needs_geo_focus"
    suggested_clarifications: list[str] = []
    confidence: float                # 0.0-1.0 routing confidence
    estimated_depth: Literal["quick", "standard", "deep"] = "standard"
```

**Responsibility:** Examine the raw user query and decide whether it needs clarification or can proceed directly to instruction building. This is a lightweight, single-LLM-call gate.

**Non-interactive awareness:** When `TriageInput.interactive == False` (API/server mode), the Triage Agent prefers `"direct_to_research"` unless the query is fundamentally ambiguous (confidence < 0.3). This prevents the Clarifier from blocking in non-interactive contexts.

### 2.2 Clarifier Agent

```python
class ClarifierTurn(BaseModel):
    question: str
    options: list[str] = []          # suggested answers for the user
    rationale: str                   # why this question helps


class ClarifierResult(BaseModel):
    clarified_query: str             # merged expression of the user's needs
    answered_questions: list[dict] = []  # [{question, answer}]
    auto_resolved: bool = False      # true if fallback defaults were used
```

**Responsibility:** Conduct up to 3 rounds of back-and-forth with the user to collect missing information. Each round asks one question (with 2-3 suggested answers). Stops early if all clarity flags are resolved.

**Non-interactive fallback:** When `interactive == False`, the Clarifier uses auto-resolve logic:
1. For each clarity flag, use a reasonable default (e.g. `time_range="recent"`, `geo_focus="global"`, `format_preference="report"`)
2. Merge all defaults into clarified_query with `[Auto-resolved]` prefix
3. Set `auto_resolved = True`
4. No actual LLM calls made for clarification rounds

This enables the V3 pipeline to work in API server mode without modification.

### 2.3 Instruction Builder Agent

```python
class ResearchBrief(BaseModel):
    """The distilled research mandate -- replaces the raw user query.
    Validated with business-rule checks after LLM generation.
    """
    clarified_question: str
    time_range: str = "recent"          # "past_year", "past_5_years", "all_time", etc.
    geo_focus: str = "global"
    format_preference: Literal["report", "comparison", "analysis", "summary"] = "report"
    constraints: list[str] = []         # excluded sources, viewpoints, etc.
    depth_indicator: Literal["quick", "standard", "deep"] = "standard"
    seed_subquestions: list[str] = []   # 2-3 LLM-generated starting angles
    target_audience: str = "general"    # "expert", "general", "executive"
    special_instructions: str = ""

    @model_validator(mode="after")
    def validate_seed_subquestions(self) -> "ResearchBrief":
        if not self.seed_subquestions:
            self.seed_subquestions = [self.clarified_question]
        return self

    @model_validator(mode="after")
    def validate_depth_consistency(self) -> "ResearchBrief":
        if self.depth_indicator == "quick" and len(self.seed_subquestions) > 3:
            self.seed_subquestions = self.seed_subquestions[:3]
        return self

    @model_validator(mode="after")
    def validate_time_range(self) -> "ResearchBrief":
        valid_ranges = {"recent", "past_year", "past_5_years", "all_time"}
        if self.time_range not in valid_ranges:
            self.time_range = "recent"  # default fallback
        return self
```

**Responsibility:** Compress the user's clarified query (or direct query if no clarification needed) into a structured, machine-readable research brief. This is the key Context Engineering point: the brief replaces all previous conversation history for downstream agents.

**Validation step:** After LLM generates the raw ResearchBrief, run it through Pydantic validation AND business-rule checks:
- `seed_subquestions` must be non-empty (fill with `[clarified_question]` if empty)
- `depth_indicator` must be consistent with other fields (quick mode limits subquestions to 3)
- `time_range` must be one of the known values (fall back to "recent" if invalid)
- If validation fails, attempt one retry with LLM (pass the validation error back)
- If second attempt also fails, fall back to defaults and flag a warning

### 2.4 Research Supervisor Agent

```python
class SubQuestionRegistry(BaseModel):
    """Managed by the Supervisor -- tracks all sub-questions."""
    entries: list[SubQuestionEntry] = []

    def get_entry(self, id: str) -> SubQuestionEntry | None:
        for e in self.entries:
            if e.id == id:
                return e
        return None

    def update_status(self, id: str, status: str) -> None:
        entry = self.get_entry(id)
        if entry:
            entry.status = status


class SubQuestionEntry(BaseModel):
    id: str
    question: str
    rationale: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    search_count: int = 0
    extracts_count: int = 0
    card_count: int = 0
    result: AgentResult | None = None


class SupervisorAction(BaseModel):
    action: Literal["start_agent", "check_progress", "reassign", "finalize"]
    subquestion_ids: list[str] = []
    rationale: str = ""
```

**Responsibility:** Manage the lifecycle of sub-research agents. The Supervisor:
1. Takes `ResearchBrief` and creates 2-5 `SubQuestionEntry`
2. Manages a pool of parallel execution slots (default 3)
3. Decides when to launch new sub-agents vs wait for running ones
4. Monitors for saturation (a subquestion with no new findings after 3 searches)
5. Detects dead-ends and reassigns remaining scope
6. Signals all research complete when all subquestions are done/saturated
7. Enforces budget and timeout limits
8. Uses thread-safe state management

**Context Isolation:** The Supervisor does NOT see search results or evidence cards. It only sees the metadata (status, counts) from each SubQuestionEntry.

**Thread-safe Supervisor implementation:**

```python
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError


class ResearchSupervisor:
    def __init__(self, llm, tools, ctx: RunContext):
        self._llm = llm
        self._tools = tools
        self._ctx = ctx
        self._registry = SubQuestionRegistry()
        self._lock = threading.Lock()                 # Protects all registry mutations
        self._total_llm_calls = 0
        self._running_futures: dict[Future, str] = {}
        self._errors: list[str] = []

    def _safe_update(self, sq_id: str, **updates):
        """Thread-safe update of a SubQuestionEntry."""
        with self._lock:
            entry = self._registry.get_entry(sq_id)
            if entry:
                for k, v in updates.items():
                    setattr(entry, k, v)

    def _safe_acquire_slot(self) -> bool:
        """Thread-safe slot availability check."""
        with self._lock:
            running = sum(1 for e in self._registry.entries if e.status == "running")
            return running < self._ctx.config.max_parallel_agents

    def run(self) -> list[AgentResult]:
        self._plan_subquestions()

        results: list[AgentResult] = []
        with ThreadPoolExecutor(
            max_workers=self._ctx.config.max_parallel_agents
        ) as executor:
            while self._has_pending():
                if not self._check_llm_budget():
                    self._finalize_remaining("budget_limit")
                    break

                pending = self._next_pending(
                    limit=self._ctx.config.max_parallel_agents
                )
                for sq in pending:
                    self._safe_update(sq.id, status="running")
                    future = executor.submit(
                        self._run_one_agent,
                        sq,
                    )
                    self._running_futures[future] = sq.id

                for future in as_completed(
                    self._running_futures,
                    timeout=self._ctx.config.pipeline_step_timeout,
                ):
                    sq_id = self._running_futures.pop(future)
                    try:
                        result = future.result(
                            timeout=self._ctx.config.per_subagent_timeout
                        )
                        results.append(result)
                        self._safe_update(sq_id, status="completed", result=result)
                        self._total_llm_calls += self._count_llm_calls(result)
                    except TimeoutError:
                        self._errors.append(f"Agent {sq_id} timed out")
                        self._safe_update(sq_id, status="skipped")
                    except Exception as exc:
                        self._errors.append(f"Agent {sq_id} failed: {exc}")
                        self._safe_update(sq_id, status="failed")

        return results

    def _check_llm_budget(self) -> bool:
        return self._total_llm_calls < self._ctx.config.total_llm_call_budget
```

### 2.5 Sub-Research Agent

```python
class AgentResult(BaseModel):
    """Output from a single Sub-Research Agent run."""
    subquestion_id: str
    subquestion: str
    search_results: list[SearchResult] = []
    evidence_cards: list[EvidenceCard] = []
    visited_urls: list[str] = []
    errors: list[str] = []
    token_usage: list[TokenUsage] = []
    steps: list[AgentStep] = []
    saturated: bool = False
    contradictions_found: list[str] = []


class AgentStep(BaseModel):
    """Single action within a sub-agent's research loop."""
    iteration: int
    action: str                               # "search", "fetch", "extract", etc.
    query: str = ""
    result_summary: str = ""
    urls: list[str] = []
    contradictions_found: list[str] = []
```

**Responsibility:** Execute the full research loop for ONE subquestion:
1. Generate 2-3 search queries based on the subquestion
2. For each search result, fetch/extract full content
3. Extract evidence cards from fetched content
4. Cross-validate claims within the subquestion's sources
5. Loop until saturation or max iterations

**Each sub-agent is isolated:** It only knows its subquestion and has its own tool calls. It never sees other subquestions' data.

**Inherited from V2:** The per-subquestion research loop pattern (search -> extract -> validate) is directly inherited from V2's `subquestion_agent.py`. V3 adds: iteration loop with saturation, TokenUsage tracking, and contradiction preservation.

**TokenUsage tracking at every LLM call:**

```python
class SubResearchAgent:
    def _plan_queries(self) -> list[str]:
        prompt = build_search_plan_prompt(self._sq.question)
        text, llm_usage = self._llm.complete(prompt)
        self._usage.append(TokenUsage(
            node=f"subagent_{self._sq.id}_plan",
            prompt_tokens=llm_usage.prompt_tokens,
            completion_tokens=llm_usage.completion_tokens,
            estimated_cost=llm_usage.estimated_cost,
        ))
        return parse_queries(text)

    def _extract_cards(self) -> list[EvidenceCard]:
        prompt = build_extraction_prompt(self._sq.question, self._sources)
        text, llm_usage = self._llm.complete(prompt)
        self._usage.append(TokenUsage(
            node=f"subagent_{self._sq.id}_extract",
            prompt_tokens=llm_usage.prompt_tokens,
            completion_tokens=llm_usage.completion_tokens,
            estimated_cost=llm_usage.estimated_cost,
        ))
        return parse_cards(text)

    def run(self, max_iterations: int = 3) -> AgentResult:
        queries = self._plan_queries()
        for query in queries:
            result = self._tools.execute(...)
        cards = self._extract_cards()
        cards = self._cross_validate(cards)
        return AgentResult(
            subquestion_id=self._sq.id,
            evidence_cards=cards,
            token_usage=self._usage,
            contradictions_found=self._contradictions,
            visited_urls=list(self._visited_urls),
        )
```

### 2.6 Evidence Consolidator Agent

```python
class ConsolidatedEvidence(BaseModel):
    evidence_cards: list[EvidenceCard]
    contradictions: list[Contradiction] = []
    cross_agent_corroborations: int = 0
    quality_scores: dict[str, float] = {}
    coverage_gaps: list[str] = []
    pre_write_warnings: list[str] = []
    blocked: bool = False                    # Writer should not proceed if True


class Contradiction(BaseModel):
    topic: str
    claim_a: str
    agent_a: str
    source_a: str
    claim_b: str
    agent_b: str
    source_b: str
    explanation: str = ""
```

**Responsibility:** Receive all `AgentResult` objects and produce a consolidated evidence set:
1. **Semantic dedup:** Merge evidence cards with claims about the same fact
2. **Cross-subquestion corroboration:** Inherited from V2's `coordinator.py` `_detect_cross_agent_corroboration()`, which upgrades corroboration levels when different agents from different domains confirm the same claim
3. **Contradiction detection:** Inherited from V2's hybrid Jaccard+LLM approach (`_detect_contradictions_llm()` in coordinator.py)
4. **Pre-write validation gate:** Before passing to Writer, check:
   - Unresolved contradictions exist -> add to `pre_write_warnings`
   - Any subquestion has < 2 evidence cards -> add to `coverage_gaps`
   - Contradictions on critical facts -> set `blocked = True`

```python
class EvidenceConsolidator:
    def _pre_write_gate(
        self, consolidated: ConsolidatedEvidence
    ) -> ConsolidatedEvidence:
        warnings = []

        if consolidated.contradictions:
            consolidated.pre_write_warnings.append(
                f"{len(consolidated.contradictions)} contradiction(s) detected: "
                + "; ".join(c.topic for c in consolidated.contradictions[:3])
            )

        for sq_id, score in consolidated.quality_scores.items():
            if score < 0.3:
                consolidated.coverage_gaps.append(
                    f"Subquestion {sq_id} has low evidence quality ({score:.2f})"
                )

        critical = [
            c for c in consolidated.contradictions
            if self._is_high_confidence_contradiction(c, consolidated.evidence_cards)
        ]
        if len(critical) > 1:
            consolidated.blocked = True
            consolidated.pre_write_warnings.append(
                f"BLOCKED: {len(critical)} critical contradiction(s) unresolved. "
                "Writer cannot produce a coherent report."
            )

        return consolidated
```

### 2.7 Writing Agent

```python
class WriteFeedback(BaseModel):
    review_issues: list[str] = []
    review_suggestions: list[str] = []
    allowed_urls: set[str] = set()
```

**Responsibility:** One-shot report generation from consolidated evidence. Same mechanism as V2's `build_writing_prompt` + `validate_citations`, reused unchanged. The Writer sees ONLY `ConsolidatedEvidence.evidence_cards` -- no raw search results.

**Pre-write warning awareness:** If `ConsolidatedEvidence.blocked == True`, the Writer refuses to write and returns an error diagnostic with coverage gaps and contradictions listed. If warnings exist but not blocked, they are injected into the writing prompt as advisory notes.

### 2.8 Multi-Dimension Review Agent

```python
from pydantic import BaseModel, Field


class ReviewRubric(BaseModel):
    factual_accuracy: int = Field(ge=0, le=100)
    coverage_completeness: int = Field(ge=0, le=100)
    reasoning_quality: int = Field(ge=0, le=100)
    citation_quality: int = Field(ge=0, le=100)
    clarity_structure: int = Field(ge=0, le=100)


class ReviewResult(BaseModel):
    rubric: ReviewRubric
    composite_score: int = Field(ge=0, le=100)
    passed: bool
    issues: list[str] = []
    suggestions: list[str] = []
    can_improve: bool = True
```

**Responsibility:** Multi-dimensional report evaluation (truly new in V3 -- V2's critic only logged issues without triggering rewrites).
1. Score each of the 5 dimensions with specific justification
2. Composite = weighted average (FA:30%, CO:25%, RQ:20%, CI:15%, CS:10%)
3. If composite >= 70 or rewrite limit reached (max 2 rewrites total) -> pass
4. Else -> return review_feedback to Writing Agent for rewrite
5. Each rewrite attempt includes the previous review as feedback

---

## 3. Complete Workflow

### Phase 0: Triage (1 LLM call)

```
1. User submits query
2. Triage Agent receives TriageInput(query, interactive=True/False)
3. LLM classifies: route, clarity_flags, confidence, estimated_depth
4. If route == "clarify" AND interactive == True: proceed to Phase 1A
5. If route == "clarify" AND interactive == False:
   -> Set auto_resolve mode, skip to Phase 1B with defaults
6. If route == "direct_to_research": skip to Phase 1B
```

### Phase 1A: Clarification (0-3 LLM calls, user interaction OR auto-resolve)

```
1. Clarifier Agent gets TriageDecision.clarity_flags
2. If interactive mode:
   a. For each flag (max 3), generate one question
   b. User responds (text or picks from options)
   c. Update ClarifierResult.answered_questions
3. If auto-resolve mode:
   a. Use defaults for each clarity flag
   b. Set ClarifierResult.auto_resolved = True
4. Build final clarified_query
5. Pass to Instruction Builder
```

### Phase 1B: Instruction Building (1 LLM call + validation)

```
1. Instruction Builder receives (clarified_query OR raw query)
2. LLM generates ResearchBrief with all fields
3. ResearchBrief validated via Pydantic model_validate
4. Business-rule checks applied:
   - Non-empty seed_subquestions
   - Valid time_range
   - Depth-constraint consistency
5. If validation fails -> retry once with LLM (pass error feedback)
6. If retry also fails -> fall back to safe defaults, flag warning
7. Publish "research_brief" event
8. ResearchBrief is the ONLY context passed to downstream agents
```

### Phase 2: Research Supervision + Execution (varies: 5-25 LLM calls)

```
1. Supervisor receives ResearchBrief
2. LLM generates SubQuestionRegistry (2-5 subquestions)
3. Pipeline budget check: projected_cost <= budget?
   If NO -> abort with "budget exceeded" message
4. Supervisor establishes parallel slot pool (default 3)
5. RESEARCH LOOP (thread-safe):
   a. Acquire lock, check available slots
   b. Pick next pending subquestion
   c. Launch Sub-Research Agent via ThreadPoolExecutor
      with concurrent.futures.timeout (default 120s per agent)
   d. Sub-Research Agent runs its own loop:
      - Phase 2a: Generate 2-3 search queries (1 LLM call, record TokenUsage)
      - Phase 2b: Execute searches (tool calls, 0 LLM)
      - Phase 2c: Fetch/extract search results (tool calls, 0 LLM)
      - Phase 2d: Extract evidence cards (1 LLM call, record TokenUsage)
      - Phase 2e: Cross-validate within subquestion (1 LLM call, record TokenUsage)
      - Phase 2f: Check saturation; preserve contradictions found so far
      - Phase 2g: If not saturated and within budget, loop to 2a
   e. On timeout: mark subquestion as "skipped", release slot
   f. On completion: lock, update SubQuestionEntry, release slot
   g. Supervisor budget check: total_llm_calls < budget?
      If NO -> finalize remaining pending as "skipped"
6. Supervisor signals "research_complete" with AgentResult[]
```

### Phase 3: Evidence Consolidation (1 LLM call + pre-write gate)

```
1. Consolidator receives AgentResult[]
2. Merge all evidence cards, deduplicate semantically
3. Detect cross-subquestion corroboration (reuse V2 coordinator logic)
4. Detect contradictions via LLM (reuse V2 hybrid approach)
5. Assign quality scores per subquestion
6. Identify coverage gaps (subquestions with < 2 cards)
7. PRE-WRITE VALIDATION GATE:
   a. Check for critical unresolved contradictions
   b. If too many contradictions -> set blocked=True
   c. If blocked -> return with coverage_gaps + contradiction list
   d. If not blocked but warnings exist -> attach as advisory notes
8. Output ConsolidatedEvidence
```

### Phase 4: Writing (1-2 LLM calls, streaming)

```
1. Check ConsolidatedEvidence.blocked
   If blocked -> skip writing, return error diagnostic
2. Writer receives ConsolidatedEvidence + ResearchBrief
3. Inject pre_write_warnings into prompt as advisory notes
4. Build writing prompt (reuse build_writing_prompt from V2)
5. Generate report (streaming)
6. Validate citations (reuse validate_citations from V2)
7. If FAILED and attempt < 2: rewrite with failure feedback
8. Output final report string
```

### Phase 5: Review (1-2 LLM calls)

```
1. Reviewer receives Report + ConsolidatedEvidence
2. Score 5 dimensions with justification
3. Calculate composite score
4. If composite >= 70 OR rewrite count >= 2:
   - Mark passed
   - Output final report + review summary
5. Else (composite < 70 and rewrites < 2):
   - Output review_feedback
   - Writer rewrites with feedback (counts as rewrite, max 2 total)
```

### Total LLM Call Estimate (with budget enforcement)

| Phase              | Min Calls | Max Calls | Notes                                           |
|--------------------|-----------|-----------|-------------------------------------------------|
| Triage             | 1         | 1         | Single classification                           |
| Clarify            | 0         | 3         | 0 if direct or auto-resolve, 1-3 if interactive |
| Instruction Build  | 1         | 2         | 1 + optional retry on validation failure        |
| Supervisor (plan)  | 1         | 1         | Subquestion generation                          |
| Sub-Agents (each)  | 2         | 6         | Per subquestion. Budget cap: default 15 total   |
| Consolidation      | 1         | 1         | Pre-write gate is rule-based, not LLM           |
| Writing            | 1         | 2         | 1 initial + 1 optional rewrite                  |
| Review             | 1         | 2         | 1 review + 1 optional follow-up                 |
| **Total (quick)**  | **8**     | **--**    | 1+1+1+2x2+1+1+1 = 8-9                          |
| **Total (standard)** | **--** | **18**    | +1 clarify + 3x3 sub + optional rewrite         |
| **Total (deep)**   | **--**    | **28**    | +3 clarify + 4x4 sub + rewrite                  |

**Budget enforcement:** `RunConfig.total_llm_call_budget` caps the total. Quick=10, Standard=18, Deep=28. Pipeline checks before Phase 2 and after each sub-agent completion.

---

## 4. Key Design Decisions and Trade-offs

### Decision 1: Multi-Agent Pipeline over Single-Agent Loop

**Status:** Enhanced architecture from V2.

**Rationale:** OpenAI Deep Research's foundation is Context Isolation -- each agent sees only the context it needs. V2's single-agent loop (react_v2.py) carried the entire workspace into every action prompt, causing token usage to grow linearly with iterations.

**What V3 inherits from V2:** V2's `graph_v2.py` already implements a multi-agent pipeline with parallel subquestion agents, coordinator node, and separate writer node. V3 formalizes this into explicit agent roles.

**Trade-off:** Increased total LLM calls (8-28 vs V2's ~10-15), but each call's prompt is smaller and more focused. Net wall-clock time is LOWER due to parallelism.

**Cost consideration:** 8-28 LLM calls at ~3K tokens each = ~24K-84K tokens per run. At DeepSeek pricing ($0.14/M input, $0.28/M output): ~$0.003-$0.024 per run. For quick-mode (8 calls, ~24K tokens): ~$0.003. For deep-mode (28 calls, ~84K tokens): ~$0.024.

### Decision 2: ResearchBrief as Context Compression Point

**Status:** New in V3 (no equivalent in V2 -- raw question string passed everywhere).

**Rationale:** In V2, the raw `question` string was passed everywhere. If the user had a back-and-forth clarification, that history was lost or inconsistently incorporated. The `ResearchBrief` Pydantic model compresses ALL prior context (original query + clarification answers + inferred constraints) into a single structured object.

**Trade-off:** Adds 1-2 LLM calls (Clarifier + Instruction Builder). But downstream agents save 3-10x that in prompt size because they don't need conversation history.

### Decision 3: Parallel Sub-Research Agents with Supervisor

**Status:** Enhanced from V2 (already present in graph_v2.py).

**What V2 already has:** `graph_v2.py` uses `ThreadPoolExecutor` to parallelize subquestion agents (lines 90-101), each running independent search-extract-validate pipeline.

**What V3 adds:** Explicit Supervisor role with lifecycle management, saturation detection, budget enforcement, timeout control, and thread-safe state management. V2's agent execution is fire-and-forget (collect results, no mid-execution monitoring).

**Trade-off:** Parallel sub-agents increase total LLM calls but reduce wall-clock time. V3 adds budget gates and timeout handling that V2 lacks.

### Decision 4: LLM-Powered Evidence Consolidation

**Status:** Enhanced from V2.

**What V2 already has:** `coordinator.py` implements cross-agent corroboration detection (lines 78-147), hybrid Jaccard+LLM contradiction detection (lines 295-414), and comprehensive evidence merging.

**What V3 adds:** Coverage gap analysis (flagging subquestions with insufficient evidence), per-subquestion quality scoring, and pre-write validation gate that can block the Writer if critical contradictions are unresolved.

**Trade-off:** Adds 1 LLM call over V2. The pre-write gate prevents wasted Writer calls on contradictory evidence, saving 2+ LLM calls in failure scenarios.

### Decision 5: Multi-Dimensional Review with Rewrite Loop

**Status:** Truly new in V3.

**Rationale:** V2's critic (`_critique_report()` in react_v2.py lines 853-888) was a single LLM call that logged issues to `errors[]` but never triggered rewrites. V3's Review Agent uses a structured 5-dimension rubric with clear pass/fail thresholds (70/100) and up to 2 rewrite cycles.

**Trade-off:** Adds 1-2 LLM calls. But structured reviews catch more issues and the rewrite loop ensures minimum quality before output.

### Decision 6: Tool System -- Extend Existing Registry, Defer MCP

**Status:** Reuses V2's `ToolRegistry`, defers MCPToolAdapter.

**Rationale:** V2's `ToolRegistry` is a simple, well-tested container with `register()` and `execute()`. Creating a parallel `MCPToolRegistry` would require maintaining two separate registration systems. Since MCP servers are not yet in use, the MCP adapter adds complexity with no immediate benefit.

**V3 approach:** Extend `ToolRegistry` with an optional `mcp_servers` dict. When no MCP servers are configured, it behaves identically to V2's registry. When MCP servers are available, tool lookup checks local tools first, then MCP servers.

**Deferred:** `MCPToolAdapter` and full MCP integration moved to Phase 5 (production readiness).

### Decision 7: Non-Interactive Fallback for Clarifier

**Status:** New in V3 (fixes a critical gap in the original design).

**Rationale:** The original V3 design assumed CLI-only interaction. The existing codebase already has `server.py` (API server), and the Clarifier Agent would block in non-interactive mode. Adding `ClarifierMode` with `auto_resolve` fallback makes the pipeline work in both CLI and API contexts.

**Trade-off:** Auto-resolve may miss nuance that interactive clarification would catch.

### Decision 8: Thread-Safe Supervisor State

**Status:** New in V3 (fixes a critical correctness gap in the original design).

**Rationale:** The original design used `ThreadPoolExecutor` with concurrent writes to `SupervisorState.running_agents` dict -- a classic race condition. The revised design uses `threading.Lock` for all state mutations.

**Comparison with V2:** V2's `graph_v2.py` uses `ThreadPoolExecutor` in fire-and-forget mode -- it submits all agents, then collects results. No concurrent state updates occur because each agent returns an independent `AgentResult` and the coordinator processes them sequentially. V3's Supervisor needs thread safety because it monitors and mutates registry state during execution.

### Decision 9: Pruning Preserves Contradiction History

**Status:** Bug fix in V3's original design.

**Rationale:** The original `prune_subagent_history()` discarded intermediate contradictions, losing valuable information. The revised version preserves `contradictions_found` from each iteration and includes them in the final `AgentResult`.

### Decision 10: Context Isolation vs Cross-Corroboration Tension

**Status:** Acknowledged design tension, addressed with configurable isolation.

**Rationale:** Context Isolation prevents cross-contamination between sub-agents, but cross-subquestion corroboration requires comparing claims across subquestions. These goals are in tension: perfect isolation makes cross-corroboration impossible.

**Resolution:**
- Sub-agents run in true isolation at research time (no knowledge of other subquestions)
- Consolidator explicitly re-correlates at merge time using LLM semantic similarity
- Isolation level is configurable: from strict (no cross-subquestion context) to relaxed (sub-agents receive brief summaries of sibling subquestions) via `RunConfig.isolation_level`

**Default:** strict isolation for research, full visibility at consolidation.

---

## 5. Tool System Design

### Architecture (Simplified -- Reuses Existing V2 System)

```
Tool (Protocol, unchanged from V2)
+-- TavilySearchTool          (reused from V2)
+-- WebFetchTool              (reused from V2)
+-- TavilyExtractTool         (reused from V2)
+-- CompareSourcesTool        (reused from V2)
+-- FactCheckTool             (reused from V2)
+-- MCPToolAdapter            (DEFERRED to Phase 5)
```

### Tool Registry (Extended, not replaced)

```python
# tools/registry.py -- existing V2 class, extended with MCP support

class ToolRegistry:
    """V2-compatible tool registry, extended with optional MCP server support."""

    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        self._mcp_servers: dict[str, MCPServer] = {}   # optional, Phase 5
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: Tool) -> None:
        """Add a local tool (same as V2)."""
        self._tools[tool.name] = tool

    def register_mcp_server(self, name: str, server: MCPServer) -> None:
        """Register an MCP server (deferred, no-op until Phase 5)."""
        self._mcp_servers[name] = server

    def execute(self, name: str, **kwargs) -> ToolResult:
        tool = self._tools.get(name)
        if tool:
            return tool.execute(**kwargs)
        # Fall through to MCP servers (Phase 5)
        for srv in self._mcp_servers.values():
            if srv.has_tool(name):
                return srv.call_tool(name, **kwargs).to_tool_result()
        return ToolResult(
            error=f"Unknown tool: {name}. Available: {sorted(self._tools.keys())}"
        )

    def describe_tools(self) -> str:
        lines = ["Available tools:"]
        for name in sorted(self._tools):
            tool = self._tools[name]
            lines.append(f"\n## {name}")
            lines.append(f"Description: {tool.description}")
            lines.append(f"Parameters: {tool.parameters}")
        return "\n".join(lines)
```

**Key simplification:** No `MCPToolRegistry` class. No two-registry maintenance. One `ToolRegistry` handles both local and MCP tools, with zero behavioral change when MCP is not configured.

### Tool Execution in Sub-Research Agent

Each sub-agent receives a shared (read-only) `ToolRegistry` reference. Tool instances that maintain internal mutable state (caches, counters) are identified and their shared state paths documented, rather than pretending perfect isolation exists.

**Known shared state in tools:**
1. `TavilyKeyPool` -- application singleton, shared across all agents. Mitigated by connection pooling, not isolation. Does not affect data integrity (only rate limiting).
2. `ResearchMemory` singleton -- shared writes from Supervisor (for meta-learning), not from sub-agents. Sub-agents do not write to ResearchMemory.
3. Tool caches -- if any tool maintains an internal cache, it is shared. This is generally beneficial (deduplication) and not a data-integrity issue.

**Context Isolation Claim:** "Each sub-agent only sees its own subquestion's data in prompts. Tool execution is isolated in the sense that tools are stateless with respect to research content. Shared infrastructure (KeyPool, cache) affects performance, not data confidentiality or research integrity."

---

## 6. State Management

### State Model

```python
# -- Shared across all agents --

class RunContext(BaseModel):
    session_id: str
    created_at: datetime
    research_brief: ResearchBrief
    config: "RunConfig"


class RunConfig(BaseModel):
    max_parallel_agents: int = 3
    max_iterations_per_subagent: int = 3       # reduced from 5 for budget control
    total_search_budget: int = 30
    total_llm_call_budget: int = 18            # prevents LLM call explosion
    per_subagent_timeout: int = 120            # seconds, prevents hanging
    pipeline_timeout: int = 600                # seconds, total pipeline timeout
    pipeline_step_timeout: int = 60            # seconds per step within supervisor
    max_rewrite_attempts: int = 2
    review_pass_threshold: int = 70
    tavily_results_per_query: int = 5
    evidence_card_min_count: int = 3
    clarifier_mode: Literal["interactive", "auto_resolve"] = "auto_resolve"
    isolation_level: Literal["strict", "relaxed"] = "strict"
    cost_per_call_estimate: float = 0.001       # used for pre-run budget projection


# -- Stage state --

class TriageState(BaseModel):
    input: TriageInput
    decision: TriageDecision | None = None


class ClarifierState(BaseModel):
    result: ClarifierResult
    turns_remaining: int = 3
    mode: Literal["interactive", "auto_resolve"] = "auto_resolve"


class SupervisorState(BaseModel):
    registry: SubQuestionRegistry
    running_agents: dict[str, AgentResult] = {}
    slot_count: int
    phase: Literal["planning", "executing", "finalizing"] = "planning"
    total_llm_calls: int = 0
    # NOT thread-safe directly -- mutating methods require external Lock
```

### Context Isolation Strategy

| Agent               | Sees                                          | Does NOT See                                   |
|---------------------|-----------------------------------------------|------------------------------------------------|
| Triage              | Raw query                                     | Nothing (first)                                |
| Clarifier           | Raw query, flags                              | ResearchBrief, evidence                        |
| Instruction Builder | Clarified query or raw query                  | Evidence, reports                              |
| Supervisor          | ResearchBrief only                            | Search results, evidence cards                 |
| Sub-Research Agent  | One SubQuestionEntry, tools                   | Other subquestions, full report                |
| Consolidator        | AgentResult[]                                 | Raw user query, report                         |
| Writer              | ConsolidatedEvidence + ResearchBrief          | Raw search results, full extracted text        |
| Reviewer            | Report + ConsolidatedEvidence                 | Raw search results, user query                 |

**Note on tool-level isolation:** Sub-agents share the same `ToolRegistry` instance. Tool execution is not data-isolated (all agents use the same API key pool and connection pool). However, this affects only performance characteristics, not research data integrity. True isolation is achieved at the prompt/context level -- no sub-agent sees another subquestion's data in its LLM prompt.

### How Context Is Passed

```python
class V3Pipeline:
    def __init__(self, llm: LLMClient, tools: ToolRegistry, config: RunConfig):
        self._llm = llm
        self._tools = tools
        self._config = config

    async def run(self, query: str) -> PipelineResult:
        # Stage 1: Triage
        triage = TriageAgent(self._llm)
        decision = triage.run(TriageInput(
            query=query,
            interactive=self._config.clarifier_mode == "interactive",
        ))

        # Stage 2: Clarify or Build
        brief = self._build_brief(decision, query)

        # Budget check before expensive phases
        projected_cost = self._project_cost(brief)
        if projected_cost > self._config.total_llm_call_budget:
            return PipelineResult(errors=[
                f"Projected cost ({projected_cost} calls) exceeds "
                f"budget ({self._config.total_llm_call_budget})"
            ])

        ctx = RunContext(
            session_id=uuid4().hex[:12],
            research_brief=brief,
            config=self._config,
        )

        # Stage 3: Supervisor + Sub-Agents
        supervisor = ResearchSupervisor(self._llm, self._tools, ctx)
        agent_results = await supervisor.run()

        # Stage 4: Consolidation + Pre-write gate
        consolidator = EvidenceConsolidator(self._llm)
        consolidated = consolidator.run(agent_results)
        if consolidated.blocked:
            return PipelineResult(errors=[
                f"Evidence consolidation blocked: "
                f"{consolidated.pre_write_warnings}"
            ])

        # Stage 5: Write + Review
        writer = WritingAgent(self._llm)
        report = writer.run(consolidated, brief)

        reviewer = MultiDimensionReviewer(self._llm)
        review = reviewer.run(report, consolidated)

        rewrite_count = 0
        while (
            not review.passed
            and rewrite_count < self._config.max_rewrite_attempts
        ):
            rewrite_count += 1
            report = writer.rewrite(consolidated, brief, review)
            review = reviewer.run(report, consolidated)

        return PipelineResult(
            report=report,
            review=review,
            evidence=consolidated,
            brief=brief,
        )
```

### Budget Projection

```python
def _project_cost(self, brief: ResearchBrief) -> int:
    """Estimate total LLM calls before starting expensive phases."""
    depth_map = {"quick": 8, "standard": 15, "deep": 25}
    base = depth_map.get(brief.depth_indicator, 15)
    num_sq = len(brief.seed_subquestions)
    per_sq_estimate = 3  # plan + extract + validate per subquestion
    estimated = base + (num_sq * per_sq_estimate)
    return min(estimated, self._config.total_llm_call_budget)
```

---

## 7. Context Engineering Strategy

Context engineering is the most critical design principle. V3 implements it at four levels:

### Level 1: Query Compression (Clarifier -> ResearchBrief)

Compresses ALL conversational context into a single structured field.

### Level 2: Brief Isolation (Supervisor)

Supervisor sees ONLY the ResearchBrief.

### Level 3: Subquestion Isolation (Sub-Research Agents)

Each sub-agent sees ONLY its own subquestion in prompts. It shares tool infrastructure (KeyPool, connection pool) with other agents, which affects rate limiting but not data integrity.

**Configurable isolation:** When `isolation_level = "relaxed"`, sub-agents receive a one-line summary of sibling subquestions ("Other researchers are covering: X, Y, Z") to avoid redundant searches without causing bias.

### Level 4: Evidence Isolation (Writer)

Writer sees only ConsolidatedEvidence.

### Level 5: Pruning with Contradiction Preservation

```python
def prune_subagent_history(
    iterations: list[AgentStep],
    contradictions_accumulated: list[str],  # accumulated across iterations
) -> tuple[list[AgentStep], list[str]]:
    """Keep only the last iteration's full steps; summarize earlier ones.
    Preserve contradictions found across all iterations.
    """
    if len(iterations) <= 1:
        return iterations, contradictions_accumulated

    last = iterations[-1]
    prior = iterations[:-1]

    for step in prior:
        contradictions_accumulated.extend(step.contradictions_found)

    summary = (
        f"(Previous {len(prior)} iterations explored "
        f"{len(set(s.query for s in prior if s.query))} queries, "
        f"visited {len(set(u for s in prior for u in s.urls))} URLs"
    )
    if contradictions_accumulated:
        summary += (
            f", found {len(contradictions_accumulated)} contradiction(s) "
            f"during earlier iterations"
        )
        for c in contradictions_accumulated[-5:]:  # keep last 5
            summary += f"\n  - {c}"

    return [
        AgentStep(iteration=0, action="summary", result_summary=summary),
        last,
    ], contradictions_accumulated
```

### Context Isolation vs Cross-Corroboration Tension (Analysis)

**The tension:**
- Context Isolation prevents sub-agents from seeing other subquestions' findings (avoids bias/cross-contamination)
- Cross-subquestion corroboration requires comparing claims across subquestions (requires shared semantic space)
- These goals are inherently in tension: perfect isolation makes cross-corroboration harder

**V3's resolution:**
1. **At research time:** Sub-agents are strictly isolated (default). Each agent only knows its own subquestion.
2. **At consolidation time:** Consolidator explicitly re-correlates all evidence cards using LLM semantic similarity, regardless of which agent produced them.
3. **Configurable isolation:** For research where cross-pollination is valuable (e.g., broad surveys), set `isolation_level = "relaxed"` to give sub-agents context about siblings.
4. **Coverage gaps:** Consolidator explicitly identifies subquestions with insufficient evidence.

**Quantified trade-off:** Strict isolation means the Consolidator does the correlation work. This costs 1 additional LLM call (the consolidation phase). In V2's approach (no isolation, everything in one context), the correlation happened implicitly but the context was much larger. The trade-off is favorable for V3: one LLM call with ~2K tokens vs V2's approach of carrying all subquestions in every action prompt (accumulating 8K+ tokens).

---

## 8. Structured Output Definitions

Key Pydantic models for the V3 pipeline.

### 8.1 Core Data Models (reused from V2, unchanged)

```python
# From state.py -- reused:
# - SubQuestion
# - SearchResult
# - EvidenceCard (with corroboration_level, corroborating_sources)
# - TokenUsage, UsageInfo, ExtractedClaim, ExtractedSource
```

### 8.2 Pipeline Models (new or modified in V3)

All models reside in `src/deepresearch/agents/react_v3/models.py`.

```python
from datetime import datetime
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator
from typing import Literal


class RunConfig(BaseModel):
    """Configuration for a single V3 pipeline run."""
    max_parallel_agents: int = 3
    max_iterations_per_subagent: int = 3
    total_search_budget: int = 30
    total_llm_call_budget: int = 18
    per_subagent_timeout: int = 120                # seconds
    pipeline_timeout: int = 600                    # seconds, 10 min
    pipeline_step_timeout: int = 60                # seconds within supervisor
    max_rewrite_attempts: int = 2
    review_pass_threshold: int = 70
    tavily_results_per_query: int = 5
    evidence_card_min_count: int = 3
    clarifier_mode: Literal["interactive", "auto_resolve"] = "auto_resolve"
    isolation_level: Literal["strict", "relaxed"] = "strict"
    cost_per_call_estimate: float = 0.001          # USD


class RunContext(BaseModel):
    """Immutable context shared across all agents."""
    session_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=datetime.utcnow)
    research_brief: "ResearchBrief | None" = None
    config: RunConfig = Field(default_factory=RunConfig)


# -- Triage --

class TriageInput(BaseModel):
    query: str
    conversation_history: list[dict] = []
    interactive: bool = True


class TriageDecision(BaseModel):
    route: Literal["clarify", "direct_to_research"]
    clarity_flags: list[str] = []
    suggested_clarifications: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_depth: Literal["quick", "standard", "deep"] = "standard"


# -- Clarifier --

class ClarifierTurn(BaseModel):
    question: str
    options: list[str] = []
    rationale: str = ""


class ClarifierResult(BaseModel):
    clarified_query: str
    answered_questions: list[dict] = []
    auto_resolved: bool = False


# -- Instruction Builder --

class ResearchBrief(BaseModel):
    """The distilled research mandate -- replaces raw user query.
    Validated with business-rule checks after LLM generation.
    """
    clarified_question: str
    time_range: str = "recent"
    geo_focus: str = "global"
    format_preference: Literal["report", "comparison", "analysis", "summary"] = "report"
    constraints: list[str] = []
    depth_indicator: Literal["quick", "standard", "deep"] = "standard"
    seed_subquestions: list[str] = []
    target_audience: str = "general"
    special_instructions: str = ""

    @model_validator(mode="after")
    def validate_seed_subquestions(self) -> "ResearchBrief":
        if not self.seed_subquestions:
            self.seed_subquestions = [self.clarified_question]
        return self

    @model_validator(mode="after")
    def validate_depth_consistency(self) -> "ResearchBrief":
        if self.depth_indicator == "quick" and len(self.seed_subquestions) > 3:
            self.seed_subquestions = self.seed_subquestions[:3]
        return self


# -- Supervisor --

class SubQuestionEntry(BaseModel):
    id: str
    question: str
    rationale: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    search_count: int = 0
    extracts_count: int = 0
    card_count: int = 0
    result: "AgentResult | None" = None


class SubQuestionRegistry(BaseModel):
    entries: list[SubQuestionEntry] = []

    def get_entry(self, id: str) -> SubQuestionEntry | None:
        for e in self.entries:
            if e.id == id:
                return e
        return None


class SupervisorAction(BaseModel):
    action: Literal["start_agent", "check_progress", "reassign", "finalize"]
    subquestion_ids: list[str] = []
    rationale: str = ""


# -- Sub-Research Agent --

class AgentStep(BaseModel):
    iteration: int
    action: str
    query: str = ""
    result_summary: str = ""
    urls: list[str] = []
    contradictions_found: list[str] = []


class AgentResult(BaseModel):
    subquestion_id: str
    subquestion: str
    search_results: list["SearchResult"] = []
    evidence_cards: list["EvidenceCard"] = []
    visited_urls: list[str] = []
    errors: list[str] = []
    token_usage: list["TokenUsage"] = []
    steps: list[AgentStep] = []
    saturated: bool = False
    contradictions_found: list[str] = []


# -- Evidence Consolidator --

class Contradiction(BaseModel):
    topic: str
    claim_a: str
    agent_a: str
    source_a: str
    claim_b: str
    agent_b: str
    source_b: str
    explanation: str = ""


class ConsolidatedEvidence(BaseModel):
    evidence_cards: list["EvidenceCard"] = []
    contradictions: list[Contradiction] = []
    cross_agent_corroborations: int = 0
    quality_scores: dict[str, float] = {}
    coverage_gaps: list[str] = []
    pre_write_warnings: list[str] = []
    blocked: bool = False


# -- Review --

class ReviewRubric(BaseModel):
    factual_accuracy: int = Field(ge=0, le=100)
    coverage_completeness: int = Field(ge=0, le=100)
    reasoning_quality: int = Field(ge=0, le=100)
    citation_quality: int = Field(ge=0, le=100)
    clarity_structure: int = Field(ge=0, le=100)


class ReviewResult(BaseModel):
    rubric: ReviewRubric
    composite_score: int = Field(ge=0, le=100)
    passed: bool = False
    issues: list[str] = []
    suggestions: list[str] = []
    can_improve: bool = True


# -- Pipeline Output --

class PipelineResult(BaseModel):
    report: str = ""
    review: ReviewResult | None = None
    evidence: ConsolidatedEvidence | None = None
    brief: ResearchBrief | None = None
    session_id: str = ""
    iterations: int = 0
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    errors: list[str] = []
```

---

## 9. Comparison Matrix: V2 vs V3

This matrix has been corrected from the original draft. Several features previously marked as "New in V3" already exist in V2/graph_v2. The corrected matrix accurately reflects what each version provides.

| Dimension | V2 (graph_v2 + coordinator) | V3 (Multi-Agent Pipeline) | Rationale |
|-----------|----------------------------|---------------------------|-----------|
| **Architecture** | LangGraph StateGraph with 5 nodes (plan, run_agents, coordinator, write, save) | 8 explicit agents (Triage, Clarifier, Builder, Supervisor, Sub-AgentxN, Consolidator, Writer, Reviewer) | More explicit roles, but core research flow is similar to graph_v2 |
| **Triage / Clarification** | None -- raw query goes directly to planner | Triage Agent + Clarifier Agent (0-3 rounds or auto-resolve) | **Truly new**: V2 has no query triage |
| **Research Brief** | None -- raw `question` string passed everywhere | ResearchBrief Pydantic with business-rule validation | **Truly new**: V2 has no context compression layer |
| **Context Engineering** | None -- full workspace passed every iteration (react_v2) or subquestions passed to agents (graph_v2) | ResearchBrief compression, per-agent context isolation, sub-agent pruning | Formalized in V3, partially present in graph_v2 (subquestion isolation) |
| **Parallel Research** | graph_v2: ThreadPoolExecutor parallel subquestion agents | Parallel sub-agents with Supervisor lifecycle, budget control, thread safety | V2 has the foundation; V3 adds explicit management |
| **Cross-Validation** | Per-subquestion + Cross-subquestion via coordinator.py | Same logic, reused from V2, with added coverage gap analysis | Already in V2, V3 enhances |
| **Contradiction Detection** | Hybrid: Jaccard fast filter + LLM semantic classification (coordinator.py) | Same hybrid approach, inherited from V2 | Already in V2, V3 reuses unchanged |
| **Report Generation** | build_writing_prompt + validate_citations + 1 rewrite | Same code, same reuse | **Unchanged** from V2 |
| **Report Review** | `_critique_report()` -- single LLM call, logs to errors, no rewrite (react_v2.py) | Multi-dimension rubric (5 axes), 70% threshold, up to 2 rewrites | **Truly new**: V2's critic is passive, V3's is actionable |
| **Pre-write Validation** | None -- evidence goes directly to Writer | Pre-write gate in Consolidator: blocks on critical contradictions | **Truly new**: prevents wasted writers |
| **Tool System** | ToolRegistry with register/execute/describe | Same ToolRegistry, extended with optional MCP server support | **Evolutionary**: backward-compatible extension |
| **Token Usage Tracking** | Full tracking in react_v2.py, graph_v2.py, subquestion_agent.py | Same pattern, enforced at every LLM call | Already in V2, V3 fixes original omission |
| **Budget Control** | max_iterations=15 + dry_rounds=3 (react_v2.py) or search-based (graph_v2) | total_llm_call_budget + per_subagent_timeout + pipeline_timeout + depth tiers | **Truly new**: explicit budget enforcement |
| **Thread Safety** | Fire-and-forget parallelism (graph_v2), no concurrent state | threading.Lock on Supervisor registry, timeout on futures | V3 addresses a problem V2 avoids by design |
| **Clarifier non-interactive** | N/A (no Clarifier) | clarifier_mode: auto_resolve with defaults | **Truly new**: necessary for API compatibility |
| **State Model** | ResearchState TypedDict | RunContext + per-stage models | V3's typed interfaces are more maintainable |
| **Decision Logging** | DecisionLogger (JSONL) | Same DecisionLogger, extended with `agent` field | Backward compatible |
| **Research Memory** | ResearchMemory singleton | Same singleton | **Unchanged**, shared across V2 and V3 |
| **Configuration** | AppConfig (dataclass) | RunConfig (Pydantic) + env-based AppConfig | Schema validation |
| **Error Handling** | Inline try/except, dry-round detection | Per-agent error boundary, Supervisor-level termination, pre-pipeline budget check | More layered in V3 |
| **Streaming Output** | Generator per phase | Generator per stage (same SSE pattern) | Same mechanism |
| **Config File** | pyproject.toml | pyproject.toml (same) | Unchanged |

### What V3 Preserves from V2 (unchanged)

| Component            | File                       | Status     |
|----------------------|----------------------------|------------|
| LLMClient protocol   | `clients/llm.py`           | Unchanged  |
| DeepSeekLLMClient    | `clients/llm.py`           | Unchanged  |
| TavilySearchClient   | `clients/tavily.py`        | Unchanged  |
| SubQuestion          | `state.py`                 | Reused     |
| SearchResult         | `state.py`                 | Reused     |
| EvidenceCard         | `state.py`                 | Reused     |
| ExtractedClaim       | `state.py`                 | Reused     |
| ExtractedSource      | `state.py`                 | Reused     |
| TokenUsage, UsageInfo| `state.py`                 | Reused     |
| Tool protocol        | `tools/base.py`            | Unchanged  |
| ToolResult           | `tools/base.py`            | Unchanged  |
| TavilySearchTool     | `tools/tavily_search.py`   | Reused     |
| WebFetchTool         | `tools/web_fetch.py`       | Reused     |
| TavilyExtractTool    | `tools/tavily_extract.py`  | Reused     |
| CompareSourcesTool   | `tools/compare_sources.py` | Reused     |
| FactCheckTool        | `tools/fact_check.py`      | Reused     |
| build_writing_prompt | `prompts/writing.py`       | Reused     |
| validate_citations   | `citations.py`             | Reused     |
| build_extraction_prompt | `prompts/extraction.py`  | Reused     |
| build_validation_prompt | `prompts/evidence.py`    | Reused     |
| CoordinatorResult    | `agents/coordinator.py`    | Consolidator reuses this logic |
| Contradiction        | `agents/coordinator.py`    | Reused     |
| coordinate()         | `agents/coordinator.py`    | Consolidator calls this |
| DecisionLogger       | `utils/decision_log.py`    | Reused (extended with agent field) |
| ResearchMemory       | `utils/research_memory.py` | Reused     |
| SearchCache          | `utils/search_cache.py`    | Reused     |

### What V3 Changes from V2

| Component               | V2 Behavior                                      | V3 Behavior                                                      |
|-------------------------|--------------------------------------------------|------------------------------------------------------------------|
| Agent entry point       | `ReActV2Agent.run(question)` or LangGraph app    | `V3Pipeline.run(query)` -- orchestrates all agents              |
| Triage                  | None                                             | TriageAgent + ClarifierAgent (interactive or auto-resolve)       |
| Instruction building    | None (raw question)                              | InstructionBuilder -> ResearchBrief with validation               |
| Supervisor              | graph_v2: fire-and-forget ThreadPoolExecutor     | Explicit lifecycle, budget watch, thread safety, timeouts        |
| Pre-write validation    | None                                             | Consolidator with pre-write gate                                  |
| Report review           | _critique_report() logs to errors, no rewrite    | MultiDimensionReviewer with rewrite loop                          |
| Budget control          | Implicit (max_iterations / dry_rounds)           | Explicit (total_llm_call_budget + timeouts)                       |
| Tool system             | ToolRegistry only                                | Extended ToolRegistry + optional MCP support                      |
| Runner integration      | build_agent() with 6 branches                    | +1 branch via architecture registry (Phase 0 prerequisite)        |

### What V3 Removes (Not in V2)

| Feature                                    | Why Removed                                                  |
|--------------------------------------------|--------------------------------------------------------------|
| `TopicState.open_questions` / `resolved_questions` | Replaced by Supervisor's status tracking for subquestions   |
| `ResearchNote` dataclass                   | Replaced by EvidenceCard (more structured, typed)            |
| `_auto_manage_workspace()`                 | Supervisor handles saturation detection with LLM awareness   |
| `_update_question_pool()`                  | Question pool concept replaced by SubQuestionRegistry        |
| LangGraph dependency for agent orchestration | V3 uses built-in async orchestration (no LangGraph StateGraph) |
| Fire-and-forget parallelism                | V3 uses managed futures with timeout and state tracking      |

---

## 10. Implementation Path

### Package Structure

```
src/deepresearch/agents/react_v3/
+-- __init__.py
+-- models.py              # Pydantic models for all V3 agents
+-- triage.py              # TriageAgent
+-- clarifier.py           # ClarifierAgent (interactive + auto_resolve)
+-- instruction_builder.py # InstructionBuilderAgent (with validation)
+-- supervisor.py          # ResearchSupervisor (thread-safe, budget-aware)
+-- sub_agent.py           # SubResearchAgent (with TokenUsage tracking)
+-- consolidator.py        # EvidenceConsolidator (with pre-write gate)
+-- writer.py              # WritingAgent (wraps V2's build_writing_prompt)
+-- reviewer.py            # MultiDimensionReviewer
+-- pipeline.py            # V3Pipeline orchestrator
+-- mcp_tool.py            # MCPToolAdapter (Phase 5, optional)
```

### Phase Plan

#### Phase 0: Prerequisite -- Refactor build_agent() (Week 0)

- [ ] Refactor `runner.py`'s `build_agent()` from a 243-line single function with branching to a strategy/plugin pattern
- [ ] Each architecture implements `ResearchArchitecture` protocol with `build(config) -> Callable`
- [ ] Register architectures via `ARCHITECTURE_REGISTRY: dict[str, type[ResearchArchitecture]]`
- [ ] V2 and V3 both use the same registry -- no special-casing
- [ ] Write tests for the registry (test_architecture_registry.py)
- [ ] **Critical dependency**: No V3 code can be merged without this refactoring

```python
# New pattern for runner.py

class ResearchArchitecture(Protocol):
    """Each architecture implements this protocol."""
    name: str

    def build(self, llm, search, config, **kwargs) -> Callable[[str], ResearchState]:
        ...

# Registry
ARCHITECTURE_REGISTRY: dict[str, type[ResearchArchitecture]] = {}

def register(cls):
    ARCHITECTURE_REGISTRY[cls.name] = cls
    return cls

@register
class PipelineArchitecture(ResearchArchitecture):
    name = "pipeline"
    def build(self, llm, search, config, **kwargs) -> Callable:
        ...

@register
class ReactV2Architecture(ResearchArchitecture):
    name = "react-v2"
    def build(self, llm, search, config, **kwargs) -> Callable:
        ...

@register
class ReactV3Architecture(ResearchArchitecture):
    name = "react-v3"
    def build(self, llm, search, config, **kwargs) -> Callable:
        ...

def build_agent(*, architecture="pipeline", **kwargs):
    cls = ARCHITECTURE_REGISTRY.get(architecture)
    if cls is None:
        raise ValueError(
            f"Unknown architecture: {architecture}. "
            f"Available: {list(ARCHITECTURE_REGISTRY)}"
        )
    return cls().build(**kwargs)
```

#### Phase 1: Foundation (Week 1)

- [ ] Create `agents/react_v3/` package with `models.py`
- [ ] Implement `RunConfig`, `RunContext`, all Pydantic models (with ResearchBrief validation)
- [ ] Extend `ToolRegistry` in `tools/registry.py` with MCP support (backward-compatible)
- [ ] Implement cost projection: `_project_cost()` for pre-pipeline budget check
- [ ] Register `"react-v3"` in architecture registry (Phase 0 prerequisite)
- [ ] Write unit tests for all models (test_react_v3_models.py)

#### Phase 2: Core Agents (Week 2)

- [ ] Implement `TriageAgent` (with interactive flag) + tests
- [ ] Implement `InstructionBuilderAgent` (with ResearchBrief validation + retry) + tests
- [ ] Implement `SubResearchAgent` (inherits search-extract-validate from V2, adds iteration loop, saturation detection, TokenUsage tracking, contradiction preservation) + tests

#### Phase 3: Coordination (Week 3)

- [ ] Implement `ResearchSupervisor` (thread-safe, budget-aware, timeout-aware) + tests
- [ ] Implement `EvidenceConsolidator` (reuses V2's coordinator.py logic, adds pre-write gate) + tests
- [ ] Implement `WritingAgent` (wraps `build_writing_prompt` + `validate_citations`, adds pre-write warning awareness) + tests
- [ ] Implement `MultiDimensionReviewer` (with rewrite loop, composite scoring) + tests

#### Phase 4: Pipeline + Integration (Week 4)

- [ ] Implement `V3Pipeline` orchestrator (with budget projection, pre-write gate, error boundaries)
- [ ] Implement `ClarifierAgent` (interactive CLI + auto-resolve mode)
- [ ] Add streaming SSE events to pipeline
- [ ] Integration tests with fake LLM/Search clients
- [ ] CLI integration via architecture registry

#### Phase 5: Production Readiness (Week 5)

- [ ] Online testing with real DeepSeek + Tavily
- [ ] Benchmark vs V2 on same queries (quality + cost + wall-clock)
- [ ] DecisionLogger integration (add `agent` field)
- [ ] ResearchMemory integration (Supervisor reads, does not write)
- [ ] Documentation updates
- [ ] MCPToolAdapter (if MCP servers available -- optional, deferred from Phase 1)

### Migration Strategy

1. **Coexistence:** V2 and V3 run side-by-side as two architectures in the strategy registry. User chooses with `--architecture react-v2` (default) or `--architecture react-v3`.

2. **Shared Core:** Both modes share the same tools, clients, state types, prompts, validation code, coordinator logic, and subquestion agent code. V3 only adds code; it never changes V2's.

3. **Gradual Default Shift:** After Phase 5 benchmarks confirm V3 quality >= V2 at comparable or better cost, change the CLI default to `react-v3`.

4. **V2 Deprecation:** After 2 months of stable V3 production use, mark V2 as deprecated. Keep the code for 6 months for rollback.

### Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Parallel sub-agents exceed API rate limits | High | Use TavilyKeyPool (already exists); configurable `max_parallel_agents`; retry with backoff |
| LLM call cost higher than V2 | Medium-High | Budget gate pre-pipeline; tiered depth modes with enforced call limits; monitor per-call token counts; abort if projected cost > budget |
| Context isolation loses cross-subquestion serendipity | Medium | Consolidator explicitly re-correlates; `isolation_level = "relaxed"` option; coverage_gaps flagging |
| Clarifier agent blocks in API mode | Critical (fixed) | `clarifier_mode: "auto_resolve"` provides non-interactive fallback with sane defaults |
| Supervisor race conditions | Critical (fixed) | `threading.Lock` on all registry mutations; timeouts on futures |
| Sub-agent hangs/stalls | Medium | `per_subagent_timeout` (120s); `pipeline_step_timeout` (60s); slot release on timeout |
| build_agent() maintainability | Medium | **Phase 0 prerequisite**: refactor to strategy/plugin pattern before V3 code is added |
| ResearchBrief validation failure | Medium | 1 retry with LLM + error feedback; if second failure, fall back to safe defaults |
| MCP tool adapter unused complexity | Low | **Deferred to Phase 5**: no MCP code in Phase 1-4; existing ToolRegistry handles everything |
| Pre-write gate blocks valid research | Low | Only blocks on critical contradictions; warnings pass through; Writer can still produce output with caveats |

---

## Appendix A: Key Prompt Design Principles

```
+-----------------------------------------------------------+
|                Prompt Design Principles                     |
+-----------------------------------------------------------+
| 1. Each agent prompt contains ONLY the context it needs    |
| 2. Every prompt ends with "Return JSON ONLY:"              |
| 3. JSON schema is included in the prompt                   |
| 4. Examples are shown inline for complex structures        |
| 5. Instructions use imperative, bullet-point format        |
| 6. No conversation history -- all context is structured    |
| 7. Output format is validated with Pydantic                |
| 8. Failed parsing forces a retry (max 2) with error msg    |
| 9. ResearchBrief validation errors are passed back to      |
|    the LLM for self-correction on retry                    |
+-----------------------------------------------------------+
```

## Appendix B: Streaming Event Protocol

```
V3Pipeline events for SSE:

{"type": "phase",     "data": {"phase": "triage",         "message": "Analyzing query..."}}
{"type": "phase",     "data": {"phase": "clarify",        "message": "Need more details..."}}
{"type": "clarify",   "data": {"question": "...", "options": ["...", "..."], "round": 1, "mode": "interactive|auto_resolve"}}
{"type": "phase",     "data": {"phase": "build",          "message": "Building research brief..."}}
{"type": "budget",    "data": {"projected_calls": 12, "budget": 18, "proceed": true}}
{"type": "phase",     "data": {"phase": "research",       "message": "Researching 3 topics..."}}
{"type": "sub_start", "data": {"subquestion_id": "q1", "question": "..."}}
{"type": "sub_search","data": {"subquestion_id": "q1", "query": "..."}}
{"type": "sub_card",  "data": {"subquestion_id": "q1", "count": 5}}
{"type": "sub_done",  "data": {"subquestion_id": "q1", "cards": 7, "urls": 12, "calls": 4}}
{"type": "sub_timeout","data": {"subquestion_id": "q4", "timeout": 120}}
{"type": "phase",     "data": {"phase": "consolidate",    "message": "Cross-validating evidence..."}}
{"type": "gate",      "data": {"blocked": false, "warnings": ["1 contradiction detected"], "gaps": []}}
{"type": "phase",     "data": {"phase": "writing",        "message": "Writing report..."}}
{"type": "token",     "data": {"text": "..."}}              # streaming report tokens
{"type": "phase",     "data": {"phase": "review",         "message": "Reviewing report..."}}
{"type": "review",    "data": {"rubric": {...}, "composite": 85, "passed": true}}
{"type": "done",      "data": {"iterations": 15, "total_llm_calls": 14, "total_tokens": 45000, "total_cost": 0.18}}
```

## Appendix C: Comparison with LangChain OpenDeepResearch

| Dimension | LangChain OpenDeepResearch | React V3 |
|-----------|---------------------------|-----------|
| **Architecture** | Parallel supervisor + sub-research agents | 8 explicit agents with typed interfaces |
| **Subquestion decomposition** | LLM generates subquestions, supervisor assigns | ResearchBrief provides seed_subquestions, LLM expands |
| **Parallel execution** | asyncio-based, event loop | ThreadPoolExecutor with thread-safe supervisor |
| **Evidence consolidation** | Not explicitly documented as a separate phase | Formal Consolidator with coverage gaps, quality scores, pre-write gate |
| **Report review** | Not publicly documented | 5-dimension rubric with rewrite loop, composite scoring |
| **Triage/Clarification** | None (assumes clear query) | TriageAgent + ClarifierAgent with non-interactive fallback |
| **Context Engineering** | Subquestion isolation at research time | Four-level isolation (query compression, brief isolation, subquestion isolation, evidence isolation) |
| **Pruning** | Not documented | Sub-agent history pruning with contradiction preservation |
| **Budget control** | Not documented in public materials | total_llm_call_budget, per_subagent_timeout, pipeline_timeout, pre-run cost projection |
| **Thread safety** | asyncio avoids shared state issues | threading.Lock for concurrent state mutations |
| **MCP integration** | Native LangChain tool system | Extended ToolRegistry with deferred MCP adapter |
| **Non-interactive mode** | API-compatible by design | explicit clarifier_mode: auto_resolve |
| **Pre-write validation** | Not documented | Pre-write gate: blocks on critical contradictions |

**V3's differentiators from OpenDeepResearch:**
1. Multi-dimensional review with rewrite loop (OpenDeepResearch does not publicly document report quality gates)
2. Pre-write validation gate that prevents wasted generation on contradictory evidence
3. Non-interactive fallback for API/headless operation
4. Explicit cost budgeting with pre-run projection
5. Business-rule validated ResearchBrief as context compression layer

---

## 11. Revision Log

| Date       | Author              | Change                        | Reference        |
|------------|---------------------|-------------------------------|------------------|
| 2026-06-18 | V3 Design Team      | Initial draft                 | --               |
| 2026-06-18 | V3 Design Team      | Revision 1 (Griller review)   | 15 issues resolved |

### Issue Responses (Griller Review v1)

| #  | Issue                                                      | Severity | Verdict           | Summary of Change                                               |
|----|------------------------------------------------------------|----------|-------------------|----------------------------------------------------------------|
| 1  | SubResearchAgent missing TokenUsage tracking               | Critical | Accept & Modify   | Added TokenUsage tracking to every LLM call in sub-agent        |
| 2  | Clarifier no non-interactive fallback                      | Critical | Accept & Modify   | Added `clarifier_mode` to RunConfig; auto-resolve with defaults |
| 3  | Missing LLM Call Budget and pipeline timeout               | Major    | Accept & Modify   | Added `total_llm_call_budget`, timeouts to RunConfig            |
| 4  | Supervisor concurrent state update race condition          | Critical | Accept & Modify   | Added `threading.Lock` to Supervisor                            |
| 5  | Cross-agent tool sharing breaks context isolation          | Critical | Accept & Modify   | Documented shared state paths; added `isolation_level` config   |
| 6  | Sub-agent history pruning loses contradictions             | Major    | Accept & Modify   | `prune_subagent_history()` now preserves contradictions         |
| 7  | build_agent() function bloat                               | Critical | Accept & Modify   | Added Phase 0 prerequisite: strategy/plugin refactoring         |
| 8  | 12-40 LLM calls economics unsustainable                    | Critical | Accept & Modify   | Revised estimate to 8-28; added budget enforcement; cost calc   |
| 9  | MCPToolRegistry incompatibility with existing ToolRegistry | Major    | Accept & Defer    | Extended existing ToolRegistry; deferred MCP to Phase 5          |
| 10 | Multiple "New in V3" features already exist in V2          | Critical | Accept & Modify   | Corrected all claims in Comparison Matrix (Section 9)           |
| 11 | Context Isolation vs Consolidator serendipity tension      | Major    | Accept & Modify   | Added tension analysis (Section 7); configurable isolation      |
| 12 | No OpenDeepResearch comparison                             | Minor    | Accept & Add      | Added Appendix C                                                 |
| 13 | ResearchBrief validation missing                            | Critical | Accept & Modify   | Added business-rule validators with retry-on-failure             |
| 14 | Sub-agent no deadlock/timeout detection                    | Major    | Accept & Modify   | Added `concurrent.futures.timeout`; slot release on timeout      |
| 15 | Writer has no fact-check before writing                    | Major    | Accept & Modify   | Added pre-write validation gate in Consolidator                 |

**Summary:** 13/15 issues accepted and modified, 1 deferred (MCPToolAdapter to Phase 5), 1 accepted and added (OpenDeepResearch comparison). No issues rejected.

---

## Document Metadata

| Property    | Value                                        |
|-------------|----------------------------------------------|
| Version     | v1.0                                         |
| Status      | Final -- passed 1 round of design review     |
| Filename    | `docs/architecture-v3.md`                    |
| Author      | React V3 Architecture Team                   |
| Reviewed by | Griller review v1 (15 issues, all resolved)  |
| Last updated | 2026-06-18                                  |
| Supersedes  | Initial draft (pre-griller)                  |
| Next review | After Phase 2 implementation (Week 2)        |
