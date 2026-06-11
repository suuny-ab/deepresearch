# Deep Research Agent v0.1.1 Improvements Design

Date: 2026-06-11

## 1. Background

The v0.1.0 MVP meets the original engineering acceptance criteria: it runs a fixed LangGraph workflow, uses DeepSeek and Tavily, saves Markdown reports, enforces source URL constraints, includes quality review output, and has passing offline tests.

Real usage exposed several product and observability issues that should be addressed in v0.1.1 before broader use:

1. Progress messages are printed all at once before the workflow actually runs.
2. When report validation fails, the saved failure report is hard to understand.
3. Failure reports do not show the specific invalid URLs that caused rejection.
4. Failure report filenames look like normal report filenames.
5. CLI output does not distinguish a successful report from a validation-failure report.
6. Users cannot easily inspect intermediate workflow outputs from the terminal.

The goal of v0.1.1 is to improve feedback, observability, and failure clarity without changing the core MVP workflow or adding automatic research loops.

## 2. Goals

v0.1.1 should:

- Keep the existing fixed LangGraph pipeline.
- Keep existing source-safety behavior.
- Make progress output honest and useful.
- Make validation failures understandable to users.
- Make failed report files visually distinguishable from successful reports.
- Improve `--verbose` output so users can inspect key intermediate artifacts.
- Preserve all current tests and add regression tests for new behavior.

## 3. Non-Goals

v0.1.1 will not implement:

- Automatic report rewrite after validation failure.
- Reviewer-driven retry loops.
- Additional Tavily searches after review.
- Multi-agent collaboration.
- Concurrent search.
- Web UI.
- Trace JSON files.
- PDF/DOCX export.
- Search result caching.

These are candidates for v0.2 or later.

## 4. Acceptance Decision Context

The current v0.1.0 version is accepted as an MVP engineering implementation, but it has product-quality issues. v0.1.1 is an improvement package, not a redefinition of the original MVP.

The most important distinction:

- v0.1.0 correctly refuses to publish unsafe reports.
- v0.1.1 should explain those refusals clearly and make runtime behavior easier to inspect.

## 5. Design Overview

v0.1.1 introduces three small design changes:

1. **Run status model**
   - Add lightweight metadata to the final state indicating whether the output is a successful report or a failed validation artifact.

2. **Improved report validation feedback**
   - Preserve structured validation failure details such as invalid URLs and reason codes.
   - Render those details in a user-facing failure report.

3. **CLI observability improvements**
   - Replace misleading pre-printed progress with honest workflow start/end messages or node-aware progress.
   - Expand `--verbose` to print subquestions, search queries, result counts, note counts, review score, and errors.

## 6. Report Validation Failure Handling

### 6.1 Current Behavior

Current failure reports look like this:

```markdown
# Research report not published

The report generation failed validation, so no unsupported report was published from that generation.
Invalid source URLs were detected in the generated report, so no report was published from that generation.

Only the following source URLs were available for a valid report:

- https://...
```

Problems:

- English-only output in an otherwise Chinese-facing workflow.
- Does not list the invalid URLs.
- Does not tell the user whether retrying might help.
- Does not distinguish the saved file from a successful report.

### 6.2 New Failure Report Format

When generated report validation fails, save a Chinese user-facing failure report:

```markdown
# 研究报告生成失败

本次报告没有发布，因为生成内容未通过来源校验。

## 失败原因

模型生成的报告包含未被搜索结果支持的来源 URL，因此系统拒绝保存该报告正文。

## 非法来源 URL

- https://invalid.example/source-a
- https://invalid.example/source-b

## 可用来源 URL

以下 URL 来自本次 Tavily 搜索结果，报告只能引用这些来源：

- https://allowed.example/source-1
- https://allowed.example/source-2

## 你可以怎么做

- 重新运行一次同样的问题。
- 使用更具体的研究问题。
- 增加 `--results-per-query` 以提供更多可用来源。
- 使用 `--verbose` 查看子问题、搜索 query 和搜索结果数量。
```

For other validation failures, use the same structure but change the reason:

| Failure | Reason Text |
|---|---|
| Invalid URLs | `模型生成的报告包含未被搜索结果支持的来源 URL。` |
| No citations | `模型生成的报告没有在正文中引用任何可用来源。` |
| Missing Sources section | `模型生成的报告缺少 ## Sources 来源部分。` |
| Body citations missing | `模型生成的报告只在 Sources 部分列出来源，但正文关键论点没有引用来源。` |

### 6.3 Structured Validation Result

Introduce a small internal model or dataclass:

```python
@dataclass(frozen=True)
class ReportValidationFailure:
    reason: Literal[
        "invalid_urls",
        "no_citations",
        "missing_sources_section",
        "missing_body_citations",
    ]
    message: str
    invalid_urls: list[str]
    allowed_urls: list[str]
```

This object does not need to be part of the public state model unless useful. It can remain internal to `nodes/writing.py`.

## 7. Failed Report Filename

### 7.1 Current Behavior

Both successful and failed outputs use filenames like:

```text
reports/2026-06-11-092627-ai.md
```

### 7.2 New Behavior

Successful reports keep the existing format:

```text
reports/2026-06-11-093242-ai.md
```

Validation-failure reports use:

```text
reports/2026-06-11-092627-ai-failed.md
```

### 7.3 Design

Extend filename/report writer utilities to accept a status flag:

```python
make_report_filename(question: str, *, failed: bool = False, now: datetime | None = None) -> str
```

Behavior:

- `failed=False`: `2026-06-11-093242-ai.md`
- `failed=True`: `2026-06-11-093242-ai-failed.md`

`save_report()` should accept the same flag and return the final path.

## 8. CLI Success vs Failure Messaging

### 8.1 Current Behavior

The CLI always prints:

```text
Saved report to: reports/xxx.md
```

### 8.2 New Behavior

If report generation succeeds:

```text
Saved report to: reports/2026-06-11-093242-ai.md
```

If report validation fails:

```text
Report validation failed.
Saved failure report to: reports/2026-06-11-092627-ai-failed.md
Run again or use --verbose to inspect intermediate workflow details.
```

### 8.3 State Signal

The save node needs to know whether it is saving a successful report or a failure report.

Add one field to `ResearchState`:

```python
report_status: Literal["success", "failed_validation"]
```

Rules:

- `write_report` sets `report_status="success"` when report passes validation.
- `write_report` sets `report_status="failed_validation"` when it replaces the report with a failure report.
- `save_report` uses `report_status` to choose the filename suffix.
- CLI uses `report_status` to choose terminal message.

If the field is missing for backward compatibility, treat it as `"success"`.

## 9. Progress Display

### 9.1 Current Behavior

The CLI prints all progress stages before invoking the graph:

```text
[1/6] Planning research...
[2/6] Searching web...
[3/6] Synthesizing notes...
[4/6] Writing report...
[5/6] Reviewing report...
[6/6] Saving report...
```

Then the actual workflow runs.

This is misleading because the terminal appears to reach `[6/6]` before any work has visibly completed.

### 9.2 v0.1.1 Minimum Behavior

Replace the fake per-stage output with honest workflow-level output:

```text
Starting research workflow...
This may take a few minutes while calling DeepSeek and Tavily.
```

After completion:

```text
Research workflow completed.
Saved report to: ...
```

This is the minimum acceptable v0.1.1 fix because it avoids false precision.

### 9.3 Optional Node-Aware Progress

If simple to implement, use LangGraph streaming or node wrappers to print each stage as it actually starts:

```text
[1/6] Planning research...
[2/6] Searching web...
[3/6] Synthesizing notes...
[4/6] Writing report...
[5/6] Reviewing report...
[6/6] Saving report...
```

Unlike v0.1.0, each line must be printed immediately before the corresponding node runs.

Recommended implementation:

- Add a small wrapper when building nodes in the CLI:

```python
def with_progress(label: str, node: Node) -> Node:
    def wrapped(state: ResearchState) -> ResearchState:
        console.print(label)
        return node(state)
    return wrapped
```

- Wrap the six CLI-created node functions.
- Keep graph structure unchanged.

This is preferred over deeper LangGraph instrumentation because it is simple, testable, and preserves the architecture.

## 10. Verbose Output

### 10.1 Current Behavior

`--verbose` only prints `errors` after the workflow finishes.

### 10.2 New Behavior

When `--verbose` is enabled, print a compact summary after the workflow finishes:

```text
Workflow details:

Subquestions:
1. <question>
   query: <search_query>
2. ...

Search results:
- q1: 5 result(s)
- q2: 4 result(s)

Research notes:
- q1: confidence=high, findings=3, sources=2
- q2: confidence=medium, findings=2, sources=2

Review:
- passed: True
- score: 92
- issues: 0
- suggestions: 2

Errors:
- ...
```

Rules:

- Do not print API keys.
- Do not print full raw Tavily responses.
- Do not print long full source contents.
- Keep summaries short.

## 11. Testing Strategy

Add or update tests for:

### 11.1 Failure Report Content

- Invalid URL failure report includes:
  - Chinese title `研究报告生成失败`
  - specific invalid URL
  - allowed URL list
  - user next steps

### 11.2 Failed Filename

- `make_report_filename(..., failed=True)` returns filename ending in `-failed.md`.
- `save_report(..., failed=True)` writes to a `-failed.md` path.

### 11.3 State Status

- Successful `write_report` sets `report_status="success"`.
- Validation failure sets `report_status="failed_validation"`.
- Save node uses `report_status` to choose failed filename.

### 11.4 CLI Messaging

- Successful fake workflow prints `Saved report to:`.
- Failed-validation fake workflow prints `Report validation failed.` and `Saved failure report to:`.

### 11.5 Progress Output

If using wrapper-based node progress:

- CLI tests or unit tests verify progress labels are emitted by wrappers in execution order.

If using minimum honest progress:

- CLI test verifies it prints `Starting research workflow...` and does not pre-print all six misleading stage lines before execution.

### 11.6 Verbose Output

- Given a fake result state with subquestions, search results, notes, review, and errors, verbose formatter prints compact summaries without source contents or secrets.

## 12. Acceptance Criteria

v0.1.1 passes when:

1. All existing tests still pass.
2. New tests for failure reports, failed filenames, CLI failure messaging, and verbose summaries pass.
3. A validation-failure report is clearly labeled as failed.
4. A validation-failure filename ends in `-failed.md`.
5. CLI output distinguishes success from validation failure.
6. CLI progress output is no longer misleading.
7. `--verbose` provides enough intermediate detail for a user to confirm that planning, searching, synthesis, writing, and review occurred.
8. No external API calls are made in default tests.

## 13. Recommended Implementation Order

1. Add `report_status` to `ResearchState`.
2. Refactor report validation failure generation into a structured helper.
3. Update failure report text to Chinese and include invalid URLs.
4. Add failed filename support in `filenames.py` and `report_writer.py`.
5. Update saving node to pass `failed=True` when `report_status="failed_validation"`.
6. Update CLI success/failure message.
7. Replace misleading progress output with wrapper-based node progress or honest workflow-level progress.
8. Add verbose summary formatter and tests.
9. Run full offline test suite.

## 14. Open Decisions

### Decision 1: Progress Implementation

Recommended: wrapper-based node progress in CLI.

Alternative: workflow-level honest progress only.

### Decision 2: Verbose Timing

Recommended: print verbose summary after workflow completion.

Alternative: print details as each node completes, which requires more invasive node instrumentation.

### Decision 3: Retry

Recommendation for v0.1.1: no automatic retry.

Reason: retry adds LLM cost and control-flow complexity. It should be designed separately for v0.2.
