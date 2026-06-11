# Deep Research Agent Design

Date: 2026-06-10

## 1. Overview

Build a Python command-line Deep Research Agent based on LangGraph. The user provides a research question as a command argument. The agent performs a fixed workflow:

1. Decompose the question into subquestions
2. Search the web with Tavily
3. Synthesize research notes
4. Write a structured Markdown report
5. Review report quality
6. Save and print the final report

The first version is an MVP stable release. It prioritizes reliability, observability, clear state transitions, source-backed writing, and testability over autonomous multi-agent behavior or iterative self-improvement.

Confirmed decisions:

- Project type: Python CLI tool
- Package manager: uv
- Workflow framework: LangGraph
- Search backend: Tavily Search API
- LLM provider: DeepSeek v4 pro through an OpenAI-compatible API
- CLI input: command argument, e.g. `deepresearch "research question"`
- Output: print full Markdown report in terminal and save it under `reports/`
- First-version workflow: fixed linear MVP pipeline

## 2. Goals

The first version should:

- Accept a research question from the CLI
- Run a deterministic LangGraph workflow
- Use DeepSeek to plan, synthesize, write, and review
- Use Tavily to collect web search results
- Produce a structured Markdown research report
- Include source URLs in the report
- Save the report to disk
- Print the full report in the terminal
- Surface failures clearly instead of pretending success
- Provide enough tests to validate the core engineering behavior

## 3. Non-Goals

The first version will not implement:

- Web UI
- Database persistence
- Vector database or RAG over local documents
- User accounts
- Interactive chat mode
- YAML/JSON task files
- Automatic research retry loops
- Multi-agent collaboration
- Concurrent search
- PDF/DOCX export
- Search result caching
- Historical report indexing

These are possible later extensions.

## 4. Architecture

The project will use four layers:

```text
CLI layer
  ↓
LangGraph workflow layer
  ↓
Node business logic layer
  ↓
External service adapter layer
```

### 4.1 CLI Layer

The CLI receives a research question and optional runtime parameters. It loads configuration, initializes the workflow, executes it, prints progress, prints the final Markdown report, and shows the saved output path.

Example:

```bash
deepresearch "分析 2026 年 AI 搜索引擎的发展趋势"
```

### 4.2 LangGraph Workflow Layer

The graph is a fixed linear workflow:

```text
START
  → plan_research
  → search_web
  → synthesize_notes
  → write_report
  → review_report
  → save_report
END
```

MVP does not branch on review result. The review result is preserved and shown, but the report is saved even if the review fails.

### 4.3 Node Business Logic Layer

Each node is a focused function that accepts and returns `ResearchState` updates.

Nodes:

| Node | Responsibility |
|---|---|
| `plan_research` | Decompose user question into subquestions and search queries |
| `search_web` | Run Tavily searches and normalize results |
| `synthesize_notes` | Convert search results into source-backed research notes |
| `write_report` | Generate the final structured Markdown report |
| `review_report` | Review report quality and produce structured feedback |
| `save_report` | Persist the Markdown report and return the output path |

### 4.4 External Service Adapter Layer

External services are isolated behind adapters:

| Adapter | Responsibility |
|---|---|
| `llm_client` | Call DeepSeek v4 pro through OpenAI-compatible API |
| `search_client` | Call Tavily Search API |
| `report_writer` | Generate filenames and save Markdown files |
| `config` | Load defaults, environment variables, and CLI overrides |

This keeps workflow code independent from vendor-specific APIs.

## 5. Initial Directory Structure

```text
deepsearch/
  pyproject.toml
  README.md
  .env.example
  src/
    deepresearch/
      __init__.py
      cli.py
      config.py
      graph.py
      state.py
      nodes/
        __init__.py
        planning.py
        searching.py
        synthesizing.py
        writing.py
        reviewing.py
        saving.py
      clients/
        __init__.py
        llm.py
        tavily.py
      prompts/
        __init__.py
        planning.py
        synthesizing.py
        writing.py
        reviewing.py
      utils/
        __init__.py
        citations.py
        filenames.py
  tests/
    test_state.py
    test_filenames.py
    test_graph_structure.py
    test_report_writer.py
    test_json_parsing.py
  reports/
    .gitkeep
  docs/
    superpowers/
      specs/
```

## 6. Data Models

Use `TypedDict` for LangGraph state and Pydantic models for structured intermediate objects.

### 6.1 ResearchState

```python
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

### 6.2 SubQuestion

Generated by `plan_research`.

```python
class SubQuestion(BaseModel):
    id: str
    question: str
    search_query: str
    rationale: str
```

### 6.3 SearchResult

Normalized result from Tavily.

```python
class SearchResult(BaseModel):
    subquestion_id: str
    title: str
    url: str
    content: str
    score: float | None = None
    published_date: str | None = None
```

### 6.4 ResearchNote

Source-backed synthesized notes.

```python
class ResearchNote(BaseModel):
    subquestion_id: str
    key_findings: list[str]
    source_urls: list[str]
    confidence: Literal["low", "medium", "high"]
```

### 6.5 ReviewResult

Report review output.

```python
class ReviewResult(BaseModel):
    passed: bool
    score: int
    issues: list[str]
    suggestions: list[str]
```

The implementation should constrain `score` to 0-100.

## 7. Citation Strategy

The report must only cite URLs that appeared in `SearchResult.url`. The `write_report` prompt must require source-backed claims and a `Sources` section.

Preferred report format:

```markdown
AI 搜索引擎正在从“链接排序”转向“答案生成”。[^1]

[^1]: https://example.com/article
```

MVP can also use inline Markdown links if simpler. The key rule is: no invented URLs.

## 8. Node Behavior

### 8.1 plan_research

Input:

- `question`

Output:

- `subquestions`

Behavior:

- Call DeepSeek v4 pro
- Generate 3-6 subquestions, bounded by config
- Generate one Tavily search query per subquestion
- Return structured JSON parsed into `SubQuestion`

Failure handling:

- If JSON parsing fails, fallback to one subquestion using the original question as both question and search query
- Record the parse error in `errors`

### 8.2 search_web

Input:

- `subquestions`

Output:

- `search_results`

Behavior:

- For each `search_query`, call Tavily
- Default to 5 results per query
- Normalize results into `SearchResult`

Failure handling:

- If one query fails, record the error and continue
- If all queries fail or no usable results exist, stop the workflow with a clear fatal error

MVP searches sequentially for easier debugging.

### 8.3 synthesize_notes

Input:

- `question`
- `subquestions`
- `search_results`

Output:

- `notes`

Behavior:

- Group search results by `subquestion_id`
- Call DeepSeek to extract key findings and source URLs
- Require that each finding is traceable to supplied URLs
- Mark confidence as `low`, `medium`, or `high`

Failure handling:

- If structured parsing fails, generate conservative fallback notes from result titles/content
- Mark fallback confidence as `low`
- Record the error

### 8.4 write_report

Input:

- `question`
- `subquestions`
- `notes`
- `search_results`

Output:

- `report_markdown`

Report structure:

```markdown
# <研究问题标题>

## 摘要

## 关键结论

## 背景与问题拆解

## 深度分析

### 1. <子问题一>

### 2. <子问题二>

## 风险、不确定性与不同观点

## 结论

## Sources
```

Rules:

- Every key conclusion should include at least one source URL
- Sources must come from `search_results`
- If evidence is weak, state uncertainty explicitly
- Do not invent URLs or unsupported claims

Failure handling:

- If notes or search results are insufficient, generate a failure-style Markdown report that explains the limitation instead of fabricating findings

### 8.5 review_report

Input:

- `question`
- `report_markdown`
- `search_results`

Output:

- `review`

Behavior:

- Call DeepSeek to review quality
- Return `passed`, `score`, `issues`, and `suggestions`

Review criteria:

- Relevance to original question
- Coverage of subquestions
- Source-backed claims
- Avoidance of unsupported assertions
- Markdown readability
- Clear conclusion and uncertainty discussion

MVP does not use the review result for branching.

### 8.6 save_report

Input:

- `question`
- `report_markdown`
- `review`

Output:

- `output_path`

Behavior:

- Ensure output directory exists
- Generate a safe timestamped filename
- Write UTF-8 Markdown
- Append `Quality Review` to the saved report

Example path:

```text
reports/2026-06-10-153000-ai-search-trends.md
```

## 9. Configuration

Configuration priority:

```text
defaults < environment/.env < CLI arguments
```

`.env.example`:

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

## 10. CLI Interface

Base command:

```bash
deepresearch "你的研究问题"
```

Optional arguments:

| Argument | Default | Description |
|---|---:|---|
| `question` | required | Research question |
| `--max-subquestions` | `5` | Maximum generated subquestions |
| `--results-per-query` | `5` | Tavily results per query |
| `--output-dir` | `reports` | Markdown output directory |
| `--model` | `DEEPSEEK_MODEL` | Override default DeepSeek model |
| `--verbose` | `false` | Print debugging details |

Recommended libraries:

- `typer` for CLI parsing
- `rich` for progress and Markdown display

`pyproject.toml` should expose:

```toml
[project.scripts]
deepresearch = "deepresearch.cli:app"
```

## 11. Error Handling

### 11.1 Fatal Errors

Fatal errors terminate the workflow with a clear message:

| Error | Example |
|---|---|
| Missing API key | `DEEPSEEK_API_KEY` or `TAVILY_API_KEY` missing |
| LLM unavailable | Authentication failure, timeout, bad model |
| Search unavailable | All Tavily searches fail |
| Report write failure | Output directory permission error |

The CLI should show clear user-facing errors and avoid unnecessary stack traces in normal mode.

### 11.2 Non-Fatal Errors

Non-fatal errors are stored in `ResearchState.errors` and the workflow continues when possible:

| Error | Handling |
|---|---|
| One search query fails | Continue other queries |
| LLM JSON parse fails | Use fallback data |
| A subquestion lacks good sources | Low confidence notes |
| Review score is low | Save report with review feedback |

### 11.3 Project Exceptions

Use project-specific exception types:

```python
class LLMError(Exception):
    pass

class SearchError(Exception):
    pass

class ReportWriteError(Exception):
    pass
```

## 12. LLM Output Parsing

MVP parsing strategy:

```text
try parse full response as JSON
  ↓ fail
try extract fenced ```json block
  ↓ fail
use conservative fallback
```

Pydantic validates parsed structures.

Avoid implementing a complex JSON-repair agent in the first version.

## 13. Observability

Normal mode should print progress:

```text
[1/6] Planning research...
[2/6] Searching web...
[3/6] Synthesizing notes...
[4/6] Writing report...
[5/6] Reviewing report...
[6/6] Saving report...
```

Verbose mode may print:

- Generated subquestions
- Search queries
- Result counts
- Review score and issues

Never print:

- API keys
- Secrets
- Full raw API responses by default
- Excessively long search payloads

## 14. Testing Strategy

Use `pytest`.

### 14.1 Unit Tests

`test_state.py`:

- Validate `SubQuestion`
- Validate `SearchResult`
- Validate `ResearchNote` confidence enum
- Validate `ReviewResult` score range

`test_filenames.py`:

- Safe slug generation
- Special characters removed
- Empty or non-ASCII questions have fallback filename
- Filename includes timestamp

`test_report_writer.py`:

- Creates output directory
- Writes UTF-8 Markdown
- Returns existing path
- Appends quality review

`test_graph_structure.py`:

- Graph compiles
- Node sequence is correct

`test_json_parsing.py`:

- Parses raw JSON
- Parses fenced JSON code blocks
- Falls back on invalid JSON
- Handles missing required fields

### 14.2 Offline Integration Test

Use fake clients to run the full graph without external API calls.

Expected behavior:

- Input question enters state
- Fake planning returns subquestions
- Fake search returns results
- Notes are generated
- Markdown report is generated
- Review is generated
- Report file is saved

### 14.3 Optional Online Smoke Test

Manual command requiring real credentials:

```bash
uv run deepresearch "AI 搜索引擎的发展趋势"
```

Purpose:

- Confirm CLI startup
- Confirm environment variables
- Confirm DeepSeek connectivity
- Confirm Tavily connectivity
- Confirm graph runs end-to-end
- Confirm Markdown is saved and printed

This is not part of default tests because it depends on external APIs, network, cost, and nondeterministic model output.

## 15. Acceptance Criteria

Running:

```bash
uv run deepresearch "分析 AI 搜索引擎在 2026 年的发展趋势"
```

Should:

- Show the six progress stages
- Generate a Markdown report
- Print the report in the terminal
- Save the report under `reports/`
- Print the saved path

The report should contain:

- Title
- Summary
- Key findings
- Background and question decomposition
- Deep analysis
- Risks, uncertainty, or alternative views
- Conclusion
- Sources
- Quality Review

Citation acceptance:

- At least 3 source URLs when search succeeds
- Sources section lists cited URLs
- Key claims include citations or source links
- No fabricated URLs outside search results

Error acceptance:

- Missing `TAVILY_API_KEY` gives a clear error
- Missing `DEEPSEEK_API_KEY` gives a clear error
- One failed search query does not abort all work
- All failed searches produce a clear failure instead of a fake report

## 16. First-Version Quality Strategy

MVP quality is guaranteed through:

- Fixed, predictable workflow
- Structured intermediate data
- Source URL constraints
- Explicit quality review node
- Conservative fallback behavior
- Clear fatal vs non-fatal errors
- Unit tests and offline integration tests
- Optional real API smoke test

The MVP does not guarantee perfect factual accuracy or expert-level research depth. It guarantees a stable, inspectable, source-backed research pipeline that can be extended later.

## 17. Future Extensions

Possible post-MVP improvements:

1. Review-failure conditional loop
2. Additional search queries from reviewer feedback
3. Concurrent Tavily search
4. Multiple search backends
5. Configurable report templates
6. Search result caching
7. YAML research task files
8. Web UI
9. Multi-agent planning/review
10. PDF/DOCX export
11. Historical report index
12. Source credibility scoring
