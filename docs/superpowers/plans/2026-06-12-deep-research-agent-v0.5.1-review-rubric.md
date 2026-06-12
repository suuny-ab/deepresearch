# Deep Research Agent v0.5.1 Review Rubric Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5-dimension scoring rubric to review prompt and pass evidence_cards instead of search_results.

**Architecture:** Two small changes — `prompts/reviewing.py` gets the rubric prompt, `nodes/reviewing.py` passes `evidence_cards` as input. Review remains a pure observer.

**Tech Stack:** Python 3.11+, DeepSeek API

---

### Task 0: Pre-check

- [ ] `git status --short` → clean
- [ ] `uv run pytest -v` → all pass

---

### Task 1: Update review prompt + node

**Files:**
- Modify: `src/deepresearch/prompts/reviewing.py`
- Modify: `src/deepresearch/nodes/reviewing.py`
- Modify: `tests/test_reviewing_node.py`

- [ ] **Step 1: Update test_reviewing_node.py**

Replace the existing test content. The test should verify that the review prompt receives evidence_cards with corroboration info, not raw search results.

```python
from tests.conftest import FakeLLMClient

from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.state import EvidenceCard, SubQuestion


def test_review_report_uses_evidence_cards():
    llm = FakeLLMClient([
        '{"passed":true,"score":86,"issues":[],"suggestions":[]}'
    ])
    node = make_review_report_node(llm)

    evidence_cards = [
        EvidenceCard(
            id="e1", subquestion_id="q1",
            claim="RAG is important.",
            source_url="https://example.com/report",
            source_title="Report",
            supporting_snippet="RAG is important.",
            content_type="extracted_content",
            corroboration_level="strongly_corroborated",
            corroborating_sources=["https://other1.example/a", "https://other2.example/b"],
            confidence="high",
        ),
    ]

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "report_markdown": "# AI Search\n\nRAG is important.[1]\n\n## Sources\n\n[1] https://example.com/report",
        "search_results": [],  # Empty — review should use evidence_cards
        "evidence_cards": evidence_cards,
        "errors": [],
    })

    assert result["review"].score == 86
    assert result["review"].passed is True


def test_review_prompt_contains_rubric():
    from deepresearch.prompts.reviewing import build_reviewing_prompt
    from deepresearch.state import EvidenceCard

    cards = [
        EvidenceCard(
            id="e1", subquestion_id="q1", claim="Claim.",
            source_url="https://example.com/a", source_title="A",
            supporting_snippet="Claim.", content_type="extracted_content",
            corroboration_level="weakly_corroborated",
            corroborating_sources=["https://example.com/b"],
            confidence="high",
        ),
    ]

    prompt = build_reviewing_prompt("AI search", "# Report", cards)

    assert "来源支撑" in prompt or "source support" in prompt.lower()
    assert "交叉验证" in prompt or "corroboration" in prompt.lower()
    assert "完整性" in prompt or "completeness" in prompt.lower()
    assert "30%" in prompt
    assert "20%" in prompt
    assert "https://example.com/a" in prompt
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
uv run pytest tests/test_reviewing_node.py -v
```

Expected: failures — old prompt structure.

- [ ] **Step 3: Replace review prompt**

Replace `src/deepresearch/prompts/reviewing.py`:

```python
from deepresearch.state import EvidenceCard


def build_reviewing_prompt(
    question: str,
    report_markdown: str,
    evidence_cards: list[EvidenceCard],
) -> str:
    card_summaries = []
    for c in evidence_cards:
        card_summaries.append(
            f"- [{c.id}] {c.claim[:120]}... "
            f"(corroboration: {c.corroboration_level}, "
            f"source: {c.source_url})"
        )

    cards_text = "\n".join(card_summaries) if card_summaries else "- None"

    return f"""
Review this Markdown research report. Score it on five dimensions using the rubric below. First assign a score (0-100) for each dimension, then compute the weighted total.

Scoring Rubric:

1. Source Support (weight 30%)
   90-100: All key conclusions use numbered citations from EvidenceCards
   60-89:  Most key conclusions cite sources; a few unsupported claims
   30-59:  Many unsupported claims throughout
   0-29:   Few or no citations

2. Cross-Validation Coverage (weight 20%)
   90-100: Main conclusions backed by strongly/weakly corroborated cards
   60-89:  Some conclusions have cross-validation, some single-source
   30-59:  Most conclusions from single sources
   0-29:   No effective cross-validation

3. Completeness (weight 20%)
   90-100: Covers core arguments from all subquestions
   60-89:  Covers most subquestions, some angles missed
   30-59:  Important subquestions missing
   0-29:   Only covers a fraction of the question

4. Structure & Clarity (weight 15%)
   90-100: All required sections present, logical flow
   60-89:  Sections present but some sections thin
   30-59:  Required sections missing
   0-29:   Disorganized

5. Relevance & Focus (weight 15%)
   90-100: All content directly addresses the research question
   60-89:  Mostly relevant, occasional tangents
   30-59:  Significant off-topic content
   0-29:   Largely unrelated to the question

Compute: total = (source_support * 0.30) + (corroboration * 0.20) + (completeness * 0.20) + (structure * 0.15) + (relevance * 0.15)
Round to the nearest integer.

EvidenceCards used in this report (with corroboration status):
{cards_text}

Return only JSON in this exact shape:
{{"passed":true,"score":88,"issues":["..."],"suggestions":["..."]}}
Score must be an integer from 0 to 100.

Original question:
{question}

Report:
{report_markdown}
""".strip()
```

- [ ] **Step 4: Update review node**

In `src/deepresearch/nodes/reviewing.py`, change the prompt call:

```python
# 旧
prompt = build_reviewing_prompt(state["question"], state.get("report_markdown", ""), state.get("search_results", []))

# 新
prompt = build_reviewing_prompt(state["question"], state.get("report_markdown", ""), state.get("evidence_cards", []))
```

Also update the import from `SearchResult` to `EvidenceCard` (or just remove the SearchResult import if no longer needed).

- [ ] **Step 5: Run tests to confirm pass**

```bash
uv run pytest tests/test_reviewing_node.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/deepresearch/prompts/reviewing.py src/deepresearch/nodes/reviewing.py tests/test_reviewing_node.py
git commit -m "feat: add scoring rubric and pass evidence_cards to review prompt"
```

---

### Task 2: Full test suite

- [ ] `uv run pytest -v` → all pass
- [ ] `git status --short` → clean

---

## Self-Review

Spec coverage:
- Rubric: Task 1 Step 3 (prompt replacement)
- evidence_cards input: Task 1 Step 4 (node change)

No placeholders. All steps include actual code.
