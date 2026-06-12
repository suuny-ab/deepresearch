# Phase 1: Three Prompt-Level Fixes

## Task A: Evidence Card Minimum Quantity Instruction

**Problem**: Evidence prompt doesn't tell the LLM how many cards to generate. Combined with cross-validation's conservative bias, this produces too few cards (baseline: 4 cards for comparison-type queries).

**Fix**: Add a minimum quantity instruction to `prompts/evidence.py`.

**Changes needed**:
- `prompts/evidence.py`: Add instruction like "Generate at least 12-20 evidence cards total, with at least 3-5 cards per subquestion."
- Consider: per-subquestion minimum vs. overall minimum

**Files**: `src/deepresearch/prompts/evidence.py`

---

## Task B: Notes All-or-Nothing Fallback Fix

**Problem**: When synthesis LLM uses any URL outside EvidenceCards, ALL notes are discarded and replaced with low-confidence fallback. Should be per-note filtering instead.

**Current flow** (from `prepare_evidence.py`):
1. LLM returns `research_notes` and `evidence_cards`
2. If notes contain URLs not in evidence_cards, ALL notes → low-confidence fallback
3. Writer bypasses notes by using evidence_cards directly

**Fix**: Change from full discard to per-note filtering:
- For each note, check if its cited URLs are a subset of evidence_card URLs
- If yes → keep note with original confidence
- If no → either discard that note or mark it low-confidence individually

**Files**: `src/deepresearch/nodes/prepare_evidence.py`

---

## Task C: Review Feedback Loop (Review → Rewrite)

**Problem**: Review score is computed but never consumed. No rewrite triggered by low scores.

**Current flow**:
```
write_report → review_report → save_report  (review score is dead-end)
```

**Target flow**:
```
write_report → review_report → { score >= threshold → save_report }
                               { score < threshold → rewrite_report (up to N times) }
```

**Changes needed**:
1. `graph.py`: Add conditional edge from `review_report` back to `write_report`
2. `state.py`: Add `rewrite_count` or retry counter to state
3. `prompts/writing.py`: Add review feedback injection for rewrite passes (include previous review critique in prompt)
4. `nodes/writing.py`: Accept review_feedback in context when rewriting
5. `prompts/reviewing.py`: Adjust rubric to be more actionable (already has 5-dimension rubric from v0.5)

**Threshold**: Score < 70 triggers rewrite, max 2 rewrites

**Files**: `graph.py`, `state.py`, `prompts/writing.py`, `nodes/writing.py`

---

## Implementation Order

1. **Task A** (quantity instruction) — simplest, pure prompt change, no logic
2. **Task B** (notes fallback) — moderate, changes parsing logic
3. **Task C** (review feedback loop) — most complex, changes graph structure

## Test Plan

- **Task A**: Update `tests/test_evidence_prompt.py` to verify instruction is present in output
- **Task B**: Update `tests/test_prepare_evidence_node.py` to test per-note filtering
- **Task C**: Add tests for conditional rewrite path in `tests/test_graph_structure.py`
