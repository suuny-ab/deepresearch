# Deep Research Agent v0.3.1 Subquestion Context + Dry-Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pass subquestion research intent into the evidence extraction prompt, and add a `--dry-run` flag that stops after `prepare_evidence` for fast A/B testing of evidence extraction changes.

**Architecture:** Two independent changes. (1) `build_evidence_prompt` gains a `subquestions` parameter; sources are grouped by subquestion with question text as section headers. `prepare_evidence` passes subquestions from state. (2) `build_research_graph` gains a `dry_run` parameter; when True, the graph edge from `prepare_evidence` goes to END. CLI prints evidence card summary instead of full report.

**Tech Stack:** Python 3.11+, Pydantic, LangGraph, pytest

---

## File Structure Changes

**Modify:**
```text
src/deepresearch/prompts/evidence.py       — add subquestions param, group sources by subquestion
src/deepresearch/nodes/prepare_evidence.py — pass subquestions to build_evidence_prompt
src/deepresearch/graph.py                  — add dry_run parameter
src/deepresearch/cli.py                    — add --dry-run flag, print evidence summary
tests/test_evidence_prompt.py              — update tests for new prompt structure
tests/test_prepare_evidence_node.py        — update test for subquestion passing
tests/test_graph_structure.py              — add dry_run graph test
tests/test_cli.py                          — add dry-run cli test
```

---

### Task 0: Pre-check

**Files:**
- No file changes.

- [ ] **Step 1: Check git status**

Run:
```bash
git status --short
```

Expected: clean.

- [ ] **Step 2: Run current tests**

Run:
```bash
uv run pytest -v
```

Expected: all 124 pass.

- [ ] **Step 3: No commit**

---

### Task 1: Update evidence prompt to accept and display subquestion context

**Files:**
- Modify: `src/deepresearch/prompts/evidence.py`
- Modify: `tests/test_evidence_prompt.py`

- [ ] **Step 1: Replace test_evidence_prompt.py**

Replace the full content of `tests/test_evidence_prompt.py`:

```python
from deepresearch.prompts.evidence import build_evidence_prompt
from deepresearch.state import ExtractedSource, SubQuestion


def test_evidence_prompt_requires_evidence_cards():
    source = ExtractedSource(
        subquestion_id="q1",
        url="https://example.com/a",
        title="Source A",
        raw_content="RAG remains important for AI search.",
    )
    subquestions = [
        SubQuestion(id="q1", question="What is AI search?", search_query="q", search_queries=["q"], rationale="r"),
    ]

    prompt = build_evidence_prompt("AI search", [source], subquestions)

    assert "EvidenceCard" in prompt
    assert "supporting_snippet" in prompt
    assert "Do not create claims not supported by the source text" in prompt
    assert "https://example.com/a" in prompt


def test_evidence_prompt_includes_cross_validation_instructions():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="RAG remains important.",
        ),
        ExtractedSource(
            subquestion_id="q1",
            url="https://other.example/b",
            title="Source B",
            raw_content="RAG is still important for search.",
        ),
    ]
    subquestions = [
        SubQuestion(id="q1", question="What is AI search?", search_query="q", search_queries=["q"], rationale="r"),
    ]

    prompt = build_evidence_prompt("AI search", sources, subquestions)

    assert "corroboration_level" in prompt
    assert "single_source" in prompt
    assert "weakly_corroborated" in prompt
    assert "strongly_corroborated" in prompt
    assert "different domain" in prompt.lower() or "DIFFERENT domain" in prompt
    assert "corroborating_sources" in prompt


def test_evidence_prompt_groups_sources_by_subquestion():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="RAG is important.",
        ),
        ExtractedSource(
            subquestion_id="q2",
            url="https://other.example/b",
            title="Source B",
            raw_content="AI search market growing.",
        ),
    ]
    subquestions = [
        SubQuestion(id="q1", question="Core tech trends?", search_query="q1", search_queries=["q1"], rationale="tech"),
        SubQuestion(id="q2", question="Market competition?", search_query="q2", search_queries=["q2"], rationale="market"),
    ]

    prompt = build_evidence_prompt("AI search", sources, subquestions)

    # Subquestion text appears in prompt
    assert "Core tech trends?" in prompt
    assert "Market competition?" in prompt

    # Sources appear grouped under their subquestions
    assert "q1:" in prompt
    assert "q2:" in prompt

    # Source URLs appear
    assert "https://example.com/a" in prompt
    assert "https://other.example/b" in prompt


def test_evidence_prompt_backward_compatible_with_no_subquestions():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="Content.",
        ),
    ]

    prompt = build_evidence_prompt("AI search", sources, subquestions=[])

    assert "https://example.com/a" in prompt
    assert "EvidenceCard" in prompt
```

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_evidence_prompt.py -v
```

Expected: `TypeError` — `build_evidence_prompt()` got unexpected keyword argument `subquestions`.

- [ ] **Step 3: Update evidence prompt**

Replace `src/deepresearch/prompts/evidence.py`:

```python
from deepresearch.state import ExtractedSource, SubQuestion


def build_evidence_prompt(
    question: str,
    sources: list[ExtractedSource],
    subquestions: list[SubQuestion],
) -> str:
    # Build subquestion lookup
    sq_map: dict[str, str] = {
        sq.id: sq.question for sq in subquestions
    }

    # Group sources by subquestion
    groups: dict[str, list[ExtractedSource]] = {}
    for source in sources:
        key = source.subquestion_id
        groups.setdefault(key, []).append(source)

    # Build subquestion overview
    subquestion_lines = []
    if subquestions:
        subquestion_lines.append("Research subquestions:")
        for sq in subquestions:
            subquestion_lines.append(f"- [{sq.id}] {sq.question}")
        subquestion_lines.append("")

    # Build grouped source listing
    source_lines = []
    source_lines.append("Sources (grouped by subquestion):")
    for sq_id, group_sources in groups.items():
        sq_question = sq_map.get(sq_id, sq_id)
        source_lines.append(f"--- {sq_id}: {sq_question} ---")
        for source in group_sources:
            source_lines.append(f"  URL: {source.url}")
            source_lines.append(f"  Title: {source.title}")
            source_lines.append(f"  Content ({source.format}): {source.raw_content}")
            source_lines.append("")
    source_lines.append("---")

    grouped_sources = "\n".join(source_lines)
    subquestion_overview = "\n".join(subquestion_lines)

    return f"""
You extract EvidenceCard objects from source text for a research report.
Do not create claims not supported by the source text.
Every claim must be grounded in a supporting_snippet copied or closely paraphrased from the source text.
Each EvidenceCard must copy the supplied `url` value into EvidenceCard `source_url`.
If the source text is weak, thin, or only a search snippet, use low confidence.

The sources below are organized by subquestion. Each source was retrieved
to answer a specific subquestion, shown in the group header.
Use this structure to understand the research intent behind each source
when deciding whether two sources from DIFFERENT subquestions are truly
corroborating the same claim, or merely discussing related topics from
different angles.

{subquestion_overview}

For each claim you extract, also check ALL other supplied sources
(even those from different subquestions that cover related topics)
to determine whether independent sources corroborate the same claim.

corroboration_level rules:
- "single_source"      Only this one source mentions this claim
- "weakly_corroborated"      One OTHER independent source (different domain) supports this claim
- "strongly_corroborated"    2+ OTHER independent sources (different domains) support this claim

CRITICAL: Two pages from the SAME domain (e.g., two openai.com pages)
do NOT count as independent corroboration. Only DIFFERENT domain
agreement constitutes meaningful cross-validation.

When asserting corroboration, you MUST:
1. Quote the supporting snippet from the corroborating source
2. Verify the corroborating source's domain is different from the primary source
3. Include corroborating source URLs in corroborating_sources

Each source is marked with content_type:
- "extracted_content" — full webpage text was available
- "search_content"   — only a search snippet was available (extract failed)

When assessing corroboration strength:
- Two full-text sources independently stating the same fact → strong signal
- One full text + one snippet → weaker but still valid
- Two snippets → treat as weakly_corroborated at best
- Label the strength honestly; do not inflate weak signals

Return only JSON in this exact shape:
{{"evidence_cards":[{{"id":"e1","subquestion_id":"q1","claim":"...","source_url":"https://...","source_title":"...","supporting_snippet":"...","content_type":"extracted_content","corroboration_level":"single_source|weakly_corroborated|strongly_corroborated","corroborating_sources":["https://other-domain.com/..."],"confidence":"low|medium|high"}}]}}

Original question:
{question}

{grouped_sources}
""".strip()
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_evidence_prompt.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/prompts/evidence.py tests/test_evidence_prompt.py
git commit -m "feat: pass subquestion context into evidence prompt"
```

---

### Task 2: Pass subquestions from prepare_evidence to build_evidence_prompt

**Files:**
- Modify: `src/deepresearch/nodes/prepare_evidence.py`

- [ ] **Step 1: Update the prompt call**

In `src/deepresearch/nodes/prepare_evidence.py`, find the `build_evidence_prompt` call (around line 241-243):

```python
        prompt = build_evidence_prompt(
            state.get("question", ""), extracted_sources
        )
```

Change to:

```python
        prompt = build_evidence_prompt(
            state.get("question", ""), extracted_sources,
            subquestions=state.get("subquestions", []),
        )
```

- [ ] **Step 2: Run tests to confirm no breakage**

Run:
```bash
uv run pytest tests/test_prepare_evidence_node.py tests/test_integration_offline.py -v
```

Expected: all pass (10 + 1 tests).

- [ ] **Step 3: Commit**

```bash
git add src/deepresearch/nodes/prepare_evidence.py
git commit -m "feat: pass subquestions to evidence prompt"
```

---

### Task 3: Add dry_run parameter to graph

**Files:**
- Modify: `src/deepresearch/graph.py`
- Modify: `tests/test_graph_structure.py`

- [ ] **Step 1: Add failing test**

In `tests/test_graph_structure.py`, add:

```python
def test_dry_run_graph_compiles_with_prepare_evidence_to_end(tmp_path):
    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        synthesize_notes=lambda state: {**state, "notes": []},
        write_report=lambda state: {**state, "report_markdown": "# Report"},
        review_report=lambda state: {**state, "review": None},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
        dry_run=True,
    )

    assert graph is not None
    # Invoke — should stop after prepare_evidence
    result = graph.invoke({"question": "AI search", "errors": []})
    # In dry_run mode, no report should be generated
    assert "report_markdown" not in result
```

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_graph_structure.py::test_dry_run_graph_compiles_with_prepare_evidence_to_end -v
```

Expected: `TypeError` — `build_research_graph()` got unexpected keyword argument `dry_run`.

- [ ] **Step 3: Update graph.py**

In `src/deepresearch/graph.py`, update `build_research_graph` signature to accept `dry_run: bool = False`:

```python
def build_research_graph(
    *,
    plan_research: Node,
    search_web: Node,
    prepare_evidence: Node,
    synthesize_notes: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
    dry_run: bool = False,
):
    graph = StateGraph(ResearchState)
    graph.add_node("plan_research", plan_research)
    graph.add_node("search_web", search_web)
    graph.add_node("prepare_evidence", prepare_evidence)
    graph.add_node("synthesize_notes", synthesize_notes)
    graph.add_node("write_report", write_report)
    graph.add_node("review_report", review_report)
    graph.add_node("save_report", save_report)

    graph.add_edge(START, "plan_research")
    graph.add_edge("plan_research", "search_web")
    graph.add_edge("search_web", "prepare_evidence")

    if dry_run:
        graph.add_edge("prepare_evidence", END)
    else:
        graph.add_edge("prepare_evidence", "synthesize_notes")
        graph.add_edge("synthesize_notes", "write_report")
        graph.add_edge("write_report", "review_report")
        graph.add_edge("review_report", "save_report")
        graph.add_edge("save_report", END)

    return graph.compile()
```

Also update `create_research_app` to accept and forward `dry_run`:

```python
def create_research_app(
    *,
    plan_research: Node,
    search_web: Node,
    prepare_evidence: Node,
    synthesize_notes: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
    dry_run: bool = False,
):
    return build_research_graph(
        plan_research=plan_research,
        search_web=search_web,
        prepare_evidence=prepare_evidence,
        synthesize_notes=synthesize_notes,
        write_report=write_report,
        review_report=review_report,
        save_report=save_report,
        dry_run=dry_run,
    )
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_graph_structure.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/graph.py tests/test_graph_structure.py
git commit -m "feat: add dry_run graph mode stopping after prepare_evidence"
```

---

### Task 4: Add --dry-run flag to CLI

**Files:**
- Modify: `src/deepresearch/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Update CLI to support --dry-run**

In `src/deepresearch/cli.py`:

Add `dry_run` parameter to `main()`:

```python
@app.command()
def main(
    question: str = typer.Argument(..., help="Research question"),
    max_subquestions: int | None = typer.Option(None, "--max-subquestions", help="Maximum generated subquestions"),
    results_per_query: int | None = typer.Option(None, "--results-per-query", help="Tavily results per query"),
    output_dir: str | None = typer.Option(None, "--output-dir", help="Report output directory"),
    model: str | None = typer.Option(None, "--model", help="DeepSeek model override"),
    verbose: bool = typer.Option(False, "--verbose", help="Print debugging details"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Stop after evidence extraction and print card summary"),
):
```

In `_build_app`, pass `dry_run` to `create_research_app`:

```python
def _build_app(config: AppConfig, dry_run: bool = False):
    ...
    return create_research_app(
        plan_research=...,
        ...
        dry_run=dry_run,
    )
```

In the main flow, after invoke, check for dry_run:

```python
        research_app = _build_app(config, dry_run=dry_run)
        result = research_app.invoke({"question": question, "errors": []})

        if dry_run:
            console.print("\n[Dry run] Evidence extraction complete.\n")
            evidence_metrics = result.get("evidence_metrics", {})
            cards = result.get("evidence_cards", [])
            console.print(f"EvidenceCards: {evidence_metrics.get('evidence_cards', 0)}")
            console.print()
            console.print("Evidence corroboration:")
            corroboration = evidence_metrics.get("corroboration", {})
            for key in ["strongly_corroborated", "weakly_corroborated", "single_source"]:
                value = corroboration.get(key, 0)
                desc = {
                    "strongly_corroborated": " (3+ independent sources agree)",
                    "weakly_corroborated": " (2 independent sources agree)",
                    "single_source": " (only one source mentions this)",
                }.get(key, "")
                console.print(f"- {key}: {value}{desc}")
            if cards:
                console.print("\nEvidence card summaries:")
                for i, card in enumerate(cards, start=1):
                    claim_snippet = card.claim[:100] + "..." if len(card.claim) > 100 else card.claim
                    console.print(f"{i}. [{card.id}] {claim_snippet} (corroboration: {card.corroboration_level}, sources: {len(card.corroborating_sources)})")
            return
```

- [ ] **Step 2: Add CLI test**

In `tests/test_cli.py`, add:

```python
def test_cli_dry_run_prints_evidence_summary(monkeypatch):
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "evidence_cards": [],
        "evidence_metrics": {
            "evidence_cards": 5,
            "corroboration": {"strongly_corroborated": 2, "weakly_corroborated": 2, "single_source": 1},
        },
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda _config, dry_run=False: fake_app)

    result = runner.invoke(app, ["AI search", "--dry-run"])

    assert result.exit_code == 0
    assert "[Dry run] Evidence extraction complete." in result.output
    assert "EvidenceCards: 5" in result.output
    assert "strongly_corroborated: 2" in result.output
    assert "weakly_corroborated: 2" in result.output
```

- [ ] **Step 3: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_cli.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/deepresearch/cli.py tests/test_cli.py
git commit -m "feat: add --dry-run flag for evidence extraction testing"
```

---

### Task 5: Run full test suite

**Files:**
- No file changes unless fixes needed.

- [ ] **Step 1: Run all tests**

Run:
```bash
uv run pytest -v
```

Expected: all pass.

- [ ] **Step 2: Check git status**

Run:
```bash
git status --short
```

Expected: clean.

- [ ] **Step 3: Commit if fixes needed**

---

### Task 6: Lightweight online validation

**Files:**
- No file changes. This is a manual verification step.

- [ ] **Step 1: Get explicit authorization**

Confirm with user before external API calls.

- [ ] **Step 2: Run dry-run on comparison-type query**

```bash
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --dry-run --verbose --max-subquestions 2 --results-per-query 2
```

Expected: EvidenceCard >= 5, execution < 3 min.

- [ ] **Step 3: If dry-run passes, run standard validation**

```bash
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --verbose
```

Verify: EvidenceCard >= 5, Review score >= 85.

---

## Self-Review

Spec coverage:
- Subquestion context in evidence prompt: Tasks 1, 2.
- --dry-run flag: Tasks 3, 4.
- Lightweight online validation: Task 6.

No placeholders. All steps include actual code.
