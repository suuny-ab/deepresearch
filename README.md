# Deep Research Agent

> **AI-powered LangGraph research agent with three execution modes: pipeline, multi-agent, and ReAct.** Two-phase evidence pipeline for hallucination reduction, cross-source claim validation, automated citation verification, and a 15-dimension quality evaluation framework.
> 100% citation compliance  · 84/100 avg review score  · 195 offline tests  · Zero-LLM evaluators

## Why This Project Matters

Building an LLM-powered research agent isn't just about calling an API — it's about solving the inherent problems of non-deterministic systems:

1. **LLMs hallucinate URLs** → Strict `[N]` citation contract with 7-dimension validator + auto-rewrite
2. **Extraction and validation conflict** → Two-phase evidence pipeline (extract first, validate second)
3. **Source authority can't be hardcoded** → Cross-validation replaces domain scoring: "these independent sources agree" > "this domain is trustworthy"
4. **Evaluation is the hard problem** → 15 deterministic (zero-LLM) evaluators + LangSmith tracing

## Execution Modes

```bash
# 1. Pipeline — fast, deterministic 6-step flow
uv run deepresearch "AI 搜索引擎趋势" --architecture pipeline

# 2. Multi-Agent — each subquestion gets its own parallel agent
uv run deepresearch "LangGraph vs CrewAI 技术选型" --architecture multi-agent

# 3. ReAct — autonomous agent with tool-calling loop
uv run deepresearch "固态电池商业化进展" --architecture react
```

## Architecture

```
Pipeline mode:   plan → search → evidence(2-phase) → write → review ⇄ save
Multi-Agent:     plan → [Agent₁ | Agent₂ | Agent₃] → coordinator → write → review ⇄ save
ReAct:           Think ⇄ Act(search/fetch/write) — autonomous tool-calling loop
```

## Evidence Pipeline

The core insight: **extraction and cross-validation are conflicting cognitive tasks**. Extraction wants divergence (capture everything); cross-validation wants convergence (be conservative about claiming corroboration). One LLM call doing both produces timid output.

```
Phase 1: Extract claims from all sources (1 LLM call, no validation instruction)
Phase 2: Per-subquestion cross-validation (N parallel LLM calls)
Post-validation: Code-level boundary checks (domain diversity, URL validity)
```

EvidenceCards include `corroboration_level`: **single_source** | **weakly_corroborated** | **strongly_corroborated**

## Key Design Decisions

| Decision | Why |
|----------|-----|
| Two-phase evidence pipeline | Extract claims first, then cross-validate — eliminates task conflict |
| Cross-validation over source scoring | "3 independent domains agree" > "this domain scores 95" |
| Subquestion-level agent isolation | One agent crash doesn't kill the whole research |
| 7-dimension citation validator | Body citations, source URLs, bare URLs, unused sources, etc. |
| Auto-rewrite on citation failure | Saves human from debugging LLM output formatting |
| Review feedback loop (score < 70) | Review isn't just observability — it triggers action |
| Deleted 30% self-built infra for LangSmith | Solo projects should focus on Agent quality, not platform |
| 15 deterministic evaluators | Zero-LLM metrics: citation compliance, source utilization, corroboration rates |
| Thread-safe parallel execution | Phase 2 validation + multi-agent search run concurrently |
| Per-node token cost tracking | Know exactly what each pipeline stage costs |

## Benchmark Results (v0.6.0)

| Metric | Value |
|--------|-------|
| Citation pass rate | **100%** (3/3 questions) |
| Average review score | **84.0** |
| Avg claims per source | **2.85** |
| Avg evidence cards | **28** |
| Strong corroboration | 3.8% |
| Weak corroboration | 25.3% |

### Citation Accuracy (FACT)

Validates whether cited sources actually support the claims made in the report — scrapes each URL and uses DeepSeek to verify.

| Architecture | Citations Checked | Verified Correct | Accuracy |
|---|---|---|---|
| Pipeline | 31 | 7 | 22.6% |
| Multi-Agent | 26 | 24 | **92.3%** |
| ReAct | 27 | 8 | 29.6% |

## Setup

```bash
uv sync
cp .env.example .env
# Fill in DEEPSEEK_API_KEY, TAVILY_API_KEY
```

## Observability

LangSmith auto-traces every node: inputs, outputs, LLM token usage, and latency.
Set `LANGCHAIN_API_KEY` in `.env` to enable.

## Test

```bash
uv run pytest                    # 195 offline tests, <2s, zero API calls
```


## Tech Stack

Python · LangGraph · DeepSeek · Tavily · Pydantic · Typer · Rich · pytest · LangSmith

**Project structure (source):**
```

src/deepresearch/
├── agents/          # Multi-agent & ReAct implementations
├── clients/         # LLM (DeepSeek) + search (Tavily) clients
├── nodes/           # LangGraph pipeline nodes
├── prompts/         # Task-specific prompt templates
├── tools/           # Tool definitions (search, fetch, fact-check)
├── utils/           # Report writing, caching, URL handling
├── cli.py           # Typer CLI entry point
├── config.py        # Environment-based configuration
├── graph.py         # Pipeline StateGraph
├── graph_multi_agent.py  # Multi-agent graph
├── runner.py        # Agent builder (dependency injection)
├── state.py         # Pydantic state models
├── evaluators.py    # 15 deterministic quality evaluators
├── citations.py     # 7-dimension citation validator
└── errors.py        # Typed error hierarchy
```
