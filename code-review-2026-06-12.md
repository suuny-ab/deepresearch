# Code Review Report — Deep Research Agent v0.5.2

Date: 2026-06-12 | Scope: 87 commits, 39 files, +6313/-835 lines | 9 angles

## Critical

### 1. Extract fallback mislabels content as "extracted_content"
**File:** `src/deepresearch/nodes/prepare_evidence.py:88,204-212`

When Tavily `extract()` fails, `_extract_sources_for_subquestion` returns the same list as both `success` and `fallback`. The caller loop then marks all sources as `"extracted_content"` (line 206), even though they contain raw search snippets. This inflates content quality and undermines the `_validate_corroboration` downgrade logic which trusts the `"extracted_content"` label.

### 2. Assertion false positives — non-normalized URL comparison in `_run_assertions`
**File:** `src/deepresearch/nodes/prepare_evidence.py:172`

```python
count = len([c for c in claims if c.source_url == source.url])
```

LLM-generated `source_url` may differ from the original in scheme, trailing slash, or www prefix. These semantically identical URLs fail string comparison, producing false `[FAIL]` reports.

### 3. Uncaught LLM API errors propagate through graph to untyped crash
**Files:** `prepare_evidence.py:131,142`, `writing.py:148,172`, `reviewing.py:11`

`llm.complete(prompt)` calls have no try/except. Network timeout, rate limit, or auth failure propagates through langgraph to the CLI, past the narrow `ConfigError | DeepResearchError` catch.

### 4. `assert` guards for API keys silently skip under `python -O`
**File:** `src/deepresearch/cli.py:31-32`

```python
assert config.deepseek_api_key is not None
assert config.tavily_api_key is not None
```

Python `-O` strips all assert statements. Should be explicit `if key is None: raise ConfigError(...)`.

## High

### 5. `--replay-search` crashes on bad file with untrapped FileNotFoundError / JSONDecodeError
**File:** `src/deepresearch/cli.py:130-137`

Raw `open()` + `json.load()` + dict key access with no try/except inside the replay path. A missing file or malformed JSON escapes the `ConfigError | DeepResearchError` catch boundary.

### 6. Extracted source fallback double-counts when `extract` partially fails
**File:** `src/deepresearch/nodes/prepare_evidence.py:88`

On exception, all selected sources go through both the `success` and `fallback` loops (same list object returned twice). The `fallback` loop checks `if key not in extracted_content_types` to avoid double insertion, but `extracted_sources` list receives the same objects twice — potential duplicate in metrics.

### 7. Dead code: `_is_english_domain` and English-domain preference never activated
**File:** `src/deepresearch/nodes/prepare_evidence.py:36-40,54-60`

`_select_sources` is called without `has_english_query` ever being True. The entire English-domain fallback branch and its helper function are dead.

### 8. Test doubles violate `SearchClient` protocol — would fail static type checks
**Files:** `tests/test_searching_node.py`, `tests/test_prepare_evidence_node.py`

The `FakeSearchClient` in searching tests has no `extract()`. The one in prepare_evidence tests has no `search()`. If either node adds a cross-method call, tests crash with `AttributeError`.

## Medium

### 9. Phase 2 LLM calls run sequentially, multiplying wall-clock time by N
**File:** `src/deepresearch/nodes/prepare_evidence.py:223-228`

Each subquestion's validation is a fully independent API call; 5 subquestions = 5x serial latency.

### 10. `_run_assertions` computes source-claim counts in O(N×M) with temporary allocations
**File:** `src/deepresearch/nodes/prepare_evidence.py:172`

A list comprehension per source × all claims per iteration. Replace with `Counter(c.source_url for c in claims)`.

### 11. `verbose.py` looks up metrics keys that `_build_metrics` never writes
**File:** `src/deepresearch/verbose.py:35-36`

`evidence_metrics.get("subquestions", ...)` and `"total_queries"` always fall through to defaults. Dead-key lookups.

### 12. README shows stale 7-step pipeline with deleted `synthesize_notes`
**File:** `README.md:8`

The workflow diagram still reads `plan → search → evidence → synthesize_notes → write → review → save`. Actual pipeline is 6 steps (no synthesize_notes).

### 13. `_failure_to_dict` trivial wrapper (1 line) over `.to_dict()`
**File:** `src/deepresearch/nodes/writing.py:85-87`

Inline at both call sites.

### 14. Attempt-1 and attempt-2 error handling in `write_report` are near-duplicates
**File:** `src/deepresearch/nodes/writing.py:161-170,186-195`

Same pattern repeated with different variable names.

### 15. Unused imports `LLMClient` and `SearchClient` in `prepare_evidence.py`
**File:** `src/deepresearch/nodes/prepare_evidence.py:5-6`

Neither is referenced as a type annotation or value.

## Low

### 16. FakeSearchClient raises `Exception` instead of `SearchError` on simulated failure
### 17. `extracted_claims` state field written but never read by downstream nodes (only CLI --output debug flag uses it)
### 18. `_is_english_domain` misleading name — actually checks Chinese domains
### 19. `normalize_url` / `extract_domain` share duplicated URL pre-processing logic
### 20. Four JSON parse try/except blocks share identical error-appending pattern
