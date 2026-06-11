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
