# Deep Research Agent

A Python + LangGraph command-line Deep Research Agent using DeepSeek v4 pro through an OpenAI-compatible API and Tavily Search API.

## Workflow

```text
plan_research → search_web → prepare_evidence → synthesize_notes → write_report → review_report → save_report
```

## Evidence pipeline

v0.2 uses an extract-based evidence pipeline:

```text
search → source scoring → selected source extraction → EvidenceCard → notes → report
```

Search results are treated as candidate sources. The tool does not assume Tavily `content` is full source text. Selected sources are extracted with Tavily `extract()` when possible, and evidence cards bind each claim to a source URL and supporting snippet.

Verbose mode reports search coverage, source quality distribution, and evidence reliability distribution.

## Setup

```bash
uv sync
cp .env.example .env
```

Fill in `.env`:

```env
DEEPSEEK_API_KEY=...
TAVILY_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
```

Do not commit or share `.env`; it contains API secrets. Keep real keys out of source control.

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

## Citation format

Reports use strict numbered citations:

```markdown
AI search is changing discovery.[1]

## Sources

[1] https://example.com/source-a
```

The tool validates that every body citation is defined in `## Sources`, every source is cited in the body, and every numbered source URL comes from Tavily search results.

If the first generated report fails citation validation, the tool automatically rewrites the report once. This automatic rewrite may make one additional DeepSeek API call and consume quota. If the rewrite also fails, it saves a `-failed.md` report with both validation failure reasons.

## Optional online smoke test

This calls real external services and may consume API quota. An online run can make multiple DeepSeek calls and many Tavily calls: 2-3 search queries per subquestion, up to 5 subquestions by default, Tavily extraction for selected sources, plus a possible DeepSeek rewrite if citation validation fails. For cheaper smoke tests, use smaller `--max-subquestions` and `--results-per-query` values:

```bash
uv run deepresearch "AI 搜索引擎的发展趋势"
```

A successful smoke test should:

- Show seven progress stages, including Preparing evidence
- Call DeepSeek
- Call Tavily
- Print a Markdown report
- Save the report under `reports/`

## Output

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

Reports are saved as timestamped Markdown files under `reports/`.
Each saved report includes a `Quality Review` section.
