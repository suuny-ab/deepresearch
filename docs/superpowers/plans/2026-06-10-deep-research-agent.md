# Deep Research Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python + uv LangGraph CLI Deep Research Agent that uses Tavily search and DeepSeek v4 pro through an OpenAI-compatible API to generate, review, print, and save source-backed Markdown research reports.

**Architecture:** Implement a fixed linear LangGraph workflow with focused nodes: plan, search, synthesize, write, review, save. Keep external services behind adapters (`LLMClient`, `TavilySearchClient`) and make node logic testable with fake clients.

**Tech Stack:** Python 3.11+, uv, LangGraph, Pydantic, Typer, Rich, OpenAI Python SDK for DeepSeek-compatible calls, tavily-python, python-dotenv, pytest.

---

## File Structure

Create these files:

```text
pyproject.toml
README.md
.env.example
src/deepresearch/__init__.py
src/deepresearch/cli.py
src/deepresearch/config.py
src/deepresearch/errors.py
src/deepresearch/graph.py
src/deepresearch/state.py
src/deepresearch/clients/__init__.py
src/deepresearch/clients/llm.py
src/deepresearch/clients/tavily.py
src/deepresearch/nodes/__init__.py
src/deepresearch/nodes/planning.py
src/deepresearch/nodes/searching.py
src/deepresearch/nodes/synthesizing.py
src/deepresearch/nodes/writing.py
src/deepresearch/nodes/reviewing.py
src/deepresearch/nodes/saving.py
src/deepresearch/prompts/__init__.py
src/deepresearch/prompts/planning.py
src/deepresearch/prompts/synthesizing.py
src/deepresearch/prompts/writing.py
src/deepresearch/prompts/reviewing.py
src/deepresearch/utils/__init__.py
src/deepresearch/utils/json.py
src/deepresearch/utils/filenames.py
src/deepresearch/utils/report_writer.py
tests/conftest.py
tests/test_state.py
tests/test_json_parsing.py
tests/test_filenames.py
tests/test_report_writer.py
tests/test_planning_node.py
tests/test_searching_node.py
tests/test_synthesizing_node.py
tests/test_writing_node.py
tests/test_reviewing_node.py
tests/test_graph_structure.py
tests/test_integration_offline.py
reports/.gitkeep
```

Responsibilities:

- `state.py`: Pydantic data models and `ResearchState`.
- `config.py`: environment + CLI configuration object.
- `errors.py`: project exception types.
- `clients/llm.py`: DeepSeek OpenAI-compatible wrapper and fake-friendly protocol.
- `clients/tavily.py`: Tavily wrapper and search result normalization.
- `nodes/*`: pure workflow node functions plus small dependency-injected factories.
- `prompts/*`: prompt builders only; no API calls.
- `utils/json.py`: robust JSON extraction and Pydantic validation helpers.
- `utils/filenames.py`: safe timestamped filenames.
- `utils/report_writer.py`: write Markdown and append quality review.
- `graph.py`: build and compile the LangGraph graph.
- `cli.py`: Typer entrypoint, progress output, config loading, terminal Markdown rendering.

---

### Task 1: Project scaffold and package metadata

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/deepresearch/__init__.py`
- Create: package `__init__.py` files under `clients`, `nodes`, `prompts`, `utils`
- Create: `reports/.gitkeep`

- [ ] **Step 1: Write the project metadata**

Create `pyproject.toml`:

```toml
[project]
name = "deepresearch"
version = "0.1.0"
description = "LangGraph CLI Deep Research Agent using DeepSeek and Tavily"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2.0",
    "openai>=1.0.0",
    "pydantic>=2.7.0",
    "python-dotenv>=1.0.1",
    "rich>=13.7.0",
    "tavily-python>=0.5.0",
    "typer>=0.12.0",
]

[project.scripts]
deepresearch = "deepresearch.cli:app"

[dependency-groups]
dev = [
    "pytest>=8.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Write environment example**

Create `.env.example`:

```env
# DeepSeek OpenAI-compatible API
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro

# Tavily Search API
TAVILY_API_KEY=your_tavily_api_key

# Runtime defaults
DEEPRESEARCH_MAX_SUBQUESTIONS=5
DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY=5
DEEPRESEARCH_OUTPUT_DIR=reports
```

- [ ] **Step 3: Write initial README**

Create `README.md`:

```markdown
# Deep Research Agent

A Python + LangGraph command-line Deep Research Agent.

## What it does

Given a research question, it runs a fixed workflow:

1. Plan subquestions
2. Search with Tavily
3. Synthesize notes
4. Write a Markdown report
5. Review report quality
6. Save and print the report

## Setup

```bash
uv sync
cp .env.example .env
```

Fill in:

- `DEEPSEEK_API_KEY`
- `TAVILY_API_KEY`

## Run

```bash
uv run deepresearch "AI 搜索引擎的发展趋势"
```

## Test

```bash
uv run pytest
```

## Output

Reports are saved under `reports/` and printed in the terminal.
```

- [ ] **Step 4: Create package marker files**

Create these files as empty files:

```text
src/deepresearch/__init__.py
src/deepresearch/clients/__init__.py
src/deepresearch/nodes/__init__.py
src/deepresearch/prompts/__init__.py
src/deepresearch/utils/__init__.py
reports/.gitkeep
```

- [ ] **Step 5: Install dependencies**

Run:

```bash
uv sync
```

Expected: command exits with status 0 and creates `uv.lock`.

- [ ] **Step 6: Commit scaffold if this is a git repository**

Run:

```bash
git status
```

If this prints `fatal: not a git repository`, do not commit. If it is a git repository, run:

```bash
git add pyproject.toml uv.lock README.md .env.example src reports
git commit -m "chore: scaffold deepresearch project"
```

---

### Task 2: State models and JSON parsing utilities

**Files:**
- Create: `src/deepresearch/state.py`
- Create: `src/deepresearch/utils/json.py`
- Test: `tests/test_state.py`
- Test: `tests/test_json_parsing.py`

- [ ] **Step 1: Write failing state model tests**

Create `tests/test_state.py`:

```python
import pytest
from pydantic import ValidationError

from deepresearch.state import ResearchNote, ReviewResult, SearchResult, SubQuestion


def test_subquestion_requires_core_fields():
    item = SubQuestion(
        id="q1",
        question="What changed in AI search?",
        search_query="AI search trends 2026",
        rationale="Establish context",
    )

    assert item.id == "q1"
    assert item.search_query == "AI search trends 2026"


def test_search_result_keeps_source_url():
    result = SearchResult(
        subquestion_id="q1",
        title="Report",
        url="https://example.com/report",
        content="Useful summary",
        score=0.8,
    )

    assert result.url == "https://example.com/report"
    assert result.score == 0.8


def test_research_note_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        ResearchNote(
            subquestion_id="q1",
            key_findings=["Finding"],
            source_urls=["https://example.com"],
            confidence="certain",
        )


def test_review_result_score_range():
    review = ReviewResult(passed=True, score=86, issues=[], suggestions=[])

    assert review.score == 86

    with pytest.raises(ValidationError):
        ReviewResult(passed=False, score=101, issues=[], suggestions=[])
```

- [ ] **Step 2: Write failing JSON parsing tests**

Create `tests/test_json_parsing.py`:

```python
import pytest
from pydantic import BaseModel

from deepresearch.utils.json import JSONParseError, parse_json_object


class Item(BaseModel):
    name: str


def test_parse_raw_json_object():
    item = parse_json_object('{"name": "alpha"}', Item)

    assert item.name == "alpha"


def test_parse_fenced_json_object():
    item = parse_json_object('Here is JSON:\n```json\n{"name": "beta"}\n```', Item)

    assert item.name == "beta"


def test_invalid_json_raises_parse_error():
    with pytest.raises(JSONParseError):
        parse_json_object("not json", Item)


def test_missing_required_field_raises_parse_error():
    with pytest.raises(JSONParseError):
        parse_json_object("{}", Item)
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_state.py tests/test_json_parsing.py -v
```

Expected: FAIL because `deepresearch.state` and `deepresearch.utils.json` do not exist yet.

- [ ] **Step 4: Implement state models**

Create `src/deepresearch/state.py`:

```python
from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class SubQuestion(BaseModel):
    id: str
    question: str
    search_query: str
    rationale: str


class SearchResult(BaseModel):
    subquestion_id: str
    title: str
    url: str
    content: str
    score: float | None = None
    published_date: str | None = None


class ResearchNote(BaseModel):
    subquestion_id: str
    key_findings: list[str]
    source_urls: list[str]
    confidence: Literal["low", "medium", "high"]


class ReviewResult(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[str]
    suggestions: list[str]


class ResearchState(TypedDict, total=False):
    question: str
    subquestions: list[SubQuestion]
    search_results: list[SearchResult]
    notes: list[ResearchNote]
    report_markdown: str
    review: ReviewResult
    output_path: str
    errors: list[str]
```

- [ ] **Step 5: Implement JSON parser utility**

Create `src/deepresearch/utils/json.py`:

```python
import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class JSONParseError(ValueError):
    pass


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped

    match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    raise JSONParseError("No JSON object or fenced JSON block found")


def parse_json_object(text: str, model: type[T]) -> T:
    try:
        raw = _extract_json_text(text)
        data = json.loads(raw)
        return model.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise JSONParseError(str(exc)) from exc
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_state.py tests/test_json_parsing.py -v
```

Expected: PASS for all tests in these files.

- [ ] **Step 7: Commit if this is a git repository**

Run:

```bash
git status
```

If this is a git repository:

```bash
git add src/deepresearch/state.py src/deepresearch/utils/json.py tests/test_state.py tests/test_json_parsing.py
git commit -m "feat: add research state models"
```

---

### Task 3: Filename and report writing utilities

**Files:**
- Create: `src/deepresearch/utils/filenames.py`
- Create: `src/deepresearch/utils/report_writer.py`
- Test: `tests/test_filenames.py`
- Test: `tests/test_report_writer.py`

- [ ] **Step 1: Write failing filename tests**

Create `tests/test_filenames.py`:

```python
from datetime import datetime

from deepresearch.utils.filenames import make_report_filename, slugify_question


def test_slugify_ascii_question():
    assert slugify_question("AI Search Trends 2026") == "ai-search-trends-2026"


def test_slugify_removes_punctuation():
    assert slugify_question("LangGraph vs. CrewAI: which one?") == "langgraph-vs-crewai-which-one"


def test_slugify_non_ascii_falls_back_to_report():
    assert slugify_question("分析 2026 年 AI 搜索趋势") == "2026-ai"


def test_slugify_empty_falls_back_to_report():
    assert slugify_question("!!!") == "report"


def test_make_report_filename_contains_timestamp_and_slug():
    now = datetime(2026, 6, 10, 15, 30, 0)

    filename = make_report_filename("AI Search Trends", now=now)

    assert filename == "2026-06-10-153000-ai-search-trends.md"
```

- [ ] **Step 2: Write failing report writer tests**

Create `tests/test_report_writer.py`:

```python
from datetime import datetime

from deepresearch.state import ReviewResult
from deepresearch.utils.report_writer import append_quality_review, save_report


def test_append_quality_review():
    report = "# Report\n\nBody"
    review = ReviewResult(
        passed=False,
        score=72,
        issues=["Missing source near one claim"],
        suggestions=["Add a stronger source"],
    )

    result = append_quality_review(report, review)

    assert "## Quality Review" in result
    assert "Score: 72/100" in result
    assert "Passed: False" in result
    assert "Missing source near one claim" in result
    assert "Add a stronger source" in result


def test_save_report_writes_utf8_markdown(tmp_path):
    review = ReviewResult(passed=True, score=90, issues=[], suggestions=[])
    now = datetime(2026, 6, 10, 15, 30, 0)

    output_path = save_report(
        question="AI Search Trends",
        report_markdown="# 标题\n\n内容",
        review=review,
        output_dir=tmp_path,
        now=now,
    )

    assert output_path.exists()
    assert output_path.name == "2026-06-10-153000-ai-search-trends.md"
    assert "# 标题" in output_path.read_text(encoding="utf-8")
    assert "## Quality Review" in output_path.read_text(encoding="utf-8")
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_filenames.py tests/test_report_writer.py -v
```

Expected: FAIL because filename and report writer modules do not exist yet.

- [ ] **Step 4: Implement filename utility**

Create `src/deepresearch/utils/filenames.py`:

```python
import re
from datetime import datetime


def slugify_question(question: str, max_length: int = 60) -> str:
    lowered = question.lower()
    asciiish = re.sub(r"[^a-z0-9]+", "-", lowered)
    slug = re.sub(r"-+", "-", asciiish).strip("-")
    if not slug:
        return "report"
    return slug[:max_length].strip("-") or "report"


def make_report_filename(question: str, now: datetime | None = None) -> str:
    current = now or datetime.now()
    timestamp = current.strftime("%Y-%m-%d-%H%M%S")
    slug = slugify_question(question)
    return f"{timestamp}-{slug}.md"
```

- [ ] **Step 5: Implement report writer**

Create `src/deepresearch/utils/report_writer.py`:

```python
from datetime import datetime
from pathlib import Path

from deepresearch.state import ReviewResult
from deepresearch.utils.filenames import make_report_filename


def _format_bullets(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def append_quality_review(report_markdown: str, review: ReviewResult) -> str:
    return (
        report_markdown.rstrip()
        + "\n\n---\n\n"
        + "## Quality Review\n\n"
        + f"Score: {review.score}/100\n\n"
        + f"Passed: {review.passed}\n\n"
        + "### Issues\n\n"
        + _format_bullets(review.issues)
        + "\n\n"
        + "### Suggestions\n\n"
        + _format_bullets(review.suggestions)
        + "\n"
    )


def save_report(
    question: str,
    report_markdown: str,
    review: ReviewResult,
    output_dir: str | Path,
    now: datetime | None = None,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / make_report_filename(question, now=now)
    path.write_text(append_quality_review(report_markdown, review), encoding="utf-8")
    return path
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_filenames.py tests/test_report_writer.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit if this is a git repository**

Run:

```bash
git status
```

If this is a git repository:

```bash
git add src/deepresearch/utils/filenames.py src/deepresearch/utils/report_writer.py tests/test_filenames.py tests/test_report_writer.py
git commit -m "feat: add report file writer"
```

---

### Task 4: Configuration, errors, and external clients

**Files:**
- Create: `src/deepresearch/config.py`
- Create: `src/deepresearch/errors.py`
- Create: `src/deepresearch/clients/llm.py`
- Create: `src/deepresearch/clients/tavily.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py`:

```python
import pytest

from deepresearch.config import AppConfig, ConfigError


def test_config_reads_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

    config = AppConfig.from_env()

    assert config.deepseek_api_key == "deepseek-key"
    assert config.tavily_api_key == "tavily-key"
    assert config.deepseek_model == "deepseek-v4-pro"
    assert config.max_subquestions == 5


def test_config_validates_required_keys(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    config = AppConfig.from_env()

    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        config.validate_required()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL because `deepresearch.config` does not exist yet.

- [ ] **Step 3: Implement project errors**

Create `src/deepresearch/errors.py`:

```python
class DeepResearchError(Exception):
    pass


class ConfigError(DeepResearchError):
    pass


class LLMError(DeepResearchError):
    pass


class SearchError(DeepResearchError):
    pass


class ReportWriteError(DeepResearchError):
    pass
```

- [ ] **Step 4: Implement config**

Create `src/deepresearch/config.py`:

```python
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from deepresearch.errors import ConfigError


@dataclass(frozen=True)
class AppConfig:
    deepseek_api_key: str | None
    tavily_api_key: str | None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-pro"
    max_subquestions: int = 5
    results_per_query: int = 5
    output_dir: str = "reports"
    verbose: bool = False

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        return cls(
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            tavily_api_key=os.getenv("TAVILY_API_KEY"),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            max_subquestions=int(os.getenv("DEEPRESEARCH_MAX_SUBQUESTIONS", "5")),
            results_per_query=int(os.getenv("DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY", "5")),
            output_dir=os.getenv("DEEPRESEARCH_OUTPUT_DIR", "reports"),
        )

    def with_overrides(
        self,
        *,
        max_subquestions: int | None = None,
        results_per_query: int | None = None,
        output_dir: str | None = None,
        model: str | None = None,
        verbose: bool | None = None,
    ) -> "AppConfig":
        return AppConfig(
            deepseek_api_key=self.deepseek_api_key,
            tavily_api_key=self.tavily_api_key,
            deepseek_base_url=self.deepseek_base_url,
            deepseek_model=model or self.deepseek_model,
            max_subquestions=max_subquestions or self.max_subquestions,
            results_per_query=results_per_query or self.results_per_query,
            output_dir=output_dir or self.output_dir,
            verbose=self.verbose if verbose is None else verbose,
        )

    def validate_required(self) -> None:
        if not self.deepseek_api_key:
            raise ConfigError("DEEPSEEK_API_KEY is not set. Copy .env.example to .env and fill it in.")
        if not self.tavily_api_key:
            raise ConfigError("TAVILY_API_KEY is not set. Copy .env.example to .env and fill it in.")
```

- [ ] **Step 5: Implement LLM client**

Create `src/deepresearch/clients/llm.py`:

```python
from typing import Protocol

from openai import OpenAI, OpenAIError

from deepresearch.errors import LLMError


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        ...


class DeepSeekLLMClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            if not content:
                raise LLMError("LLM returned empty content")
            return content
        except (OpenAIError, IndexError, AttributeError) as exc:
            raise LLMError(str(exc)) from exc
```

- [ ] **Step 6: Implement Tavily client**

Create `src/deepresearch/clients/tavily.py`:

```python
from typing import Protocol

from tavily import TavilyClient

from deepresearch.errors import SearchError
from deepresearch.state import SearchResult


class SearchClient(Protocol):
    def search(self, query: str, *, subquestion_id: str, max_results: int) -> list[SearchResult]:
        ...


class TavilySearchClient:
    def __init__(self, api_key: str):
        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, *, subquestion_id: str, max_results: int) -> list[SearchResult]:
        try:
            response = self._client.search(query=query, max_results=max_results)
            items = response.get("results", [])
            return [
                SearchResult(
                    subquestion_id=subquestion_id,
                    title=item.get("title") or "Untitled",
                    url=item.get("url") or "",
                    content=item.get("content") or "",
                    score=item.get("score"),
                    published_date=item.get("published_date"),
                )
                for item in items
                if item.get("url")
            ]
        except Exception as exc:
            raise SearchError(str(exc)) from exc
```

- [ ] **Step 7: Run config tests**

Run:

```bash
uv run pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit if this is a git repository**

Run:

```bash
git status
```

If this is a git repository:

```bash
git add src/deepresearch/config.py src/deepresearch/errors.py src/deepresearch/clients tests/test_config.py
git commit -m "feat: add config and API clients"
```

---

### Task 5: Prompt builders and LLM-driven nodes

**Files:**
- Create: `src/deepresearch/prompts/planning.py`
- Create: `src/deepresearch/prompts/synthesizing.py`
- Create: `src/deepresearch/prompts/writing.py`
- Create: `src/deepresearch/prompts/reviewing.py`
- Create: `src/deepresearch/nodes/planning.py`
- Create: `src/deepresearch/nodes/synthesizing.py`
- Create: `src/deepresearch/nodes/writing.py`
- Create: `src/deepresearch/nodes/reviewing.py`
- Test: `tests/conftest.py`
- Test: `tests/test_planning_node.py`
- Test: `tests/test_synthesizing_node.py`
- Test: `tests/test_writing_node.py`
- Test: `tests/test_reviewing_node.py`

- [ ] **Step 1: Write shared fake LLM**

Create `tests/conftest.py`:

```python
class FakeLLMClient:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("No fake LLM response configured")
        return self.responses.pop(0)
```

- [ ] **Step 2: Write failing node tests**

Create `tests/test_planning_node.py`:

```python
from deepresearch.nodes.planning import make_plan_research_node


def test_plan_research_parses_subquestions():
    llm = FakeLLMClient([
        '{"subquestions":[{"id":"q1","question":"What is AI search?","search_query":"AI search definition","rationale":"Background"}]}'
    ])
    node = make_plan_research_node(llm, max_subquestions=5)

    result = node({"question": "AI search trends", "errors": []})

    assert result["subquestions"][0].id == "q1"
    assert result["errors"] == []


def test_plan_research_fallback_on_bad_json():
    llm = FakeLLMClient(["not json"])
    node = make_plan_research_node(llm, max_subquestions=5)

    result = node({"question": "AI search trends", "errors": []})

    assert result["subquestions"][0].question == "AI search trends"
    assert result["subquestions"][0].search_query == "AI search trends"
    assert result["errors"]
```

At the top of the file add:

```python
from tests.conftest import FakeLLMClient
```

Create `tests/test_synthesizing_node.py`:

```python
from tests.conftest import FakeLLMClient

from deepresearch.nodes.synthesizing import make_synthesize_notes_node
from deepresearch.state import SearchResult, SubQuestion


def test_synthesize_notes_parses_notes():
    llm = FakeLLMClient([
        '{"notes":[{"subquestion_id":"q1","key_findings":["AI search summarizes results"],"source_urls":["https://example.com"],"confidence":"high"}]}'
    ])
    node = make_synthesize_notes_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="AI search summarizes results")],
        "errors": [],
    })

    assert result["notes"][0].confidence == "high"
```

Create `tests/test_writing_node.py`:

```python
from tests.conftest import FakeLLMClient

from deepresearch.nodes.writing import make_write_report_node
from deepresearch.state import ResearchNote, SearchResult, SubQuestion


def test_write_report_uses_llm_markdown():
    llm = FakeLLMClient(["# AI Search\n\n## Sources\n\n- https://example.com"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert result["report_markdown"].startswith("# AI Search")
```

Create `tests/test_reviewing_node.py`:

```python
from tests.conftest import FakeLLMClient

from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.state import SearchResult


def test_review_report_parses_review():
    llm = FakeLLMClient([
        '{"passed":true,"score":88,"issues":[],"suggestions":["Add more market data"]}'
    ])
    node = make_review_report_node(llm)

    result = node({
        "question": "AI search",
        "report_markdown": "# Report\n\nSource: https://example.com",
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "errors": [],
    })

    assert result["review"].passed is True
    assert result["review"].score == 88
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_planning_node.py tests/test_synthesizing_node.py tests/test_writing_node.py tests/test_reviewing_node.py -v
```

Expected: FAIL because prompt and node modules do not exist.

- [ ] **Step 4: Implement prompt builders**

Create `src/deepresearch/prompts/planning.py`:

```python
def build_planning_prompt(question: str, max_subquestions: int) -> str:
    return f"""
You are a research planner. Decompose the user's research question into 3 to {max_subquestions} non-overlapping subquestions.
For each subquestion, provide one web search query suitable for Tavily.
Return only JSON in this exact shape:
{{"subquestions":[{{"id":"q1","question":"...","search_query":"...","rationale":"..."}}]}}

Research question:
{question}
""".strip()
```

Create `src/deepresearch/prompts/synthesizing.py`:

```python
from deepresearch.state import SearchResult, SubQuestion


def build_synthesizing_prompt(question: str, subquestions: list[SubQuestion], results: list[SearchResult]) -> str:
    return f"""
You are a careful research analyst. Use only the supplied search results.
Extract key findings for each subquestion. Every finding must be traceable to one of the supplied URLs.
Return only JSON in this exact shape:
{{"notes":[{{"subquestion_id":"q1","key_findings":["..."],"source_urls":["https://..."],"confidence":"low|medium|high"}}]}}

Original question:
{question}

Subquestions:
{[item.model_dump() for item in subquestions]}

Search results:
{[item.model_dump() for item in results]}
""".strip()
```

Create `src/deepresearch/prompts/writing.py`:

```python
from deepresearch.state import ResearchNote, SearchResult, SubQuestion


def build_writing_prompt(
    question: str,
    subquestions: list[SubQuestion],
    notes: list[ResearchNote],
    results: list[SearchResult],
) -> str:
    allowed_urls = sorted({item.url for item in results})
    return f"""
Write a structured Markdown deep research report in Chinese unless the user's question is in another language.
Use only the supplied notes and source URLs. Do not invent URLs.
Every key conclusion should include a source URL or footnote.

Required sections:
# <title>
## 摘要
## 关键结论
## 背景与问题拆解
## 深度分析
## 风险、不确定性与不同观点
## 结论
## Sources

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

Create `src/deepresearch/prompts/reviewing.py`:

```python
from deepresearch.state import SearchResult


def build_reviewing_prompt(question: str, report_markdown: str, results: list[SearchResult]) -> str:
    urls = sorted({item.url for item in results})
    return f"""
Review this Markdown research report for relevance, completeness, source support, structure, and unsupported claims.
Return only JSON in this exact shape:
{{"passed":true,"score":88,"issues":["..."],"suggestions":["..."]}}
Score must be an integer from 0 to 100.

Original question:
{question}

Allowed source URLs:
{urls}

Report:
{report_markdown}
""".strip()
```

- [ ] **Step 5: Implement planning node**

Create `src/deepresearch/nodes/planning.py`:

```python
from pydantic import BaseModel

from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.planning import build_planning_prompt
from deepresearch.state import ResearchState, SubQuestion
from deepresearch.utils.json import JSONParseError, parse_json_object


class PlanningResponse(BaseModel):
    subquestions: list[SubQuestion]


def make_plan_research_node(llm: LLMClient, max_subquestions: int):
    def plan_research(state: ResearchState) -> ResearchState:
        question = state["question"]
        errors = list(state.get("errors", []))
        prompt = build_planning_prompt(question, max_subquestions)
        text = llm.complete(prompt)
        try:
            parsed = parse_json_object(text, PlanningResponse)
            subquestions = parsed.subquestions[:max_subquestions]
        except JSONParseError as exc:
            errors.append(f"Planning JSON parse failed: {exc}")
            subquestions = [
                SubQuestion(id="q1", question=question, search_query=question, rationale="Fallback from original question")
            ]
        return {**state, "subquestions": subquestions, "errors": errors}

    return plan_research
```

- [ ] **Step 6: Implement synthesizing node**

Create `src/deepresearch/nodes/synthesizing.py`:

```python
from pydantic import BaseModel

from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.synthesizing import build_synthesizing_prompt
from deepresearch.state import ResearchNote, ResearchState
from deepresearch.utils.json import JSONParseError, parse_json_object


class NotesResponse(BaseModel):
    notes: list[ResearchNote]


def _fallback_notes(state: ResearchState) -> list[ResearchNote]:
    notes: list[ResearchNote] = []
    for subquestion in state.get("subquestions", []):
        matching = [r for r in state.get("search_results", []) if r.subquestion_id == subquestion.id]
        findings = [f"{r.title}: {r.content}" for r in matching[:3]] or ["No reliable search results were available."]
        urls = [r.url for r in matching]
        notes.append(ResearchNote(subquestion_id=subquestion.id, key_findings=findings, source_urls=urls, confidence="low"))
    return notes


def make_synthesize_notes_node(llm: LLMClient):
    def synthesize_notes(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        prompt = build_synthesizing_prompt(state["question"], state.get("subquestions", []), state.get("search_results", []))
        text = llm.complete(prompt)
        try:
            notes = parse_json_object(text, NotesResponse).notes
        except JSONParseError as exc:
            errors.append(f"Notes JSON parse failed: {exc}")
            notes = _fallback_notes(state)
        return {**state, "notes": notes, "errors": errors}

    return synthesize_notes
```

- [ ] **Step 7: Implement writing node**

Create `src/deepresearch/nodes/writing.py`:

```python
from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.writing import build_writing_prompt
from deepresearch.state import ResearchState


def make_write_report_node(llm: LLMClient):
    def write_report(state: ResearchState) -> ResearchState:
        results = state.get("search_results", [])
        notes = state.get("notes", [])
        if not results or not notes:
            report = (
                f"# Research could not be completed\n\n"
                f"The question was: {state['question']}\n\n"
                "Insufficient search results or notes were available, so no source-backed report was generated.\n"
            )
            return {**state, "report_markdown": report}

        prompt = build_writing_prompt(state["question"], state.get("subquestions", []), notes, results)
        report = llm.complete(prompt)
        return {**state, "report_markdown": report}

    return write_report
```

- [ ] **Step 8: Implement reviewing node**

Create `src/deepresearch/nodes/reviewing.py`:

```python
from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.reviewing import build_reviewing_prompt
from deepresearch.state import ResearchState, ReviewResult
from deepresearch.utils.json import JSONParseError, parse_json_object


def make_review_report_node(llm: LLMClient):
    def review_report(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        prompt = build_reviewing_prompt(state["question"], state.get("report_markdown", ""), state.get("search_results", []))
        text = llm.complete(prompt)
        try:
            review = parse_json_object(text, ReviewResult)
        except JSONParseError as exc:
            errors.append(f"Review JSON parse failed: {exc}")
            review = ReviewResult(passed=False, score=0, issues=["Review parsing failed"], suggestions=["Inspect the report manually"])
        return {**state, "review": review, "errors": errors}

    return review_report
```

- [ ] **Step 9: Run node tests**

Run:

```bash
uv run pytest tests/test_planning_node.py tests/test_synthesizing_node.py tests/test_writing_node.py tests/test_reviewing_node.py -v
```

Expected: PASS.

- [ ] **Step 10: Commit if this is a git repository**

Run:

```bash
git status
```

If this is a git repository:

```bash
git add src/deepresearch/prompts src/deepresearch/nodes tests/conftest.py tests/test_planning_node.py tests/test_synthesizing_node.py tests/test_writing_node.py tests/test_reviewing_node.py
git commit -m "feat: add LLM workflow nodes"
```

---

### Task 6: Search and saving nodes

**Files:**
- Create: `src/deepresearch/nodes/searching.py`
- Create: `src/deepresearch/nodes/saving.py`
- Test: `tests/test_searching_node.py`

- [ ] **Step 1: Write failing search node tests**

Create `tests/test_searching_node.py`:

```python
import pytest

from deepresearch.errors import SearchError
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.state import SearchResult, SubQuestion


class FakeSearchClient:
    def __init__(self, failures: set[str] | None = None):
        self.failures = failures or set()
        self.queries: list[str] = []

    def search(self, query: str, *, subquestion_id: str, max_results: int):
        self.queries.append(query)
        if query in self.failures:
            raise SearchError("search failed")
        return [SearchResult(subquestion_id=subquestion_id, title="Source", url=f"https://example.com/{subquestion_id}", content="Content")]


def test_search_web_collects_results():
    client = FakeSearchClient()
    node = make_search_web_node(client, results_per_query=5)

    result = node({
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "errors": [],
    })

    assert result["search_results"][0].url == "https://example.com/q1"
    assert client.queries == ["AI search"]


def test_search_web_continues_after_one_failure():
    client = FakeSearchClient(failures={"bad query"})
    node = make_search_web_node(client, results_per_query=5)

    result = node({
        "subquestions": [
            SubQuestion(id="q1", question="Bad", search_query="bad query", rationale="Failure"),
            SubQuestion(id="q2", question="Good", search_query="good query", rationale="Success"),
        ],
        "errors": [],
    })

    assert len(result["search_results"]) == 1
    assert result["errors"]


def test_search_web_raises_when_all_searches_fail():
    client = FakeSearchClient(failures={"bad query"})
    node = make_search_web_node(client, results_per_query=5)

    with pytest.raises(SearchError, match="All searches failed"):
        node({
            "subquestions": [SubQuestion(id="q1", question="Bad", search_query="bad query", rationale="Failure")],
            "errors": [],
        })
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_searching_node.py -v
```

Expected: FAIL because `nodes.searching` does not exist yet.

- [ ] **Step 3: Implement search node**

Create `src/deepresearch/nodes/searching.py`:

```python
from deepresearch.clients.tavily import SearchClient
from deepresearch.errors import SearchError
from deepresearch.state import ResearchState, SearchResult


def make_search_web_node(search_client: SearchClient, results_per_query: int):
    def search_web(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        results: list[SearchResult] = []
        for subquestion in state.get("subquestions", []):
            try:
                results.extend(
                    search_client.search(
                        subquestion.search_query,
                        subquestion_id=subquestion.id,
                        max_results=results_per_query,
                    )
                )
            except SearchError as exc:
                errors.append(f"Search failed for {subquestion.id}: {exc}")

        if not results:
            raise SearchError("All searches failed or returned no usable results")
        return {**state, "search_results": results, "errors": errors}

    return search_web
```

- [ ] **Step 4: Implement saving node**

Create `src/deepresearch/nodes/saving.py`:

```python
from pathlib import Path

from deepresearch.state import ResearchState
from deepresearch.utils.report_writer import save_report


def make_save_report_node(output_dir: str | Path):
    def save_report_node(state: ResearchState) -> ResearchState:
        path = save_report(
            question=state["question"],
            report_markdown=state.get("report_markdown", ""),
            review=state["review"],
            output_dir=output_dir,
        )
        return {**state, "output_path": str(path)}

    return save_report_node
```

- [ ] **Step 5: Run search tests and report writer tests**

Run:

```bash
uv run pytest tests/test_searching_node.py tests/test_report_writer.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit if this is a git repository**

Run:

```bash
git status
```

If this is a git repository:

```bash
git add src/deepresearch/nodes/searching.py src/deepresearch/nodes/saving.py tests/test_searching_node.py
git commit -m "feat: add search and save nodes"
```

---

### Task 7: LangGraph graph assembly and offline integration test

**Files:**
- Create: `src/deepresearch/graph.py`
- Test: `tests/test_graph_structure.py`
- Test: `tests/test_integration_offline.py`

- [ ] **Step 1: Write failing graph structure test**

Create `tests/test_graph_structure.py`:

```python
from deepresearch.graph import NODE_SEQUENCE, build_research_graph


def test_node_sequence_is_fixed_mvp_pipeline():
    assert NODE_SEQUENCE == [
        "plan_research",
        "search_web",
        "synthesize_notes",
        "write_report",
        "review_report",
        "save_report",
    ]


def test_graph_compiles_with_fake_nodes(tmp_path):
    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        synthesize_notes=lambda state: {**state, "notes": []},
        write_report=lambda state: {**state, "report_markdown": "# Report"},
        review_report=lambda state: {**state, "review": None},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
    )

    assert graph is not None
```

- [ ] **Step 2: Write failing offline integration test**

Create `tests/test_integration_offline.py`:

```python
from tests.conftest import FakeLLMClient

from deepresearch.graph import create_research_app
from deepresearch.nodes.planning import make_plan_research_node
from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.nodes.saving import make_save_report_node
from deepresearch.nodes.synthesizing import make_synthesize_notes_node
from deepresearch.nodes.writing import make_write_report_node
from deepresearch.state import SearchResult


class FakeSearchClient:
    def search(self, query: str, *, subquestion_id: str, max_results: int):
        return [SearchResult(subquestion_id=subquestion_id, title="Source", url="https://example.com/source", content="AI search uses generated answers.")]


def test_full_graph_runs_offline(tmp_path):
    llm = FakeLLMClient([
        '{"subquestions":[{"id":"q1","question":"What is AI search?","search_query":"AI search","rationale":"Background"}]}',
        '{"notes":[{"subquestion_id":"q1","key_findings":["AI search uses generated answers."],"source_urls":["https://example.com/source"],"confidence":"high"}]}',
        '# AI Search\n\n## Sources\n\n- https://example.com/source',
        '{"passed":true,"score":90,"issues":[],"suggestions":[]}',
    ])
    search = FakeSearchClient()

    app = create_research_app(
        plan_research=make_plan_research_node(llm, max_subquestions=5),
        search_web=make_search_web_node(search, results_per_query=5),
        synthesize_notes=make_synthesize_notes_node(llm),
        write_report=make_write_report_node(llm),
        review_report=make_review_report_node(llm),
        save_report=make_save_report_node(tmp_path),
    )

    result = app.invoke({"question": "AI search", "errors": []})

    assert result["output_path"]
    assert result["review"].score == 90
    assert "# AI Search" in result["report_markdown"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_graph_structure.py tests/test_integration_offline.py -v
```

Expected: FAIL because `graph.py` does not exist yet.

- [ ] **Step 4: Implement graph assembly**

Create `src/deepresearch/graph.py`:

```python
from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from deepresearch.state import ResearchState

NODE_SEQUENCE = [
    "plan_research",
    "search_web",
    "synthesize_notes",
    "write_report",
    "review_report",
    "save_report",
]

Node = Callable[[ResearchState], ResearchState]


def build_research_graph(
    *,
    plan_research: Node,
    search_web: Node,
    synthesize_notes: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
):
    graph = StateGraph(ResearchState)
    graph.add_node("plan_research", plan_research)
    graph.add_node("search_web", search_web)
    graph.add_node("synthesize_notes", synthesize_notes)
    graph.add_node("write_report", write_report)
    graph.add_node("review_report", review_report)
    graph.add_node("save_report", save_report)

    graph.add_edge(START, "plan_research")
    graph.add_edge("plan_research", "search_web")
    graph.add_edge("search_web", "synthesize_notes")
    graph.add_edge("synthesize_notes", "write_report")
    graph.add_edge("write_report", "review_report")
    graph.add_edge("review_report", "save_report")
    graph.add_edge("save_report", END)
    return graph.compile()


def create_research_app(
    *,
    plan_research: Node,
    search_web: Node,
    synthesize_notes: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
):
    return build_research_graph(
        plan_research=plan_research,
        search_web=search_web,
        synthesize_notes=synthesize_notes,
        write_report=write_report,
        review_report=review_report,
        save_report=save_report,
    )
```

- [ ] **Step 5: Run graph and offline integration tests**

Run:

```bash
uv run pytest tests/test_graph_structure.py tests/test_integration_offline.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit if this is a git repository**

Run:

```bash
git status
```

If this is a git repository:

```bash
git add src/deepresearch/graph.py tests/test_graph_structure.py tests/test_integration_offline.py
git commit -m "feat: assemble research graph"
```

---

### Task 8: CLI entrypoint

**Files:**
- Create: `src/deepresearch/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI missing-config test**

Create `tests/test_cli.py`:

```python
from typer.testing import CliRunner

from deepresearch.cli import app


runner = CliRunner()


def test_cli_reports_missing_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = runner.invoke(app, ["AI search"])

    assert result.exit_code == 1
    assert "DEEPSEEK_API_KEY is not set" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py -v
```

Expected: FAIL because `cli.py` does not exist yet.

- [ ] **Step 3: Implement CLI**

Create `src/deepresearch/cli.py`:

```python
import typer
from rich.console import Console
from rich.markdown import Markdown

from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily import TavilySearchClient
from deepresearch.config import AppConfig
from deepresearch.errors import ConfigError, DeepResearchError
from deepresearch.graph import create_research_app
from deepresearch.nodes.planning import make_plan_research_node
from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.nodes.saving import make_save_report_node
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.nodes.synthesizing import make_synthesize_notes_node
from deepresearch.nodes.writing import make_write_report_node

app = typer.Typer(no_args_is_help=True)
console = Console()


def _build_app(config: AppConfig):
    assert config.deepseek_api_key is not None
    assert config.tavily_api_key is not None
    llm = DeepSeekLLMClient(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )
    search = TavilySearchClient(api_key=config.tavily_api_key)
    return create_research_app(
        plan_research=make_plan_research_node(llm, config.max_subquestions),
        search_web=make_search_web_node(search, config.results_per_query),
        synthesize_notes=make_synthesize_notes_node(llm),
        write_report=make_write_report_node(llm),
        review_report=make_review_report_node(llm),
        save_report=make_save_report_node(config.output_dir),
    )


@app.command()
def main(
    question: str = typer.Argument(..., help="Research question"),
    max_subquestions: int | None = typer.Option(None, "--max-subquestions", help="Maximum generated subquestions"),
    results_per_query: int | None = typer.Option(None, "--results-per-query", help="Tavily results per query"),
    output_dir: str | None = typer.Option(None, "--output-dir", help="Report output directory"),
    model: str | None = typer.Option(None, "--model", help="DeepSeek model override"),
    verbose: bool = typer.Option(False, "--verbose", help="Print debugging details"),
):
    try:
        config = AppConfig.from_env().with_overrides(
            max_subquestions=max_subquestions,
            results_per_query=results_per_query,
            output_dir=output_dir,
            model=model,
            verbose=verbose,
        )
        config.validate_required()
        research_app = _build_app(config)

        steps = [
            "[1/6] Planning research...",
            "[2/6] Searching web...",
            "[3/6] Synthesizing notes...",
            "[4/6] Writing report...",
            "[5/6] Reviewing report...",
            "[6/6] Saving report...",
        ]
        for step in steps:
            console.print(step)

        result = research_app.invoke({"question": question, "errors": []})
        console.print(f"\nSaved report to: {result['output_path']}\n")
        console.print(Markdown(result.get("report_markdown", "")))

        if verbose and result.get("errors"):
            console.print("\nErrors:")
            for error in result["errors"]:
                console.print(f"- {error}")
    except ConfigError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(code=1) from exc
    except DeepResearchError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run CLI test**

Run:

```bash
uv run pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full offline test suite**

Run:

```bash
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 6: Commit if this is a git repository**

Run:

```bash
git status
```

If this is a git repository:

```bash
git add src/deepresearch/cli.py tests/test_cli.py
git commit -m "feat: add deepresearch CLI"
```

---

### Task 9: Documentation and optional online smoke test

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README with CLI options and smoke test**

Replace `README.md` with:

```markdown
# Deep Research Agent

A Python + LangGraph command-line Deep Research Agent using DeepSeek v4 pro through an OpenAI-compatible API and Tavily Search API.

## Workflow

```text
plan_research → search_web → synthesize_notes → write_report → review_report → save_report
```

## Setup

```bash
uv sync
cp .env.example .env
```

Fill in `.env`:

```env
DEEPSEEK_API_KEY=...
TAVILY_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro
```

## Run

```bash
uv run deepresearch "AI 搜索引擎的发展趋势"
```

Options:

```bash
uv run deepresearch "AI 搜索引擎的发展趋势" \
  --max-subquestions 5 \
  --results-per-query 5 \
  --output-dir reports \
  --model deepseek-v4-pro \
  --verbose
```

## Test

Offline tests do not call real APIs:

```bash
uv run pytest
```

## Optional online smoke test

This calls real external services and may consume API quota:

```bash
uv run deepresearch "AI 搜索引擎的发展趋势"
```

A successful smoke test should:

- Show six progress stages
- Call DeepSeek
- Call Tavily
- Print a Markdown report
- Save the report under `reports/`

## Output

Reports are saved as timestamped Markdown files under `reports/`.
Each saved report includes a `Quality Review` section.
```

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 3: Run CLI missing-key check**

Run in a shell without the API keys set:

```bash
uv run deepresearch "AI search"
```

Expected: prints `Error: DEEPSEEK_API_KEY is not set...` or `Error: TAVILY_API_KEY is not set...` and exits non-zero.

- [ ] **Step 4: Run optional online smoke test only when keys are configured**

Run:

```bash
uv run deepresearch "AI 搜索引擎的发展趋势"
```

Expected: report is printed and a Markdown file is created under `reports/`.

- [ ] **Step 5: Commit if this is a git repository**

Run:

```bash
git status
```

If this is a git repository:

```bash
git add README.md reports/.gitkeep
git commit -m "docs: document deepresearch usage"
```

---

## Self-Review

Spec coverage check:

- Python + uv project: Task 1.
- CLI command argument input: Task 8.
- LangGraph fixed pipeline: Task 7.
- DeepSeek through OpenAI-compatible API: Task 4.
- Tavily search backend: Task 4 and Task 6.
- Structured state models: Task 2.
- Planning, searching, synthesizing, writing, reviewing, saving nodes: Tasks 5 and 6.
- Terminal progress output: Task 8.
- Save report to `reports/`: Task 3, Task 6, Task 8.
- Print full Markdown report: Task 8.
- Fatal and non-fatal errors: Tasks 4, 5, 6, 8.
- Unit tests and offline integration tests: Tasks 2, 3, 5, 6, 7, 8.
- Optional online smoke test: Task 9.

Placeholder scan:

- `.env.example` and README contain `...` only as user-facing secret examples.
- No task contains undefined implementation placeholders.
- Every code-bearing step provides concrete code.

Type consistency check:

- `ResearchState`, `SubQuestion`, `SearchResult`, `ResearchNote`, and `ReviewResult` are defined in Task 2 and reused consistently.
- Client protocols expose `complete()` and `search()` methods used by nodes.
- Node factory names match graph assembly names.
- `save_report()` returns a `Path`; saving node converts it to `str` for graph state.
