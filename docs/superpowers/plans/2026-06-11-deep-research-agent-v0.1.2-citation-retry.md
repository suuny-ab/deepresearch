# Deep Research Agent v0.1.2 Citation Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现严格 `[n]` 编号引用校验，并在第一次引用校验失败后自动重写一次，提高在线成功报告生成率。

**Architecture:** 保持现有 LangGraph 主流程不变，把 citation parse/validate/retry 封装在 `write_report` 节点内部。新增独立 citation validator 模块，更新 writer prompt、写作节点状态元数据、失败报告和 verbose 摘要；review 节点继续只审核 `write_report` 输出的最终报告。

**Tech Stack:** Python 3.11+、uv、pytest、Pydantic、LangGraph、Typer/Rich；文档中文，代码标识符英文。

---

## 当前上下文

v0.1.1 已实现并通过改进验收，但在线 `--verbose` 冒烟测试显示成功报告生成率不足。失败原因是报告正文未使用 validator 认可的正文引用格式。

当前关键文件：

```text
src/deepresearch/nodes/writing.py
src/deepresearch/prompts/writing.py
src/deepresearch/verbose.py
src/deepresearch/state.py
tests/test_writing_node.py
tests/test_verbose.py
tests/test_integration_offline.py
```

当前 git 状态存在一个与本计划无关的已新增文件：

```text
docs/superpowers/reports/2026-06-11-v0.1.1-acceptance-report-zh.md
```

执行本计划时不要修改或提交这个文件，除非用户明确要求。

---

## 文件结构变化

新增：

```text
src/deepresearch/citations.py
tests/test_citations.py
```

修改：

```text
src/deepresearch/state.py
src/deepresearch/prompts/writing.py
src/deepresearch/nodes/writing.py
src/deepresearch/verbose.py
tests/test_state.py
tests/test_writing_node.py
tests/test_verbose.py
tests/test_integration_offline.py
README.md
```

职责：

- `citations.py`：解析正文 `[n]`、解析 `## Sources`、执行严格 citation validation。
- `prompts/writing.py`：强制 writer 使用 `[n]` 编号引用，不允许正文裸 URL。
- `nodes/writing.py`：生成初稿、校验、必要时自动重写一次、输出最终报告或完整失败报告。
- `state.py`：增加 retry/validation metadata。
- `verbose.py`：显示 rewrite_attempted、validation_attempts、每次失败 reason。

---

### Task 0: 预检当前仓库状态

**Files:**
- 不修改代码文件。

- [ ] **Step 1: 检查工作区**

Run:

```bash
git status --short
```

Expected:

```text
A  docs/superpowers/reports/2026-06-11-v0.1.1-acceptance-report-zh.md
```

如果还有其他未提交改动，停止并报告。

- [ ] **Step 2: 运行当前离线测试**

Run:

```bash
uv run pytest -v
```

Expected:

```text
62 passed
```

- [ ] **Step 3: 不提交预检结果**

本任务不产生 commit。

---

### Task 1: 新增 citation parser 和严格 validator

**Files:**
- Create: `src/deepresearch/citations.py`
- Create: `tests/test_citations.py`

- [ ] **Step 1: 编写失败测试**

Create `tests/test_citations.py`:

```python
from deepresearch.citations import validate_citations


ALLOWED_URLS = {
    "https://example.com/a",
    "https://example.com/b",
    "https://example.com/c",
}


def test_validate_numbered_citation_success():
    report = """# Report

AI search is changing discovery.[1]

## Sources

[1] https://example.com/a
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is True
    assert result.reason is None
    assert result.body_citations == {1}
    assert result.source_citations == {1}


def test_validate_fails_when_sources_section_missing():
    report = "# Report\n\nAI search is changing discovery.[1]"

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "missing_sources_section"


def test_validate_fails_when_body_has_no_numbered_citations():
    report = """# Report

AI search is changing discovery.

## Sources

[1] https://example.com/a
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "missing_body_citations"


def test_validate_fails_for_undefined_body_citation():
    report = """# Report

AI search is changing discovery.[1][2]

## Sources

[1] https://example.com/a
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "undefined_citations"
    assert result.undefined_citations == {2}


def test_validate_fails_for_unused_source_number():
    report = """# Report

AI search is changing discovery.[1]

## Sources

[1] https://example.com/a
[2] https://example.com/b
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "unused_sources"
    assert result.unused_sources == {2}


def test_validate_fails_for_invalid_source_url():
    report = """# Report

AI search is changing discovery.[1]

## Sources

[1] https://invalid.example/x
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "invalid_source_urls"
    assert result.invalid_source_urls == ["https://invalid.example/x"]


def test_validate_fails_for_bare_url_in_body():
    report = """# Report

AI search is changing discovery https://example.com/a [1]

## Sources

[1] https://example.com/a
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is False
    assert result.reason == "bare_urls_in_body"
    assert result.bare_body_urls == ["https://example.com/a"]


def test_validate_supports_sources_line_variants():
    report = """# Report

A.[1]
B.[2]
C.[3]

## Sources

[1] https://example.com/a
[2]: https://example.com/b
- [3] https://example.com/c - Source title
"""

    result = validate_citations(report, ALLOWED_URLS)

    assert result.passed is True
    assert result.source_urls == {
        1: "https://example.com/a",
        2: "https://example.com/b",
        3: "https://example.com/c",
    }
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_citations.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'deepresearch.citations'
```

- [ ] **Step 3: 实现 citation validator**

Create `src/deepresearch/citations.py`:

```python
import re
from dataclasses import dataclass, field
from typing import Literal

CitationFailureReason = Literal[
    "missing_sources_section",
    "missing_body_citations",
    "undefined_citations",
    "unused_sources",
    "invalid_source_urls",
    "bare_urls_in_body",
]

_SOURCES_HEADING_RE = re.compile(r"^##\s+Sources\s*$", re.IGNORECASE | re.MULTILINE)
_CITATION_RE = re.compile(r"\[(\d+)\]")
_SOURCE_LINE_RE = re.compile(r"^\s*-?\s*\[(\d+)\]\s*:??\s+(https?://\S+)", re.MULTILINE)
_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


@dataclass(frozen=True)
class CitationValidationResult:
    passed: bool
    reason: CitationFailureReason | None = None
    message: str = ""
    body_citations: set[int] = field(default_factory=set)
    source_citations: set[int] = field(default_factory=set)
    source_urls: dict[int, str] = field(default_factory=dict)
    undefined_citations: set[int] = field(default_factory=set)
    unused_sources: set[int] = field(default_factory=set)
    invalid_source_urls: list[str] = field(default_factory=list)
    bare_body_urls: list[str] = field(default_factory=list)
    allowed_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "message": self.message,
            "body_citations": sorted(self.body_citations),
            "source_citations": sorted(self.source_citations),
            "source_urls": dict(sorted(self.source_urls.items())),
            "undefined_citations": sorted(self.undefined_citations),
            "unused_sources": sorted(self.unused_sources),
            "invalid_source_urls": self.invalid_source_urls,
            "bare_body_urls": self.bare_body_urls,
            "allowed_urls": self.allowed_urls,
        }


def _clean_url(url: str) -> str:
    return url.rstrip(".,;:)"]}")


def split_sources(report: str) -> tuple[str, str | None]:
    match = _SOURCES_HEADING_RE.search(report)
    if not match:
        return report, None
    return report[: match.start()], report[match.end() :]


def extract_body_citations(body: str) -> set[int]:
    return {int(match) for match in _CITATION_RE.findall(body)}


def extract_source_urls(sources: str) -> dict[int, str]:
    parsed: dict[int, str] = {}
    for number, url in _SOURCE_LINE_RE.findall(sources):
        parsed[int(number)] = _clean_url(url)
    return parsed


def extract_urls(text: str) -> list[str]:
    return [_clean_url(match) for match in _URL_RE.findall(text)]


def validate_citations(report: str, allowed_urls: set[str]) -> CitationValidationResult:
    body, sources = split_sources(report)
    allowed = sorted(allowed_urls)

    if sources is None:
        return CitationValidationResult(
            passed=False,
            reason="missing_sources_section",
            message="报告缺少 ## Sources 来源部分。",
            allowed_urls=allowed,
        )

    bare_body_urls = extract_urls(body)
    if bare_body_urls:
        return CitationValidationResult(
            passed=False,
            reason="bare_urls_in_body",
            message="正文中出现裸 URL，URL 只能出现在 ## Sources 部分。",
            bare_body_urls=bare_body_urls,
            allowed_urls=allowed,
        )

    body_citations = extract_body_citations(body)
    source_urls = extract_source_urls(sources)
    source_citations = set(source_urls)

    if not body_citations:
        return CitationValidationResult(
            passed=False,
            reason="missing_body_citations",
            message="正文没有使用编号引用，例如 [1]、[2]。",
            body_citations=body_citations,
            source_citations=source_citations,
            source_urls=source_urls,
            allowed_urls=allowed,
        )

    undefined = body_citations - source_citations
    if undefined:
        return CitationValidationResult(
            passed=False,
            reason="undefined_citations",
            message=f"正文引用了未在 Sources 中定义的编号：{sorted(undefined)}。",
            body_citations=body_citations,
            source_citations=source_citations,
            source_urls=source_urls,
            undefined_citations=undefined,
            allowed_urls=allowed,
        )

    unused = source_citations - body_citations
    if unused:
        return CitationValidationResult(
            passed=False,
            reason="unused_sources",
            message=f"Sources 中存在未被正文引用的编号：{sorted(unused)}。",
            body_citations=body_citations,
            source_citations=source_citations,
            source_urls=source_urls,
            unused_sources=unused,
            allowed_urls=allowed,
        )

    invalid_urls = sorted(url for url in source_urls.values() if url not in allowed_urls)
    if invalid_urls:
        return CitationValidationResult(
            passed=False,
            reason="invalid_source_urls",
            message="Sources 中存在未被搜索结果支持的 URL。",
            body_citations=body_citations,
            source_citations=source_citations,
            source_urls=source_urls,
            invalid_source_urls=invalid_urls,
            allowed_urls=allowed,
        )

    return CitationValidationResult(
        passed=True,
        body_citations=body_citations,
        source_citations=source_citations,
        source_urls=source_urls,
        allowed_urls=allowed,
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_citations.py -v
```

Expected: all tests pass.

- [ ] **Step 5: 提交**

```bash
git add src/deepresearch/citations.py tests/test_citations.py
git commit -m "feat: add strict citation validator"
```

---

### Task 2: 更新 writer prompt 为严格编号引用

**Files:**
- Modify: `src/deepresearch/prompts/writing.py`
- Create: `tests/test_writing_prompt.py`

- [ ] **Step 1: 编写失败测试**

Create `tests/test_writing_prompt.py`:

```python
from deepresearch.prompts.writing import build_writing_prompt


def test_writing_prompt_requires_numbered_citations():
    prompt = build_writing_prompt("AI search", [], [], [])

    assert "Use numbered citations in the body" in prompt
    assert "[1]" in prompt
    assert "Do not put raw URLs in the body" in prompt
    assert "URLs may only appear in the ## Sources section" in prompt
    assert "Every citation number used in the body must be defined in ## Sources" in prompt
    assert "Every source listed in ## Sources must be cited in the body" in prompt
    assert "Only use URLs from the allowed source URL list" in prompt
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_writing_prompt.py -v
```

Expected: fails because prompt does not contain strict citation contract.

- [ ] **Step 3: 更新 prompt**

Modify `src/deepresearch/prompts/writing.py` return text. Replace the current citation wording with:

```python
    return f"""
请使用中文撰写结构化 Markdown 深度研究报告，除非用户问题使用其他语言。

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

Sources format:
[1] https://example.com/source-a
[2] https://example.com/source-b

Original question:
{question}

Subquestions:
{[item.model_dump() for item in subquestions]}

Research notes:
{[item.model_dump() for item in notes]}

Allowed source URLs:
{allowed_urls}
""".strip()
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_writing_prompt.py -v
```

Expected: pass.

- [ ] **Step 5: 提交**

```bash
git add src/deepresearch/prompts/writing.py tests/test_writing_prompt.py
git commit -m "feat: require numbered citations in writer prompt"
```

---

### Task 3: 扩展 state metadata 与 verbose 输出

**Files:**
- Modify: `src/deepresearch/state.py`
- Modify: `src/deepresearch/verbose.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_verbose.py`

- [ ] **Step 1: 添加 state 测试**

Append to `tests/test_state.py`:

```python
def test_research_state_accepts_validation_retry_metadata():
    from deepresearch.state import ResearchState

    state: ResearchState = {
        "question": "AI search",
        "rewrite_attempted": True,
        "validation_attempts": 2,
        "validation_failures": [
            {"reason": "missing_body_citations", "message": "正文没有使用编号引用。"},
            {"reason": "unused_sources", "message": "Sources 中存在未被正文引用的编号。"},
        ],
    }

    assert state["rewrite_attempted"] is True
    assert state["validation_attempts"] == 2
    assert len(state["validation_failures"]) == 2
```

- [ ] **Step 2: 添加 verbose 测试**

Append to `tests/test_verbose.py`:

```python
def test_format_verbose_summary_includes_validation_retry_metadata():
    state = {
        "report_status": "failed_validation",
        "rewrite_attempted": True,
        "validation_attempts": 2,
        "validation_failures": [
            {"reason": "missing_body_citations", "message": "正文没有使用编号引用。"},
            {"reason": "unused_sources", "message": "Sources 中存在未被正文引用的编号。"},
        ],
    }

    summary = format_verbose_summary(state)

    assert "Report validation:" in summary
    assert "rewrite_attempted: True" in summary
    assert "validation_attempts: 2" in summary
    assert "final_status: failed_validation" in summary
    assert "attempt 1: missing_body_citations" in summary
    assert "attempt 2: unused_sources" in summary
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_state.py tests/test_verbose.py -v
```

Expected: verbose test fails because validation metadata is not printed.

- [ ] **Step 4: 更新 ResearchState**

Modify `src/deepresearch/state.py` imports:

```python
from typing import Any, Literal, TypedDict
```

Add fields:

```python
    rewrite_attempted: bool
    validation_attempts: int
    validation_failures: list[dict[str, Any]]
```

- [ ] **Step 5: 更新 verbose formatter**

Modify `src/deepresearch/verbose.py` before Errors section:

```python
    lines.extend(["", "Report validation:"])
    lines.append(f"- rewrite_attempted: {state.get('rewrite_attempted', False)}")
    lines.append(f"- validation_attempts: {state.get('validation_attempts', 0)}")
    lines.append(f"- final_status: {state.get('report_status', 'unknown')}")
    failures = state.get("validation_failures", [])
    if failures:
        for index, failure in enumerate(failures, start=1):
            reason = failure.get("reason", "unknown") if isinstance(failure, dict) else "unknown"
            lines.append(f"- attempt {index}: {reason}")
    else:
        lines.append("- failures: None")
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_state.py tests/test_verbose.py -v
```

Expected: pass.

- [ ] **Step 7: 提交**

```bash
git add src/deepresearch/state.py src/deepresearch/verbose.py tests/test_state.py tests/test_verbose.py
git commit -m "feat: expose citation retry metadata"
```

---

### Task 4: 重构 write_report 使用 citation validator，无 retry

**Files:**
- Modify: `src/deepresearch/nodes/writing.py`
- Modify: `tests/test_writing_node.py`

- [ ] **Step 1: 添加编号引用成功测试**

Append to `tests/test_writing_node.py`:

```python
def test_write_report_accepts_numbered_citations_with_sources_mapping():
    llm = FakeLLMClient(["# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert result["report_status"] == "success"
    assert result["rewrite_attempted"] is False
    assert result["validation_attempts"] == 1
    assert result["validation_failures"] == []
```

- [ ] **Step 2: 添加严格失败测试**

Append to `tests/test_writing_node.py`:

```python
def test_write_report_rejects_unused_source_number_without_retry_yet():
    llm = FakeLLMClient(["# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com\n[2] https://example.com/extra"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [
            SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content"),
            SearchResult(subquestion_id="q1", title="Extra", url="https://example.com/extra", content="Content"),
        ],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert result["report_status"] == "failed_validation"
    assert result["rewrite_attempted"] is False
    assert result["validation_attempts"] == 1
    assert result["validation_failures"][0]["reason"] == "unused_sources"
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_writing_node.py -v
```

Expected: failures because writing node still uses old URL-in-body validator.

- [ ] **Step 4: 更新 writing node 使用 validate_citations**

In `src/deepresearch/nodes/writing.py`:

- Import:

```python
from deepresearch.citations import CitationValidationResult, validate_citations
```

- Remove old URL/body validation helpers when no longer used.
- Add helper:

```python
def _failure_to_dict(result: CitationValidationResult) -> dict[str, object]:
    return result.to_dict()
```

- Add helper for failure report with one or more failures:

```python
def _validation_failure_report(question: str, failures: list[CitationValidationResult]) -> str:
    allowed_urls = failures[-1].allowed_urls if failures else []
    lines = [
        "# 研究报告生成失败",
        "",
        "本次报告未通过来源校验，因此没有发布研究报告正文。",
        "",
    ]
    if len(failures) == 1:
        lines.extend(["## 失败原因", "", failures[0].message, ""])
    else:
        lines.extend([
            "## 第一次失败原因",
            "",
            failures[0].message,
            "",
            "## 第二次失败原因",
            "",
            failures[1].message,
            "",
        ])
    lines.extend(["## 详细诊断", ""])
    for index, failure in enumerate(failures, start=1):
        data = failure.to_dict()
        lines.extend([
            f"### 第 {index} 次诊断",
            "",
            f"- reason: {data['reason']}",
            f"- body citations: {data['body_citations'] or 'None'}",
            f"- source citations: {data['source_citations'] or 'None'}",
            f"- undefined citations: {data['undefined_citations'] or 'None'}",
            f"- unused sources: {data['unused_sources'] or 'None'}",
            f"- invalid source URLs: {data['invalid_source_urls'] or 'None'}",
            f"- bare body URLs: {data['bare_body_urls'] or 'None'}",
            "",
        ])
    lines.extend([
        "## 可用来源 URL",
        "",
        *(f"- {url}" for url in allowed_urls),
        "",
        "## 你可以怎么做",
        "",
        "- 重新运行一次。",
        "- 使用更具体的问题。",
        "- 增加 `--results-per-query`。",
        "- 使用 `--verbose` 查看子问题和搜索结果摘要。",
    ])
    return "\n".join(lines) + "\n"
```

- In `write_report`, after LLM output:

```python
validation = validate_citations(report, allowed_urls)
if validation.passed:
    return {
        **state,
        "report_markdown": report,
        "report_status": "success",
        "rewrite_attempted": False,
        "validation_attempts": 1,
        "validation_failures": [],
    }

errors.append(f"Report citation validation failed: {validation.reason}: {validation.message}")
failure_report = _validation_failure_report(state["question"], [validation])
return {
    **state,
    "report_markdown": failure_report,
    "errors": errors,
    "report_status": "failed_validation",
    "rewrite_attempted": False,
    "validation_attempts": 1,
    "validation_failures": [_failure_to_dict(validation)],
}
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_citations.py tests/test_writing_node.py -v
```

Expected: pass. If old writing tests conflict with new citation contract, update them to use `[1]` citation format instead of inline URLs.

- [ ] **Step 6: 提交**

```bash
git add src/deepresearch/nodes/writing.py tests/test_writing_node.py
git commit -m "feat: validate numbered report citations"
```

---

### Task 5: 添加一次自动重写

**Files:**
- Modify: `src/deepresearch/nodes/writing.py`
- Modify: `tests/test_writing_node.py`

- [ ] **Step 1: 添加 retry 成功测试**

Append to `tests/test_writing_node.py`:

```python
def test_write_report_retries_once_after_validation_failure_and_succeeds():
    llm = FakeLLMClient([
        "# AI Search\n\nAI search is changing discovery without citation.\n\n## Sources\n\n[1] https://example.com",
        "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com",
    ])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert result["report_status"] == "success"
    assert result["rewrite_attempted"] is True
    assert result["validation_attempts"] == 2
    assert result["validation_failures"][0]["reason"] == "missing_body_citations"
    assert len(llm.prompts) == 2
    assert "未通过引用校验" in llm.prompts[1]
    assert "https://example.com" in llm.prompts[1]
```

- [ ] **Step 2: 添加 retry 后仍失败测试**

Append to `tests/test_writing_node.py`:

```python
def test_write_report_retries_once_then_saves_full_failure_report():
    llm = FakeLLMClient([
        "# AI Search\n\nNo citation.\n\n## Sources\n\n[1] https://example.com",
        "# AI Search\n\nStill no citation.\n\n## Sources\n\n[1] https://example.com",
    ])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert result["report_status"] == "failed_validation"
    assert result["rewrite_attempted"] is True
    assert result["validation_attempts"] == 2
    assert len(result["validation_failures"]) == 2
    assert "## 第一次失败原因" in result["report_markdown"]
    assert "## 第二次失败原因" in result["report_markdown"]
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_writing_node.py -v
```

Expected: retry tests fail because only one LLM call happens.

- [ ] **Step 4: 实现 retry prompt helper**

In `src/deepresearch/nodes/writing.py`, add:

```python
def _build_rewrite_prompt(question: str, draft: str, validation: CitationValidationResult, allowed_urls: set[str]) -> str:
    return f"""
你刚才生成的报告未通过引用校验。

失败原因：{validation.message}

请重新生成完整 Markdown 报告。
必须遵守：
- 正文关键论点使用 [1]、[2] 编号引用。
- 正文不允许出现裸 URL。
- URL 只能出现在 ## Sources 部分。
- Sources 中每个编号都必须在正文中使用。
- 只能使用 allowed URLs。

Original question:
{question}

Invalid draft:
{draft}

Allowed URLs:
{sorted(allowed_urls)}
""".strip()
```

- [ ] **Step 5: 实现一次 retry**

Replace the single-failure return from Task 4 with:

```python
first_validation = validate_citations(report, allowed_urls)
if first_validation.passed:
    return {... success metadata ...}

errors.append(f"Report citation validation failed on attempt 1: {first_validation.reason}: {first_validation.message}")
rewrite_prompt = _build_rewrite_prompt(state["question"], report, first_validation, allowed_urls)
rewritten_report = llm.complete(rewrite_prompt)
second_validation = validate_citations(rewritten_report, allowed_urls)

if second_validation.passed:
    return {
        **state,
        "report_markdown": rewritten_report,
        "errors": errors,
        "report_status": "success",
        "rewrite_attempted": True,
        "validation_attempts": 2,
        "validation_failures": [_failure_to_dict(first_validation)],
    }

errors.append(f"Report citation validation failed on attempt 2: {second_validation.reason}: {second_validation.message}")
failure_report = _validation_failure_report(state["question"], [first_validation, second_validation])
return {
    **state,
    "report_markdown": failure_report,
    "errors": errors,
    "report_status": "failed_validation",
    "rewrite_attempted": True,
    "validation_attempts": 2,
    "validation_failures": [_failure_to_dict(first_validation), _failure_to_dict(second_validation)],
}
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_writing_node.py -v
```

Expected: pass.

- [ ] **Step 7: 提交**

```bash
git add src/deepresearch/nodes/writing.py tests/test_writing_node.py
git commit -m "feat: retry report writing after citation failure"
```

---

### Task 6: 更新 verbose 输出 retry 元数据

**Files:**
- Modify: `src/deepresearch/verbose.py`
- Modify: `tests/test_verbose.py`

- [ ] **Step 1: 更新 verbose 测试**

Append to `tests/test_verbose.py`:

```python
def test_format_verbose_summary_includes_retry_success_metadata():
    state = {
        "report_status": "success",
        "rewrite_attempted": True,
        "validation_attempts": 2,
        "validation_failures": [
            {"reason": "missing_body_citations", "message": "正文没有使用编号引用。"},
        ],
    }

    summary = format_verbose_summary(state)

    assert "Report validation:" in summary
    assert "rewrite_attempted: True" in summary
    assert "validation_attempts: 2" in summary
    assert "final_status: success" in summary
    assert "attempt 1: missing_body_citations" in summary
```

If Task 3 already added a similar failed case test, keep both success and failed cases.

- [ ] **Step 2: Run tests**

Run:

```bash
uv run pytest tests/test_verbose.py -v
```

Expected: pass if Task 3 already implemented generic metadata output; otherwise fail and implement.

- [ ] **Step 3: Ensure formatter handles dict failures defensively**

In `src/deepresearch/verbose.py`, ensure the existing validation section does this:

```python
failures = state.get("validation_failures", [])
if failures:
    for index, failure in enumerate(failures, start=1):
        reason = failure.get("reason", "unknown") if isinstance(failure, dict) else "unknown"
        lines.append(f"- attempt {index}: {reason}")
else:
    lines.append("- failures: None")
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_verbose.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/verbose.py tests/test_verbose.py
git commit -m "feat: show citation retry metadata in verbose output"
```

---

### Task 7: 更新 integration、README 与离线全量测试

**Files:**
- Modify: `tests/test_integration_offline.py`
- Modify: `README.md`

- [ ] **Step 1: 更新 integration test 断言**

Modify `tests/test_integration_offline.py` fake writer response to numbered citation format:

```python
'# AI Search\n\nAI search uses generated answers.[1]\n\n## Sources\n\n[1] https://example.com/source'
```

Add assertions:

```python
assert result["report_status"] == "success"
assert result["validation_attempts"] == 1
assert result["rewrite_attempted"] is False
```

- [ ] **Step 2: 更新 README**

Add a section:

```markdown
## Citation format

Reports use strict numbered citations:

```markdown
AI search is changing discovery.[1]

## Sources

[1] https://example.com/source-a
```

The tool validates that every body citation is defined in `## Sources`, every source is cited in the body, and every URL comes from Tavily search results.

If the first generated report fails citation validation, the tool automatically rewrites the report once. If the rewrite also fails, it saves a `-failed.md` report with both validation failure reasons.
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
git commit -m "docs: document numbered citation retry flow"
```

---

### Task 8: 最终离线验证

**Files:**
- No code changes unless fixes are required.

- [ ] **Step 1: Run full offline tests**

Run:

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run safe CLI checks**

Run:

```bash
uv run deepresearch --help
```

Expected: help output includes `--verbose`, `--max-subquestions`, `--results-per-query`, `--output-dir`, `--model`.

Run:

```powershell
$env:DEEPSEEK_API_KEY=$null; $env:TAVILY_API_KEY=$null; $env:PYTHON_DOTENV_DISABLED='1'; uv run deepresearch "AI search"
```

Expected: non-zero exit and clear `DEEPSEEK_API_KEY is not set` message.

- [ ] **Step 3: Check git status**

Run:

```bash
git status --short
```

Expected: clean except the unrelated `docs/superpowers/reports/2026-06-11-v0.1.1-acceptance-report-zh.md` if it remains untracked.

- [ ] **Step 4: Do not run online smoke tests in this task**

Online acceptance is separate and requires explicit user authorization because it calls external APIs.

---

### Task 9: 在线 3 题验收与报告

**Files:**
- Create: `docs/superpowers/reports/2026-06-11-v0.1.2-online-acceptance-report.md`

- [ ] **Step 1: Run online smoke tests only with explicit authorization**

Run these commands one by one:

```bash
uv run deepresearch "AI 搜索引擎的发展趋势" --verbose
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --verbose
uv run deepresearch "新能源汽车固态电池商业化进展" --verbose
```

- [ ] **Step 2: Record each result**

For each question, record:

```text
question:
result: success | failed_validation
output_path:
rewrite_attempted:
validation_attempts:
validation_failures:
review_score:
review_passed:
```

- [ ] **Step 3: Determine pass/fail**

Pass if at least 2 of 3 are success reports.

- [ ] **Step 4: Write acceptance report**

Create `docs/superpowers/reports/2026-06-11-v0.1.2-online-acceptance-report.md` with:

```markdown
# Deep Research Agent v0.1.2 Online Acceptance Report

## Summary

| Question | Result | Output | Rewrite | Attempts | Review |
|---|---|---|---|---:|---|
| ... | ... | ... | ... | ... | ... |

## Verdict

v0.1.2 online acceptance: Passed/Failed

## Details

### 1. AI 搜索引擎的发展趋势
...
```

- [ ] **Step 5: Commit report**

```bash
git add docs/superpowers/reports/2026-06-11-v0.1.2-online-acceptance-report.md
git commit -m "docs: add v0.1.2 online acceptance report"
```

---

## Self-Review

Spec coverage:

- Strict numbered citation contract: Tasks 1, 2, 4.
- Citation validator full rule coverage: Task 1.
- Writer prompt update: Task 2.
- One retry inside write_report: Task 5.
- Review final report only: graph remains unchanged; Task 5 returns final report before review node.
- Failure report with both attempts: Task 5.
- State metadata: Task 3.
- Verbose retry metadata: Tasks 3 and 6.
- Online 3-question acceptance: Task 9.
- No default external API calls: online task is separate and gated.

Placeholder scan:

- No implementation step says to fill in unspecified behavior.
- All new functions/classes have concrete code snippets.
- Online smoke test commands are explicit.

Type consistency:

- `CitationValidationResult.to_dict()` returns serializable dicts used by `ResearchState.validation_failures`.
- `report_status` remains `success | failed_validation`.
- `rewrite_attempted`, `validation_attempts`, and `validation_failures` are used consistently by writing node and verbose formatter.
