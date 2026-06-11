# Deep Research Agent v0.1.1 Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Deep Research Agent v0.1.1 user feedback by making validation failures clear, failed reports distinguishable, progress output truthful, and `--verbose` useful for inspecting workflow artifacts.

**Architecture:** Keep the fixed LangGraph pipeline unchanged. Add a lightweight `report_status` state signal, structured report validation failure rendering inside the writing node, failed filename support in report writing utilities, CLI node wrappers for truthful progress, and a focused verbose summary formatter.

**Tech Stack:** Python 3.11+, uv, pytest, Typer, Rich, LangGraph, Pydantic.

---

## Current Repository Context

The project is now a git repository, but the existing v0.1.0 files are still untracked. Before implementing, create a baseline commit if the user has not already done so. Do not mix the baseline commit and v0.1.1 changes in one commit.

Current important files:

```text
src/deepresearch/state.py
src/deepresearch/nodes/writing.py
src/deepresearch/nodes/saving.py
src/deepresearch/utils/filenames.py
src/deepresearch/utils/report_writer.py
src/deepresearch/cli.py
tests/test_writing_node.py
tests/test_filenames.py
tests/test_report_writer.py
tests/test_cli.py
tests/test_integration_offline.py
```

---

## File Structure Changes

Modify existing files:

```text
src/deepresearch/state.py
src/deepresearch/nodes/writing.py
src/deepresearch/nodes/saving.py
src/deepresearch/utils/filenames.py
src/deepresearch/utils/report_writer.py
src/deepresearch/cli.py
tests/test_state.py
tests/test_writing_node.py
tests/test_filenames.py
tests/test_report_writer.py
tests/test_cli.py
tests/test_integration_offline.py
```

Create one new utility module:

```text
src/deepresearch/verbose.py
tests/test_verbose.py
```

Responsibilities:

- `state.py`: add `report_status` to `ResearchState`.
- `nodes/writing.py`: return `report_status` and render Chinese validation-failure reports with exact invalid URLs and reason text.
- `utils/filenames.py`: add failed filename suffix support.
- `utils/report_writer.py`: write failed reports to `-failed.md` when requested.
- `nodes/saving.py`: choose failed filename based on `report_status`.
- `cli.py`: distinguish success/failure messages; wrap nodes with progress output; call verbose formatter.
- `verbose.py`: format compact workflow summaries without secrets or large raw content.

---

### Task 0: Baseline repository state

**Files:**
- No code files changed.

- [ ] **Step 1: Check git state**

Run:

```bash
git status --short
```

Expected: many v0.1.0 project files may be untracked.

- [ ] **Step 2: Run current full tests before baseline**

Run:

```bash
uv run pytest -v
```

Expected: `47 passed`.

- [ ] **Step 3: Create baseline commit if files are untracked**

If `git status --short` shows v0.1.0 files as untracked, run:

```bash
git add .
git commit -m "chore: baseline deepresearch mvp"
```

Expected: commit succeeds.

If the baseline has already been committed, skip this step and report the current branch/status.

---

### Task 1: Add report status to state and writing node

**Files:**
- Modify: `src/deepresearch/state.py`
- Modify: `src/deepresearch/nodes/writing.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_writing_node.py`

- [ ] **Step 1: Add failing state test for report_status typing**

Append to `tests/test_state.py`:

```python
def test_research_state_accepts_report_status():
    from deepresearch.state import ResearchState

    state: ResearchState = {"question": "AI search", "report_status": "failed_validation"}

    assert state["report_status"] == "failed_validation"
```

- [ ] **Step 2: Add failing writing node tests for report_status**

Append to `tests/test_writing_node.py`:

```python
def test_write_report_sets_success_status_for_valid_report():
    llm = FakeLLMClient(["# AI Search\n\nCited claim: https://example.com\n\n## Sources\n\n- https://example.com"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert result["report_status"] == "success"


def test_write_report_sets_failed_validation_status_for_invalid_url():
    llm = FakeLLMClient(["# AI Search\n\nInvented citation: https://invented.example/source"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert result["report_status"] == "failed_validation"
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_state.py tests/test_writing_node.py -v
```

Expected: new writing status assertions fail because `report_status` is missing.

- [ ] **Step 4: Add report_status to ResearchState**

Modify `src/deepresearch/state.py` imports and `ResearchState`:

```python
from typing import Literal, TypedDict
```

Ensure `ResearchState` includes:

```python
    report_status: Literal["success", "failed_validation"]
```

- [ ] **Step 5: Set report_status in writing node**

In `src/deepresearch/nodes/writing.py`:

- When no results or notes exist, return `report_status="failed_validation"`.
- When validation fails, return `report_status="failed_validation"`.
- When report passes validation, return `report_status="success"`.

The final valid return should be:

```python
return {**state, "report_markdown": report, "report_status": "success"}
```

Each invalid return should include:

```python
return {**state, "report_markdown": report, "errors": errors, "report_status": "failed_validation"}
```

- [ ] **Step 6: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_state.py tests/test_writing_node.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/deepresearch/state.py src/deepresearch/nodes/writing.py tests/test_state.py tests/test_writing_node.py
git commit -m "feat: track report validation status"
```

---

### Task 2: Improve validation-failure report content

**Files:**
- Modify: `src/deepresearch/nodes/writing.py`
- Modify: `tests/test_writing_node.py`

- [ ] **Step 1: Add failing tests for Chinese failure report and invalid URLs**

Append to `tests/test_writing_node.py`:

```python
def test_invalid_url_failure_report_is_chinese_and_lists_invalid_url():
    llm = FakeLLMClient(["# AI Search\n\nInvented citation: https://invented.example/source"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI 搜索",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    report = result["report_markdown"]
    assert "# 研究报告生成失败" in report
    assert "## 失败原因" in report
    assert "模型生成的报告包含未被搜索结果支持的来源 URL" in report
    assert "## 非法来源 URL" in report
    assert "https://invented.example/source" in report
    assert "## 可用来源 URL" in report
    assert "https://example.com" in report
    assert "## 你可以怎么做" in report
    assert "--results-per-query" in report


def test_missing_sources_failure_report_uses_specific_reason():
    llm = FakeLLMClient(["# AI Search\n\nCited claim: https://example.com"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI 搜索",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert "模型生成的报告缺少 ## Sources 来源部分" in result["report_markdown"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_writing_node.py -v
```

Expected: new tests fail because the failure report is still English and generic.

- [ ] **Step 3: Implement structured failure rendering**

In `src/deepresearch/nodes/writing.py`, add imports:

```python
from dataclasses import dataclass
from typing import Literal
```

Add after regex constants:

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

Replace `_safe_invalid_source_report` with:

```python
def _format_urls(urls: list[str]) -> str:
    return "\n".join(f"- {url}" for url in urls) if urls else "- None"


def _validation_failure_report(question: str, failure: ReportValidationFailure) -> str:
    return (
        "# 研究报告生成失败\n\n"
        f"本次报告没有发布，因为生成内容未通过来源校验。\n\n"
        "## 失败原因\n\n"
        f"{failure.message}\n\n"
        "## 非法来源 URL\n\n"
        f"{_format_urls(failure.invalid_urls)}\n\n"
        "## 可用来源 URL\n\n"
        "以下 URL 来自本次 Tavily 搜索结果，报告只能引用这些来源：\n\n"
        f"{_format_urls(failure.allowed_urls)}\n\n"
        "## 你可以怎么做\n\n"
        "- 重新运行一次同样的问题。\n"
        "- 使用更具体的研究问题。\n"
        "- 增加 `--results-per-query` 以提供更多可用来源。\n"
        "- 使用 `--verbose` 查看子问题、搜索 query 和搜索结果数量。\n"
    )
```

Add helper:

```python
def _make_failure(question: str, reason: str, message: str, invalid_urls: list[str], allowed_urls: set[str]) -> str:
    failure = ReportValidationFailure(
        reason=reason,  # type: ignore[arg-type]
        message=message,
        invalid_urls=invalid_urls,
        allowed_urls=sorted(allowed_urls),
    )
    return _validation_failure_report(question, failure)
```

Then update validation branches:

```python
if invalid_urls:
    errors.append(f"Report contains invalid source URL(s) outside search_results: {', '.join(invalid_urls)}")
    report = _make_failure(
        state["question"],
        "invalid_urls",
        "模型生成的报告包含未被搜索结果支持的来源 URL，因此系统拒绝保存该报告正文。",
        invalid_urls,
        allowed_urls,
    )
    return {**state, "report_markdown": report, "errors": errors, "report_status": "failed_validation"}
```

For no citations:

```python
report = _make_failure(
    state["question"],
    "no_citations",
    "模型生成的报告没有在正文中引用任何可用来源。",
    [],
    allowed_urls,
)
```

For missing sources:

```python
report = _make_failure(
    state["question"],
    "missing_sources_section",
    "模型生成的报告缺少 ## Sources 来源部分。",
    [],
    allowed_urls,
)
```

For missing body citations:

```python
report = _make_failure(
    state["question"],
    "missing_body_citations",
    "模型生成的报告只在 Sources 部分列出来源，但正文关键论点没有引用来源。",
    [],
    allowed_urls,
)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_writing_node.py -v
```

Expected: all writing node tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/nodes/writing.py tests/test_writing_node.py
git commit -m "feat: improve report validation failure output"
```

---

### Task 3: Failed filename support

**Files:**
- Modify: `src/deepresearch/utils/filenames.py`
- Modify: `src/deepresearch/utils/report_writer.py`
- Modify: `src/deepresearch/nodes/saving.py`
- Modify: `tests/test_filenames.py`
- Modify: `tests/test_report_writer.py`
- Create or modify: `tests/test_saving_node.py`

- [ ] **Step 1: Add failing filename tests**

Append to `tests/test_filenames.py`:

```python
def test_make_failed_report_filename_contains_failed_suffix():
    now = datetime(2026, 6, 11, 9, 26, 27)

    filename = make_report_filename("AI Search", failed=True, now=now)

    assert filename == "2026-06-11-092627-ai-search-failed.md"
```

- [ ] **Step 2: Add failing report writer test**

Append to `tests/test_report_writer.py`:

```python
def test_save_report_writes_failed_filename(tmp_path):
    review = ReviewResult(passed=False, score=0, issues=["Failed"], suggestions=[])
    now = datetime(2026, 6, 11, 9, 26, 27)

    output_path = save_report(
        question="AI Search",
        report_markdown="# 研究报告生成失败",
        review=review,
        output_dir=tmp_path,
        failed=True,
        now=now,
    )

    assert output_path.name == "2026-06-11-092627-ai-search-failed.md"
    assert output_path.exists()
```

- [ ] **Step 3: Add failing saving node test**

Create `tests/test_saving_node.py`:

```python
from deepresearch.nodes.saving import make_save_report_node
from deepresearch.state import ReviewResult


def test_save_report_node_uses_failed_filename_for_failed_validation(tmp_path):
    node = make_save_report_node(tmp_path)

    result = node({
        "question": "AI Search",
        "report_markdown": "# 研究报告生成失败",
        "review": ReviewResult(passed=False, score=0, issues=[], suggestions=[]),
        "report_status": "failed_validation",
    })

    assert result["output_path"].endswith("-failed.md")
```

- [ ] **Step 4: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_filenames.py tests/test_report_writer.py tests/test_saving_node.py -v
```

Expected: failures because `failed` argument is unsupported.

- [ ] **Step 5: Implement failed filename support**

Modify `src/deepresearch/utils/filenames.py`:

```python
def make_report_filename(question: str, *, failed: bool = False, now: datetime | None = None) -> str:
    current = now or datetime.now()
    timestamp = current.strftime("%Y-%m-%d-%H%M%S")
    slug = slugify_question(question)
    suffix = "-failed" if failed else ""
    return f"{timestamp}-{slug}{suffix}.md"
```

- [ ] **Step 6: Update report writer**

Modify `src/deepresearch/utils/report_writer.py` signature:

```python
def save_report(
    question: str,
    report_markdown: str,
    review: ReviewResult,
    output_dir: str | Path,
    failed: bool = False,
    now: datetime | None = None,
) -> Path:
```

Inside the function:

```python
path = directory / make_report_filename(question, failed=failed, now=now)
```

- [ ] **Step 7: Update saving node**

Modify `src/deepresearch/nodes/saving.py`:

```python
failed = state.get("report_status") == "failed_validation"
path = save_report(
    question=state["question"],
    report_markdown=state.get("report_markdown", ""),
    review=state["review"],
    output_dir=output_dir,
    failed=failed,
)
```

- [ ] **Step 8: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_filenames.py tests/test_report_writer.py tests/test_saving_node.py -v
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/deepresearch/utils/filenames.py src/deepresearch/utils/report_writer.py src/deepresearch/nodes/saving.py tests/test_filenames.py tests/test_report_writer.py tests/test_saving_node.py
git commit -m "feat: mark failed validation reports in filenames"
```

---

### Task 4: CLI success/failure messaging and progress wrappers

**Files:**
- Modify: `src/deepresearch/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add fake app helpers to CLI tests**

Append to `tests/test_cli.py`:

```python
from deepresearch.state import ReviewResult


class FakeResearchApp:
    def __init__(self, result):
        self.result = result
        self.inputs = []

    def invoke(self, state):
        self.inputs.append(state)
        return self.result


def _set_required_env(monkeypatch):
    monkeypatch.setattr(deepresearch.config, "load_dotenv", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-tavily-key")
```

- [ ] **Step 2: Add failing CLI success/failure messaging tests**

Append to `tests/test_cli.py`:

```python
def test_cli_prints_success_message_for_successful_report(monkeypatch):
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "report_markdown": "# Report\n\nBody",
        "output_path": "reports/success.md",
        "report_status": "success",
        "review": ReviewResult(passed=True, score=90, issues=[], suggestions=[]),
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda _config: fake_app)

    result = runner.invoke(app, ["AI search"])

    assert result.exit_code == 0
    assert "Saved report to: reports/success.md" in result.output
    assert "Report validation failed." not in result.output


def test_cli_prints_failure_message_for_failed_validation(monkeypatch):
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "report_markdown": "# 研究报告生成失败",
        "output_path": "reports/failed-failed.md",
        "report_status": "failed_validation",
        "review": ReviewResult(passed=False, score=0, issues=[], suggestions=[]),
        "errors": ["Report contains invalid source URL(s) outside search_results: https://invalid.example"],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda _config: fake_app)

    result = runner.invoke(app, ["AI search"])

    assert result.exit_code == 0
    assert "Report validation failed." in result.output
    assert "Saved failure report to: reports/failed-failed.md" in result.output
    assert "Run again or use --verbose" in result.output
```

- [ ] **Step 3: Add failing progress wrapper test**

Append to `tests/test_cli.py`:

```python
def test_with_progress_prints_label_before_running_node(capsys):
    from deepresearch.cli import _with_progress

    calls = []

    def node(state):
        calls.append("node-ran")
        return {**state, "done": True}

    wrapped = _with_progress("[1/6] Planning research...", node)
    result = wrapped({"question": "AI search"})

    captured = capsys.readouterr()
    assert "[1/6] Planning research..." in captured.out
    assert calls == ["node-ran"]
    assert result["done"] is True
```

- [ ] **Step 4: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_cli.py -v
```

Expected: failure because `_with_progress` and new messages do not exist.

- [ ] **Step 5: Implement progress wrapper**

In `src/deepresearch/cli.py`, add after `console = Console()`:

```python
def _with_progress(label: str, node):
    def wrapped(state):
        console.print(label)
        return node(state)

    return wrapped
```

Update `_build_app` to create node functions first and wrap them:

```python
plan_research = make_plan_research_node(llm, config.max_subquestions)
search_web = make_search_web_node(search, config.results_per_query)
synthesize_notes = make_synthesize_notes_node(llm)
write_report = make_write_report_node(llm)
review_report = make_review_report_node(llm)
save_report = make_save_report_node(config.output_dir)

return create_research_app(
    plan_research=_with_progress("[1/6] Planning research...", plan_research),
    search_web=_with_progress("[2/6] Searching web...", search_web),
    synthesize_notes=_with_progress("[3/6] Synthesizing notes...", synthesize_notes),
    write_report=_with_progress("[4/6] Writing report...", write_report),
    review_report=_with_progress("[5/6] Reviewing report...", review_report),
    save_report=_with_progress("[6/6] Saving report...", save_report),
)
```

Remove the `steps = [...]` pre-print block from `main()`.

- [ ] **Step 6: Implement success/failure messages**

Replace:

```python
console.print(f"\nSaved report to: {result['output_path']}\n")
```

with:

```python
if result.get("report_status") == "failed_validation":
    console.print("\nReport validation failed.")
    console.print(f"Saved failure report to: {result['output_path']}")
    console.print("Run again or use --verbose to inspect intermediate workflow details.\n")
else:
    console.print(f"\nSaved report to: {result['output_path']}\n")
```

- [ ] **Step 7: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_cli.py -v
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add src/deepresearch/cli.py tests/test_cli.py
git commit -m "feat: improve CLI progress and report status messages"
```

---

### Task 5: Verbose workflow summary

**Files:**
- Create: `src/deepresearch/verbose.py`
- Create: `tests/test_verbose.py`
- Modify: `src/deepresearch/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add verbose formatter tests**

Create `tests/test_verbose.py`:

```python
from deepresearch.state import ResearchNote, ReviewResult, SearchResult, SubQuestion
from deepresearch.verbose import format_verbose_summary


def test_format_verbose_summary_includes_compact_workflow_details():
    state = {
        "subquestions": [SubQuestion(id="q1", question="What is AI search?", search_query="AI search", rationale="Background")],
        "search_results": [
            SearchResult(subquestion_id="q1", title="A", url="https://example.com/a", content="Long content should not appear"),
            SearchResult(subquestion_id="q1", title="B", url="https://example.com/b", content="More long content should not appear"),
        ],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding 1", "Finding 2"], source_urls=["https://example.com/a"], confidence="high")],
        "review": ReviewResult(passed=True, score=92, issues=[], suggestions=["Add examples"]),
        "errors": ["One warning"],
    }

    summary = format_verbose_summary(state)

    assert "Workflow details:" in summary
    assert "Subquestions:" in summary
    assert "What is AI search?" in summary
    assert "query: AI search" in summary
    assert "Search results:" in summary
    assert "q1: 2 result(s)" in summary
    assert "Research notes:" in summary
    assert "q1: confidence=high, findings=2, sources=1" in summary
    assert "Review:" in summary
    assert "score: 92" in summary
    assert "Errors:" in summary
    assert "One warning" in summary
    assert "Long content should not appear" not in summary
```

- [ ] **Step 2: Add CLI verbose test**

Append to `tests/test_cli.py`:

```python
def test_cli_verbose_prints_workflow_summary(monkeypatch):
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "subquestions": [],
        "search_results": [],
        "notes": [],
        "report_markdown": "# Report\n\nBody",
        "output_path": "reports/success.md",
        "report_status": "success",
        "review": ReviewResult(passed=True, score=90, issues=[], suggestions=[]),
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda _config: fake_app)

    result = runner.invoke(app, ["AI search", "--verbose"])

    assert result.exit_code == 0
    assert "Workflow details:" in result.output
    assert "Subquestions:" in result.output
    assert "Review:" in result.output
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_verbose.py tests/test_cli.py -v
```

Expected: failure because `deepresearch.verbose` does not exist and CLI does not print summary.

- [ ] **Step 4: Implement verbose formatter**

Create `src/deepresearch/verbose.py`:

```python
from collections import Counter
from typing import Any


def format_verbose_summary(state: dict[str, Any]) -> str:
    lines: list[str] = ["Workflow details:", ""]

    subquestions = state.get("subquestions", [])
    lines.append("Subquestions:")
    if subquestions:
        for index, item in enumerate(subquestions, start=1):
            lines.append(f"{index}. {item.question}")
            lines.append(f"   query: {item.search_query}")
    else:
        lines.append("- None")

    results = state.get("search_results", [])
    result_counts = Counter(item.subquestion_id for item in results)
    lines.extend(["", "Search results:"])
    if result_counts:
        for subquestion_id, count in sorted(result_counts.items()):
            lines.append(f"- {subquestion_id}: {count} result(s)")
    else:
        lines.append("- None")

    notes = state.get("notes", [])
    lines.extend(["", "Research notes:"])
    if notes:
        for note in notes:
            lines.append(
                f"- {note.subquestion_id}: confidence={note.confidence}, "
                f"findings={len(note.key_findings)}, sources={len(note.source_urls)}"
            )
    else:
        lines.append("- None")

    review = state.get("review")
    lines.extend(["", "Review:"])
    if review is not None:
        lines.append(f"- passed: {review.passed}")
        lines.append(f"- score: {review.score}")
        lines.append(f"- issues: {len(review.issues)}")
        lines.append(f"- suggestions: {len(review.suggestions)}")
    else:
        lines.append("- None")

    errors = state.get("errors", [])
    lines.extend(["", "Errors:"])
    if errors:
        for error in errors:
            lines.append(f"- {error}")
    else:
        lines.append("- None")

    return "\n".join(lines)
```

- [ ] **Step 5: Wire verbose formatter into CLI**

In `src/deepresearch/cli.py`, import:

```python
from deepresearch.verbose import format_verbose_summary
```

Replace the existing verbose errors block:

```python
if verbose and result.get("errors"):
    console.print("\nErrors:")
    for error in result["errors"]:
        console.print(f"- {error}")
```

with:

```python
if verbose:
    console.print("\n" + format_verbose_summary(result))
```

- [ ] **Step 6: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_verbose.py tests/test_cli.py -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/deepresearch/verbose.py src/deepresearch/cli.py tests/test_verbose.py tests/test_cli.py
git commit -m "feat: add verbose workflow summary"
```

---

### Task 6: Update offline integration and README

**Files:**
- Modify: `tests/test_integration_offline.py`
- Modify: `README.md`

- [ ] **Step 1: Update offline integration assertions**

Modify `tests/test_integration_offline.py` to assert successful status:

```python
assert result["report_status"] == "success"
```

Place it after:

```python
assert result["review"].score == 90
```

- [ ] **Step 2: Update README for v0.1.1 behavior**

In `README.md`, add a section after `## Output`:

```markdown
## Validation failures

If the model generates a report that uses unsupported source URLs, the tool refuses to publish that report body. It saves a failure report ending in `-failed.md` and lists the invalid URLs and allowed Tavily URLs.

Example failure path:

```text
reports/2026-06-11-092627-ai-failed.md
```

## Verbose mode

Use `--verbose` to inspect workflow summaries:

```bash
uv run deepresearch "AI 搜索引擎的发展趋势" --verbose
```

Verbose mode prints subquestions, search query summaries, result counts, research note counts, review score, and non-fatal errors. It does not print API keys or full raw search payloads.
```

- [ ] **Step 3: Run full tests**

Run:

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_offline.py README.md
git commit -m "docs: document validation failures and verbose mode"
```

---

### Task 7: Final verification

**Files:**
- No new code files unless fixes are needed.

- [ ] **Step 1: Run full offline test suite**

Run:

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run safe missing-key CLI check**

Run in PowerShell:

```powershell
$env:DEEPSEEK_API_KEY=$null; $env:TAVILY_API_KEY=$null; $env:PYTHON_DOTENV_DISABLED='1'; uv run deepresearch "AI search"
```

Expected:

```text
Error: DEEPSEEK_API_KEY is not set. Copy .env.example to .env and fill it in.
```

Exit code should be non-zero.

- [ ] **Step 3: Run CLI help**

Run:

```bash
uv run deepresearch --help
```

Expected: help includes `--verbose`, `--max-subquestions`, `--results-per-query`, `--output-dir`, and `--model`.

- [ ] **Step 4: Inspect git status**

Run:

```bash
git status --short
```

Expected: clean working tree except intentionally untracked local files such as `.env` or generated reports. If generated report Markdown files are untracked, verify `.gitignore` excludes `reports/*.md`.

- [ ] **Step 5: Do not run online smoke test by default**

Do not call DeepSeek or Tavily unless explicitly authorized. Online smoke test remains manual:

```bash
uv run deepresearch "AI 搜索引擎的发展趋势"
```

---

## Self-Review

Spec coverage:

- Failure report Chinese content and invalid URL listing: Task 2.
- Failed filename suffix: Task 3.
- `report_status` state signal: Task 1 and Task 3.
- CLI success/failure messaging: Task 4.
- Honest/node progress: Task 4.
- Verbose summary: Task 5.
- README updates: Task 6.
- No automatic retry: no task implements retry.
- Tests and no external API by default: Tasks 1-7.

Placeholder scan:

- No placeholder task remains.
- Code snippets define exact functions and assertions.
- Open decisions from the spec are resolved for this plan:
  - Progress: wrapper-based node progress.
  - Verbose timing: after workflow completion.
  - Retry: not implemented in v0.1.1.

Type consistency:

- `report_status` uses `Literal["success", "failed_validation"]` consistently.
- `failed` filename flag is passed through `make_report_filename()`, `save_report()`, and saving node.
- CLI uses `result.get("report_status")` with missing field treated as success.
