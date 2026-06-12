# Deep Research Agent v0.5.2 — Pending Issues Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 2 remaining pending issues: add extraction quantity guideline and implement review feedback loop (rewrite when score < 70).

**Architecture:** Extraction quantity guideline is a 1-line prompt change. Review feedback loop adds conditional routing in the LangGraph (review → write_report or save_report), a `review_feedback` field to state, and review feedback injection into the write prompt. Max 1 rewrite.

**Tech Stack:** Python, LangGraph, Pydantic

---

### Task 1: Extraction Quantity Guideline

**Files:**
- Modify: `src/deepresearch/prompts/extraction.py` — add soft quantity guideline
- Test: `tests/test_extraction_prompt.py` — verify guideline present

- [ ] **Step 1: Modify extraction prompt**

Add a soft quantity guideline after the "Rules:" section. Replace the existing "There is no minimum or maximum" with:

Edit `src/deepresearch/prompts/extraction.py`, line 43-44. Change:

```python
extract as many as each source genuinely contains.
```

to:

```python
extract as many as each source genuinely contains.
Extract at least 2-4 claims per source on average.
Sources with rich content may support more; thin sources may support fewer.
```

- [ ] **Step 2: Add test for quantity guideline**

Add to `tests/test_extraction_prompt.py`:

```python
def test_extraction_prompt_has_quantity_guideline():
    sources = [
        ExtractedSource(
            subquestion_id="q1", url="https://example.com/a",
            title="Source A", raw_content="RAG is important for AI search.",
        ),
    ]
    subquestions = [
        SubQuestion(id="q1", question="What is AI search?", search_query="q", search_queries=["q"], rationale="r"),
    ]

    prompt = build_extraction_prompt("AI search", sources, subquestions)

    assert "at least 2-4 claims per source" in prompt
```

- [ ] **Step 3: Run tests to verify**

```bash
uv run pytest tests/test_extraction_prompt.py -v
```
Expected: all tests pass (existing 3 + new 1 = 4 passed)

- [ ] **Step 4: Commit**

```bash
git add src/deepresearch/prompts/extraction.py tests/test_extraction_prompt.py
git commit -m "feat: add extraction quantity guideline (2-4 claims per source)"
```

---

### Task 2: Add State Fields for Review Feedback Loop

**Files:**
- Modify: `src/deepresearch/state.py` — add `review_feedback` and `review_rewritten`

- [ ] **Step 1: Add fields to ResearchState**

Edit `src/deepresearch/state.py`, add after `review: ReviewResult` (line 91):

```python
    review_feedback: str | None
    review_rewritten: bool
```

The updated `ResearchState` class should look like:

```python
class ResearchState(TypedDict, total=False):
    question: str
    subquestions: list[SubQuestion]
    search_results: list[SearchResult]
    extracted_claims: list[ExtractedClaim]
    evidence_cards: list[EvidenceCard]
    evidence_metrics: dict[str, Any]
    report_markdown: str
    report_status: Literal["success", "failed_validation"]
    rewrite_attempted: bool
    validation_attempts: int
    validation_failures: list[dict[str, Any]]
    review: ReviewResult
    review_feedback: str | None
    review_rewritten: bool
    output_path: str
    errors: list[str]
```

- [ ] **Step 2: Run existing tests to confirm no breakage**

```bash
uv run pytest -q
```
Expected: 125 passed

- [ ] **Step 3: Commit**

```bash
git add src/deepresearch/state.py
git commit -m "feat: add review_feedback and review_rewritten state fields"
```

---

### Task 3: Format Review Feedback in Review Report Node

**Files:**
- Modify: `src/deepresearch/nodes/reviewing.py` — set review_feedback when score < 70

- [ ] **Step 1: Modify review_report node to set review_feedback**

Edit `src/deepresearch/nodes/reviewing.py`. Replace the `make_review_report_node` function:

```python
from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.reviewing import build_reviewing_prompt
from deepresearch.state import ResearchState, ReviewResult
from deepresearch.utils.json import JSONParseError, parse_json_object


def _format_review_feedback(review: ReviewResult) -> str:
    """Format review issues and suggestions into actionable feedback for rewrite."""
    parts = []
    if review.issues:
        parts.append("Issues identified in previous review:")
        for issue in review.issues:
            parts.append(f"- {issue}")
    if review.suggestions:
        parts.append("Suggestions for improvement:")
        for suggestion in review.suggestions:
            parts.append(f"- {suggestion}")
    return "\n".join(parts)


def make_review_report_node(llm: LLMClient):
    def review_report(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        prompt = build_reviewing_prompt(state["question"], state.get("report_markdown", ""), state.get("evidence_cards", []))
        try:
            text = llm.complete(prompt)
        except Exception as exc:
            errors.append(f"LLM call failed in review_report: {exc}")
            return {**state, "review": ReviewResult(passed=False, score=0, issues=["LLM call failed"], suggestions=[]), "errors": errors}
        try:
            review = parse_json_object(text, ReviewResult)
        except JSONParseError as exc:
            errors.append(f"Review JSON parse failed: {exc}")
            review = ReviewResult(passed=False, score=0, issues=["Review parsing failed"], suggestions=["Inspect the report manually"])

        review_feedback = None
        if review.score < 70 and not state.get("review_rewritten", False):
            review_feedback = _format_review_feedback(review)

        return {**state, "review": review, "review_feedback": review_feedback, "errors": errors}

    return review_report
```

Key logic:
- If score < 70 AND not already rewritten → format feedback and set `review_feedback`
- If score >= 70 OR already rewritten → `review_feedback` stays None
- `review_rewritten` is set to True by write_report after consuming feedback (next task)

- [ ] **Step 3: Run tests to verify**

```bash
uv run pytest tests/test_reviewing_node.py -v
```
Expected: all passing

- [ ] **Step 4: Commit**

```bash
git add src/deepresearch/nodes/reviewing.py
git commit -m "feat: format review feedback when score < 70 for rewrite"
```

---

### Task 4: Inject Review Feedback Into Write Report Node

**Files:**
- Modify: `src/deepresearch/prompts/writing.py` — accept `review_feedback` parameter
- Modify: `src/deepresearch/nodes/writing.py` — pass review_feedback, clear it after use, set review_rewritten

- [ ] **Step 1: Add review_feedback parameter to build_writing_prompt**

Edit `src/deepresearch/prompts/writing.py`. Add `review_feedback` parameter and inject it into the prompt when present:

```python
def build_writing_prompt(
    question: str,
    subquestions: list[SubQuestion],
    results: list[SearchResult],
    evidence_cards: list[EvidenceCard] | None = None,
    allowed_source_urls: set[str] | None = None,
    review_feedback: str | None = None,
) -> str:
    if allowed_source_urls is not None:
        allowed_urls = sorted(allowed_source_urls)
    elif evidence_cards:
        allowed_urls = sorted({card.source_url for card in evidence_cards})
    else:
        allowed_urls = sorted({item.url for item in results})

    feedback_section = ""
    if review_feedback:
        feedback_section = f"""
Previous review identified the following issues with your draft.
Address each issue in the rewrite:

{review_feedback}
"""

    return f"""
请使用中文撰写结构化 Markdown 深度研究报告，除非用户问题使用其他语言。
{feedback_section}
引用规则必须严格遵守：
...
```

The full updated prompt with `{feedback_section}` inserted right after the language instruction line:

```python
def build_writing_prompt(
    question: str,
    subquestions: list[SubQuestion],
    results: list[SearchResult],
    evidence_cards: list[EvidenceCard] | None = None,
    allowed_source_urls: set[str] | None = None,
    review_feedback: str | None = None,
) -> str:
    if allowed_source_urls is not None:
        allowed_urls = sorted(allowed_source_urls)
    elif evidence_cards:
        allowed_urls = sorted({card.source_url for card in evidence_cards})
    else:
        allowed_urls = sorted({item.url for item in results})

    feedback_section = ""
    if review_feedback:
        feedback_section = f"""
Previous review identified the following issues with your draft.
Address each issue in the rewrite:

{review_feedback}
"""

    return f"""
请使用中文撰写结构化 Markdown 深度研究报告，除非用户问题使用其他语言。
{feedback_section}
引用规则必须严格遵守：
1. 正文中的每个关键论点必须使用编号引用，例如 [1]、[2]。
2. 正文中不要出现裸 URL。
3. 所有 URL 只能出现在 ## Sources 部分。
4. ## Sources 中必须用 [1]、[2] 映射到 allowed source URLs。
5. 正文中使用的每个编号都必须在 ## Sources 中定义。
6. ## Sources 中列出的每个编号都必须在正文中出现。
7. 只能使用 Allowed source URLs 列表中的 URL。

Citation rules:
- Use numbered citations in the body: [1], [2], [3].
- Do not put raw URLs in the body.
- URLs may only appear in the ## Sources section.
- Every citation number used in the body must be defined in ## Sources.
- Every source listed in ## Sources must be cited in the body.
- Only use URLs from the allowed source URL list.

Required sections:
# <title>
## 摘要
## 关键结论
## 背景与问题拆解
## 深度分析
## 风险、不确定性与不同观点
## 结论
## Sources

When citing claims in the report body:
- Claims supported by multiple independent sources should be presented
  with higher certainty
- When a claim comes from a single source, consider using language like
  "According to [source]..." or "One perspective suggests..." rather than
  stating it as uncontested fact
- If different sources present conflicting views, present both sides
  rather than choosing one

Sources format:
[1] https://example.com/source-a
[2] https://example.com/source-b

Original question:
{question}

Subquestions:
{[item.model_dump() for item in subquestions]}


Allowed source URLs:
{allowed_urls}
""".strip()
```

- [ ] **Step 2: Modify write_report node to pass review_feedback and set review_rewritten**

Edit `src/deepresearch/nodes/writing.py`. In `make_write_report_node`, the `write_report` function needs to:
1. Read `review_feedback` from state
2. Pass it to `build_writing_prompt`
3. On return, set `review_feedback = None` and `review_rewritten = True` if feedback was consumed

Find the `write_report` function inside `make_write_report_node`. After the `allowed_urls = ...` line (line 137), add the review_feedback read. Then modify the `build_writing_prompt` call to pass it. Then add the cleanup in the return dict.

Current code around line 137-144:
```python
        allowed_urls = _allowed_source_urls(state)
        prompt = build_writing_prompt(
            state["question"],
            state.get("subquestions", []),
            results,
            evidence_cards=state.get("evidence_cards", []),
            allowed_source_urls=allowed_urls,
        )
```

Change to:
```python
        allowed_urls = _allowed_source_urls(state)
        review_feedback = state.get("review_feedback")
        prompt = build_writing_prompt(
            state["question"],
            state.get("subquestions", []),
            results,
            evidence_cards=state.get("evidence_cards", []),
            allowed_source_urls=allowed_urls,
            review_feedback=review_feedback,
        )
```

Now, in ALL return dicts from `write_report`, we need to add `review_feedback=None` and `review_rewritten=True` when feedback was consumed. The cleanest way is to compute the base return dict and add these conditionally.

Better approach: compute the return dict as before, then conditionally add cleanup fields.

Actually, looking at the code more carefully, there are many return paths. Let me add a helper at the end of write_report:

Find the last return statement in `write_report` and replace it. Actually, let me trace all return paths:

1. No search results → early return (no review_feedback to clear)
2. LLM call fails → error return (no review_feedback to clear)
3. First validation passes → success return (no review_feedback to clear)
4. Rewrite fails → failure return (no review_feedback to clear)
5. Second validation passes → success return (MIGHT have consumed review_feedback)
6. Second validation fails → failure return (MIGHT have consumed review_feedback)

The cleanest way: add review_feedback cleanup to paths 5 and 6 (the rewrite paths). Actually even simpler: just do it once at the end of the function by adding cleanup fields to the returned dict.

Let me add the cleanup inside each return dict for the rewrite paths. For paths 5 and 6:

Path 5 (second validation passes, line 197-206):
```python
        if second_validation.passed:
            return {
                **state,
                "report_markdown": rewritten_report,
                "errors": errors,
                "report_status": "success",
                "rewrite_attempted": True,
                "validation_attempts": 2,
                "validation_failures": [first_validation.to_dict()],
            }
```
Add `review_feedback=None` and `review_rewritten=True` if review_feedback was consumed. Since both paths 5 and 6 go through the rewrite path (the prompt was built with review_feedback), both should clear it.

Actually, the safest approach: wrap the return in write_report to always clear these fields if they were set on input:

At the bottom of `write_report`, just before each `return`, add these lines. But that's repetitive.

Let me use a simpler pattern. After computing `allowed_urls` and `review_feedback`, track whether we're doing a rewrite:

```python
        is_rewrite = review_feedback is not None
```

Then in each return path that follows the prompt construction (paths 3-6), conditionally add:
```python
        "review_feedback": None,
        "review_rewritten": True,
```
only when `is_rewrite`.

Wait, even simpler. Since `review_feedback` is in the state and we're using `**state` to spread existing state, if we explicitly set `review_feedback=None` in the return dict, it overrides whatever was in state. So let me just add cleanup to ALL return paths after the prompt construction:

Actually, for paths 1 and 2 (early exits before prompt), review_feedback wasn't consumed so we should NOT clear it. But those paths only happen on first write (no search results or LLM error), not during a rewrite. So it's fine.

Let me just be explicit: only paths that pass through the `build_writing_prompt` call need to clear review_feedback. The cleanest way:

```python
        # After building prompt, before try:
        is_rewrite = review_feedback is not None
```

Then modify paths 3, 5, 6 to include:
```python
        "review_feedback": None,
        "review_rewritten": True,
```
when `is_rewrite` is True. But since we can't do `condition ? value : default` in a dict literal... let me just build the return dict differently.

Actually, the simplest pattern that works:

```python
        is_rewrite = review_feedback is not None
        # ... rest of function ...
        
        # At the end, for each return that follows the prompt:
        result = {**state, "report_markdown": report, ...}
        if is_rewrite:
            result["review_feedback"] = None
            result["review_rewritten"] = True
        return result
```

But this requires restructuring every return path. Let me look at how many there are after prompt construction...

Path 3 (first validation passes, line 160-168):
```python
            return {
                **state,
                "report_markdown": report,
                "report_status": "success",
                "rewrite_attempted": False,
                "validation_attempts": 1,
                "validation_failures": [],
            }
```

Path 4 (rewrite LLM fails, line 186-194):
```python
            return {
                **state,
                "report_markdown": failure_report,
                "errors": errors,
                "report_status": "failed_validation",
                "rewrite_attempted": True,
                "validation_attempts": 1,
                "validation_failures": [first_validation.to_dict()],
            }
```

Path 5 (second validation passes, line 197-206):
```python
            return {
                **state,
                "report_markdown": rewritten_report,
                "errors": errors,
                "report_status": "success",
                "rewrite_attempted": True,
                "validation_attempts": 2,
                "validation_failures": [first_validation.to_dict()],
            }
```

Path 6 (second validation fails, line 218-227):
```python
        return {
            **state,
            "report_markdown": failure_report,
            "errors": errors,
            "report_status": "failed_validation",
            "rewrite_attempted": True,
            "validation_attempts": 2,
            "validation_failures": [first_validation.to_dict(), second_validation.to_dict()],
        }
```

All 4 paths need the cleanup if `is_rewrite`. The cleanest approach without restructuring everything:

Add a helper variable at the top:
```python
        is_rewrite = review_feedback is not None
```

Then add to each of the 4 return dicts:
```python
        "review_feedback": None,
        "review_rewritten": True,
```

Since these are optional TypedDict fields, they'll just be None/False on first pass when review_feedback was not set.

Let me write the exact modifications:

Path 3 (line 160-168): Add the two fields:
```python
            return {
                **state,
                "report_markdown": report,
                "report_status": "success",
                "rewrite_attempted": False,
                "validation_attempts": 1,
                "validation_failures": [],
                "review_feedback": None,
                "review_rewritten": True,
            }
```

Path 4 (line 186-194):
```python
            return {
                **state,
                "report_markdown": failure_report,
                "errors": errors,
                "report_status": "failed_validation",
                "rewrite_attempted": True,
                "validation_attempts": 1,
                "validation_failures": [first_validation.to_dict()],
                "review_feedback": None,
                "review_rewritten": True,
            }
```

Path 5 (line 197-206):
```python
            return {
                **state,
                "report_markdown": rewritten_report,
                "errors": errors,
                "report_status": "success",
                "rewrite_attempted": True,
                "validation_attempts": 2,
                "validation_failures": [first_validation.to_dict()],
                "review_feedback": None,
                "review_rewritten": True,
            }
```

Path 6 (line 218-227):
```python
        return {
            **state,
            "report_markdown": failure_report,
            "errors": errors,
            "report_status": "failed_validation",
            "rewrite_attempted": True,
            "validation_attempts": 2,
            "validation_failures": [first_validation.to_dict(), second_validation.to_dict()],
            "review_feedback": None,
            "review_rewritten": True,
        }
```

Note: Path 1 (no search results) and Path 2 (LLM call fails) don't pass through the prompt → no review_feedback to clear.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_writing_node.py tests/test_writing_prompt.py -v
```
Expected: all passing

- [ ] **Step 4: Commit**

```bash
git add src/deepresearch/prompts/writing.py src/deepresearch/nodes/writing.py
git commit -m "feat: inject review feedback into rewrite prompt"
```

---

### Task 5: Add Conditional Routing in Graph

**Files:**
- Modify: `src/deepresearch/graph.py` — add conditional edge from review_report

- [ ] **Step 1: Modify graph.py to add review routing**

Edit `src/deepresearch/graph.py`. Add `from typing import Literal` at the top. Replace the current edges (lines 38-52) with:

```python
from typing import Literal

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from deepresearch.state import ResearchState
```

```python
    from typing import Literal

    def _review_router(state: ResearchState) -> Literal["write_report", "save_report"]:
        if state.get("report_status") == "failed_validation":
            return "save_report"
        if state.get("review_feedback") is not None:
            return "write_report"
        return "save_report"

    if replay_search:
        graph.add_edge(START, "prepare_evidence")
        graph.add_edge("prepare_evidence", END)
    else:
        graph.add_edge(START, "plan_research")
        graph.add_edge("plan_research", "search_web")
        graph.add_edge("search_web", "prepare_evidence")

        if dry_run:
            graph.add_edge("prepare_evidence", END)
        else:
            graph.add_edge("prepare_evidence", "write_report")
            graph.add_conditional_edges(
                "review_report",
                _review_router,
                {"write_report": "write_report", "save_report": "save_report"},
            )
            graph.add_edge("save_report", END)
```

Key changes:
- Replace `graph.add_edge("write_report", "review_report")` and `graph.add_edge("review_report", "save_report")` with the conditional edge
- Keep `graph.add_edge("prepare_evidence", "write_report")` (write_report still runs after prepare_evidence)
- Add `graph.add_edge("write_report", "review_report")` — review always runs after write

Wait, I also need `graph.add_edge("write_report", "review_report")`. Let me look at the current code again...

Current code (line 38-52):
```python
    if replay_search:
        graph.add_edge(START, "prepare_evidence")
        graph.add_edge("prepare_evidence", END)
    else:
        graph.add_edge(START, "plan_research")
        graph.add_edge("plan_research", "search_web")
        graph.add_edge("search_web", "prepare_evidence")

        if dry_run:
            graph.add_edge("prepare_evidence", END)
        else:
            graph.add_edge("prepare_evidence", "write_report")
            graph.add_edge("write_report", "review_report")
            graph.add_edge("review_report", "save_report")
            graph.add_edge("save_report", END)
```

So the change is:
```python
            graph.add_edge("prepare_evidence", "write_report")
            graph.add_edge("write_report", "review_report")  # Keep this
            graph.add_conditional_edges(
                "review_report",
                _review_router,
                {"write_report": "write_report", "save_report": "save_report"},
            )
            graph.add_edge("save_report", END)
```

Remove `graph.add_edge("review_report", "save_report")`, add `graph.add_conditional_edges(...)`.

- [ ] **Step 2: Run existing graph tests**

```bash
uv run pytest tests/test_graph_structure.py -v
```
Expected: all existing tests pass. Note: existing tests mock nodes and may not test conditional routing directly.

- [ ] **Step 3: Commit**

```bash
git add src/deepresearch/graph.py
git commit -m "feat: add conditional routing for review feedback loop"
```

---

### Task 6: Test Review Feedback Loop

**Files:**
- Modify: `tests/test_graph_structure.py` — add test for review conditional routing
- Modify: `tests/test_writing_node.py` — add test for review feedback in rewrite prompt

- [ ] **Step 1: Add graph test for conditional routing**

Add to `tests/test_graph_structure.py`:

```python
def test_review_conditional_edge_routes_to_write_when_score_below_70(tmp_path):
    """When review score < 70 and no rewrite happened yet, route to write_report."""
    rewrite_triggered = []

    def tracking_write(state):
        rewrite_triggered.append(True)
        return {**state, "report_markdown": "# Rewritten", "review_feedback": None, "review_rewritten": True}

    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        write_report=tracking_write,
        review_report=lambda state: {**state, "review": ReviewResult(passed=False, score=50, issues=["Bad"], suggestions=["Fix it"])},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
    )

    result = graph.invoke({
        "question": "AI search",
        "errors": [],
        "review_feedback": None,
        "review_rewritten": False,
    })

    assert len(rewrite_triggered) == 1
    assert result["report_markdown"] == "# Rewritten"


def test_review_conditional_edge_skips_rewrite_when_score_above_70(tmp_path):
    """When review score >= 70, route directly to save_report."""
    rewrite_triggered = []

    def tracking_write(state):
        rewrite_triggered.append(True)
        return state

    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        write_report=tracking_write,
        review_report=lambda state: {**state, "review": ReviewResult(passed=True, score=85, issues=[], suggestions=[])},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
    )

    result = graph.invoke({
        "question": "AI search",
        "errors": [],
        "review_feedback": None,
        "review_rewritten": False,
    })

    assert len(rewrite_triggered) == 1  # Only the initial write, no rewrite
    assert result["review"].score == 85


def test_review_conditional_edge_skips_rewrite_when_already_rewritten(tmp_path):
    """When review_rewritten is True, don't rewrite again even if score < 70."""
    write_count = []

    def counting_write(state):
        write_count.append(True)
        return {**state, "report_markdown": "# Report"}

    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        write_report=counting_write,
        review_report=lambda state: {**state, "review": ReviewResult(passed=False, score=50, issues=["Bad"], suggestions=[])},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
    )

    result = graph.invoke({
        "question": "AI search",
        "errors": [],
        "review_feedback": None,
        "review_rewritten": True,  # Already rewritten
    })

    assert len(write_count) == 1  # Only initial write
```

Add import at top of file:
```python
from deepresearch.state import ReviewResult
```

- [ ] **Step 2: Add writing node test for review feedback injection**

Add to `tests/test_writing_node.py`:

```python
def test_write_report_includes_review_feedback_in_rewrite_prompt():
    """When review_feedback is provided, it should appear in the LLM prompt."""
    from tests.conftest import FakeLLMClient

    llm = FakeLLMClient([
        "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com"
    ])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "evidence_cards": [],
        "review_feedback": "Issues: The report lacks sufficient citations.\nSuggestions: Add more numbered references.",
        "errors": [],
    })

    prompt = llm.prompts[0]
    assert "review_feedback" in prompt.lower() or "Issues:" in prompt or "lacks sufficient citations" in prompt
    assert result["report_status"] == "success"


def test_write_report_clears_review_feedback_after_consumption():
    """After write_report consumes review_feedback, it should be cleared from state."""
    llm = FakeLLMClient([
        "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com"
    ])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "evidence_cards": [],
        "review_feedback": "Issues: Not enough citations.",
        "errors": [],
    })

    assert result.get("review_feedback") is None
    assert result.get("review_rewritten") is True
```

- [ ] **Step 3: Run all tests**

```bash
uv run pytest -q
```
Expected: all tests pass (125 → 130 tests)

- [ ] **Step 4: Commit**

```bash
git add tests/test_graph_structure.py tests/test_writing_node.py
git commit -m "test: add tests for review feedback loop routing and prompt injection"
```

---

### Task 7: Update CLI Verbose Display

**Files:**
- Modify: `src/deepresearch/cli.py` — show rewrite info in verbose mode

- [ ] **Step 1: Add rewrite info to CLI verbose output**

Edit `src/deepresearch/cli.py`. Find the verbose output section (around line 212, where `format_verbose_summary` is called). Before the verbose output, add rewrite status:

In the section around line 200-213:

```python
        if verbose:
            if result.get("review_feedback") or result.get("review_rewritten"):
                console.print("\nReview rewrite:")
                if result.get("review_rewritten"):
                    console.print("  Rewrite triggered by low review score")
                console.print(f"  Final review score: {result.get('review', {}).score if result.get('review') else 'N/A'}")
```

Wait, `result.get('review')` returns a `ReviewResult` object, not a dict. Let me check...

In the return from `graph.invoke()`, state fields are returned as their original types. `ReviewResult` is a `BaseModel`, so `result.get('review')` returns a `ReviewResult` instance. To access score: `result['review'].score`.

But `result.get('review')` could be None if the graph was a dry_run. Let me be safe:

```python
        if verbose:
            review = result.get("review")
            if review is not None and hasattr(review, "score"):
                review_score = review.score
            else:
                review_score = None

            if result.get("review_rewritten"):
                console.print("\nReview rewrite:")
                console.print("  Rewrite triggered by low review score")
                if review_score is not None:
                    console.print(f"  Final review score: {review_score}")
```

This should go before the `console.print("\n" + format_verbose_summary(result))` call.

Actually, looking at the CLI code more carefully (line 200-213):

```python
        if verbose:
            console.print("\n" + format_verbose_summary(result))
```

I need to insert before this line. Let me check what the verbose section looks like:

Lines 200-213:
```python
        if verbose:
            console.print("\n" + format_verbose_summary(result))
```

So the edit is:

```python
        if verbose:
            if result.get("review_rewritten"):
                review = result.get("review")
                score = review.score if review else "N/A"
                console.print(f"\n[Review] Rewrite triggered. Final score: {score}")
            console.print("\n" + format_verbose_summary(result))
```

- [ ] **Step 2: Update verbose test**

Check `tests/test_verbose.py` to see what it tests:

```bash
cat tests/test_verbose.py
```

If the test is flexible (not checking exact output), no update needed. Otherwise add assertion for the new line.

- [ ] **Step 3: Run tests**

```bash
uv run pytest -q
```
Expected: all passing

- [ ] **Step 4: Commit**

```bash
git add src/deepresearch/cli.py
git commit -m "feat: show review rewrite info in verbose output"
```
