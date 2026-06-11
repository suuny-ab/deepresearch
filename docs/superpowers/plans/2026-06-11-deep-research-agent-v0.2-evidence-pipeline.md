# Deep Research Agent v0.2 Evidence Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Extract-based Evidence Pipeline，让报告从搜索摘要驱动升级为可追溯 EvidenceCard 驱动。

**Architecture:** 在现有 LangGraph 主流程中新增 `prepare_evidence` 单节点，位于 `search_web` 与 `synthesize_notes` 之间。`prepare_evidence` 内部完成 URL 去重、来源质量评分、选中来源抽取、EvidenceCard 生成和 evidence metrics 计算；后续 notes 和 report 只基于 EvidenceCard。

**Tech Stack:** Python 3.11+、uv、pytest、Pydantic、LangGraph、Tavily SDK、Typer/Rich；文档中文，代码标识符英文。

---

## 当前上下文

当前 `main` 已包含 v0.1.2：

- 严格 `[n]` 编号引用
- citation validator
- 写作失败自动重写一次
- `--verbose` 工作流可观测性
- 在线 3 题验收通过

v0.2 的依据文档：

```text
docs/superpowers/reports/2026-06-11-tavily-capability-investigation.md
docs/superpowers/specs/2026-06-11-deep-research-agent-v0.2-evidence-pipeline.md
```

执行本计划前应处于干净工作区。

---

## 文件结构变化

新增：

```text
src/deepresearch/source_quality.py
src/deepresearch/utils/urls.py
src/deepresearch/nodes/prepare_evidence.py
src/deepresearch/prompts/evidence.py
tests/test_source_quality.py
tests/test_urls.py
tests/test_prepare_evidence_node.py
tests/test_evidence_prompt.py
```

修改：

```text
src/deepresearch/state.py
src/deepresearch/prompts/planning.py
src/deepresearch/nodes/planning.py
src/deepresearch/nodes/searching.py
src/deepresearch/clients/tavily.py
src/deepresearch/graph.py
src/deepresearch/cli.py
src/deepresearch/prompts/synthesizing.py
src/deepresearch/nodes/synthesizing.py
src/deepresearch/prompts/writing.py
src/deepresearch/nodes/writing.py
src/deepresearch/verbose.py
README.md
```

---

### Task 0: 预检当前状态

**Files:**
- 不修改文件。

- [ ] **Step 1: 检查 git 状态**

Run:

```bash
git status --short
```

Expected: 无输出。

- [ ] **Step 2: 运行当前测试**

Run:

```bash
uv run pytest -v
```

Expected: 当前 v0.1.2 测试全部通过。

- [ ] **Step 3: 不提交**

本任务不产生 commit。

---

### Task 1: 扩展数据模型

**Files:**
- Modify: `src/deepresearch/state.py`
- Modify: `tests/test_state.py`

- [ ] **Step 1: 添加失败测试**

Append to `tests/test_state.py`:

```python
def test_subquestion_accepts_multiple_search_queries():
    from deepresearch.state import SubQuestion

    item = SubQuestion(
        id="q1",
        question="AI 搜索技术趋势是什么？",
        search_query="AI 搜索 技术趋势",
        search_queries=[
            "AI 搜索 技术趋势 RAG",
            "AI search technology trends RAG 2026",
        ],
        rationale="覆盖中英文来源",
    )

    assert item.search_queries == [
        "AI 搜索 技术趋势 RAG",
        "AI search technology trends RAG 2026",
    ]


def test_search_result_accepts_query_and_source_quality_fields():
    from deepresearch.state import SearchResult

    item = SearchResult(
        subquestion_id="q1",
        query="AI search trends",
        title="Report",
        url="https://example.com/report",
        content="Summary",
        source_type="industry_report",
        source_quality_score=85,
        source_quality_reason="Report-like source",
    )

    assert item.query == "AI search trends"
    assert item.source_type == "industry_report"
    assert item.source_quality_score == 85


def test_evidence_card_model_requires_traceable_fields():
    from deepresearch.state import EvidenceCard

    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="RAG remains important for AI search.",
        source_url="https://example.com/report",
        source_title="AI Search Report",
        supporting_snippet="RAG remains a core architecture for AI search systems.",
        content_type="extracted_content",
        source_type="industry_report",
        source_quality_score=85,
        evidence_reliability="high",
        confidence="high",
    )

    assert card.source_url == "https://example.com/report"
    assert card.supporting_snippet
    assert card.evidence_reliability == "high"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_state.py -v
```

Expected: fails because fields/classes do not exist.

- [ ] **Step 3: 更新 state.py**

Modify `src/deepresearch/state.py`:

```python
SourceType = Literal[
    "official",
    "academic",
    "industry_report",
    "reputable_media",
    "company_blog",
    "blog",
    "forum",
    "seo_content",
    "unknown",
]

ContentType = Literal["search_content", "raw_content", "extracted_content"]
EvidenceReliability = Literal["low", "medium", "high"]
```

Update `SubQuestion`:

```python
class SubQuestion(BaseModel):
    id: str
    question: str
    search_query: str
    search_queries: list[str] = Field(default_factory=list)
    rationale: str
```

Update `SearchResult`:

```python
class SearchResult(BaseModel):
    subquestion_id: str
    title: str
    url: str
    content: str
    query: str | None = None
    raw_content: str | None = None
    content_type: ContentType = "search_content"
    score: float | None = None
    published_date: str | None = None
    source_type: SourceType = "unknown"
    source_quality_score: int = Field(default=50, ge=0, le=100)
    source_quality_reason: str = ""
```

Add:

```python
class ExtractedSource(BaseModel):
    subquestion_id: str
    url: str
    title: str
    raw_content: str
    extract_depth: Literal["basic", "advanced"] = "basic"
    format: Literal["markdown", "text"] = "markdown"
    source_type: SourceType = "unknown"
    source_quality_score: int = Field(default=50, ge=0, le=100)
    source_quality_reason: str = ""


class EvidenceCard(BaseModel):
    id: str
    subquestion_id: str
    claim: str
    source_url: str
    source_title: str
    supporting_snippet: str
    content_type: Literal["search_content", "extracted_content"]
    source_type: SourceType
    source_quality_score: int = Field(ge=0, le=100)
    evidence_reliability: EvidenceReliability
    confidence: Literal["low", "medium", "high"]
```

Update `ResearchState`:

```python
    extracted_sources: list[ExtractedSource]
    evidence_cards: list[EvidenceCard]
    evidence_metrics: dict[str, Any]
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_state.py -v
```

Expected: pass.

- [ ] **Step 5: 提交**

```bash
git add src/deepresearch/state.py tests/test_state.py
git commit -m "feat: add evidence pipeline state models"
```

---

### Task 2: Planning 支持多 query

**Files:**
- Modify: `src/deepresearch/prompts/planning.py`
- Modify: `src/deepresearch/nodes/planning.py`
- Modify: `tests/test_planning_node.py`

- [ ] **Step 1: 添加失败测试**

Append to `tests/test_planning_node.py`:

```python
def test_plan_research_parses_search_queries():
    llm = FakeLLMClient([
        '{"subquestions":[{"id":"q1","question":"What is AI search?","search_query":"AI search definition","search_queries":["AI search definition","AI 搜索 定义"],"rationale":"Background"}]}'
    ])
    node = make_plan_research_node(llm, max_subquestions=5)

    result = node({"question": "AI search trends", "errors": []})

    assert result["subquestions"][0].search_queries == ["AI search definition", "AI 搜索 定义"]
```

- [ ] **Step 2: 添加 prompt 测试**

Create or append to `tests/test_planning_prompt.py`:

```python
from deepresearch.prompts.planning import build_planning_prompt


def test_planning_prompt_requests_multiple_search_queries():
    prompt = build_planning_prompt("AI 搜索趋势", max_subquestions=5)

    assert "search_queries" in prompt
    assert "2" in prompt
    assert "3" in prompt
    assert "中文" in prompt or "Chinese" in prompt
    assert "English" in prompt or "英文" in prompt
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_planning_node.py tests/test_planning_prompt.py -v
```

Expected: prompt test fails until prompt updated.

- [ ] **Step 4: 更新 planning prompt**

Modify `src/deepresearch/prompts/planning.py` to require:

```text
每个子问题输出 search_query 和 search_queries。
search_queries 必须包含 2-3 个不同角度 query：中文 query、英文 query、报告/研究 query。
Return JSON shape includes search_queries.
```

- [ ] **Step 5: 确保 fallback search_queries**

Modify fallback in `src/deepresearch/nodes/planning.py`:

```python
SubQuestion(
    id="q1",
    question=question,
    search_query=question,
    search_queries=[question],
    rationale="Fallback from original question",
)
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_planning_node.py tests/test_planning_prompt.py -v
```

Expected: pass.

- [ ] **Step 7: 提交**

```bash
git add src/deepresearch/prompts/planning.py src/deepresearch/nodes/planning.py tests/test_planning_node.py tests/test_planning_prompt.py
git commit -m "feat: plan multiple search queries per subquestion"
```

---

### Task 3: search_web 支持多 query 并记录 query

**Files:**
- Modify: `src/deepresearch/nodes/searching.py`
- Modify: `src/deepresearch/clients/tavily.py`
- Modify: `tests/test_searching_node.py`

- [ ] **Step 1: 添加失败测试**

Append to `tests/test_searching_node.py`:

```python
def test_search_web_runs_all_search_queries():
    client = FakeSearchClient()
    node = make_search_web_node(client, results_per_query=3)

    result = node({
        "subquestions": [SubQuestion(
            id="q1",
            question="What?",
            search_query="fallback query",
            search_queries=["query one", "query two", "query three"],
            rationale="Coverage",
        )],
        "errors": [],
    })

    assert client.queries == ["query one", "query two", "query three"]
    assert [item.query for item in result["search_results"]] == ["query one", "query two", "query three"]
```

- [ ] **Step 2: 更新 FakeSearchClient**

In `tests/test_searching_node.py`, ensure fake search returns `SearchResult(..., query=query)`.

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_searching_node.py -v
```

Expected: fails because searching only uses `search_query`.

- [ ] **Step 4: 更新 search_web**

Modify `src/deepresearch/nodes/searching.py`:

```python
def _queries_for(subquestion) -> list[str]:
    return subquestion.search_queries or [subquestion.search_query]
```

Loop:

```python
for subquestion in state.get("subquestions", []):
    for query in _queries_for(subquestion):
        results.extend(search_client.search(query, subquestion_id=subquestion.id, max_results=results_per_query))
```

- [ ] **Step 5: 更新 Tavily client 记录 query**

Modify `src/deepresearch/clients/tavily.py` SearchResult construction:

```python
query=query,
```

Also call Tavily with v0.2 defaults:

```python
response = self._client.search(
    query=query,
    max_results=max_results,
    search_depth="basic",
    include_raw_content=False,
    include_answer=False,
    include_usage=True,
)
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_searching_node.py -v
```

Expected: pass.

- [ ] **Step 7: 提交**

```bash
git add src/deepresearch/nodes/searching.py src/deepresearch/clients/tavily.py tests/test_searching_node.py
git commit -m "feat: search all planned queries"
```

---

### Task 4: Source quality scoring

**Files:**
- Create: `src/deepresearch/source_quality.py`
- Create: `tests/test_source_quality.py`

- [ ] **Step 1: 编写失败测试**

Create `tests/test_source_quality.py`:

```python
from deepresearch.source_quality import classify_source
from deepresearch.state import SearchResult


def result(url: str, title: str = "Title", content: str = "Content") -> SearchResult:
    return SearchResult(subquestion_id="q1", title=title, url=url, content=content)


def test_classify_official_source():
    quality = classify_source(result("https://www.gov.cn/zhengce/example.html", title="政策文件"))

    assert quality.source_type == "official"
    assert quality.score >= 90


def test_classify_academic_source():
    quality = classify_source(result("https://doi.org/10.1234/example", title="Academic Paper"))

    assert quality.source_type == "academic"
    assert quality.score >= 85


def test_classify_industry_report_pdf():
    quality = classify_source(result("https://example.com/report.pdf", title="AI Search Industry Report 2026"))

    assert quality.source_type == "industry_report"
    assert quality.score >= 80


def test_classify_seo_content():
    quality = classify_source(result("https://www.seo.com/blog/ai-search-trends", title="AI Search Trends"))

    assert quality.source_type == "seo_content"
    assert quality.score <= 40


def test_quality_score_is_not_tavily_score():
    item = result("https://www.seo.com/blog/ai-search-trends")
    item.score = 0.95

    quality = classify_source(item)

    assert quality.score <= 40
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_source_quality.py -v
```

Expected: module missing.

- [ ] **Step 3: 实现 source_quality.py**

Create `src/deepresearch/source_quality.py`:

```python
from pydantic import BaseModel, Field

from deepresearch.state import SearchResult, SourceType


class SourceQuality(BaseModel):
    source_type: SourceType
    score: int = Field(ge=0, le=100)
    reason: str


def classify_source(result: SearchResult) -> SourceQuality:
    url = result.url.lower()
    title = result.title.lower()

    if ".gov" in url or "gov.cn" in url:
        return SourceQuality(source_type="official", score=95, reason="Government or official domain")
    if "doi.org" in url or "arxiv.org" in url or "sciengine.com" in url:
        return SourceQuality(source_type="academic", score=90, reason="Academic or DOI-like source")
    if url.endswith(".pdf") or any(term in title for term in ["report", "whitepaper", "research", "报告", "白皮书"]):
        return SourceQuality(source_type="industry_report", score=85, reason="Report-like source")
    if any(domain in url for domain in ["reuters.com", "bloomberg.com", "news.cn", "stcn.com", "21jingji.com", "36kr.com"]):
        return SourceQuality(source_type="reputable_media", score=75, reason="Recognized media domain")
    if any(domain in url for domain in ["seo.com", "semrush.com", "hubspot.com"]):
        return SourceQuality(source_type="seo_content", score=20, reason="SEO/marketing content domain")
    if any(domain in url for domain in ["zhihu.com", "csdn.net", "cnblogs.com"]):
        return SourceQuality(source_type="blog", score=45, reason="Blog/forum-like domain")
    if "/blog" in url:
        return SourceQuality(source_type="blog", score=45, reason="Blog path")
    if any(domain in url for domain in ["openai.com", "anthropic.com", "google.com", "microsoft.com", "aws.amazon.com", "aliyun.com", "volcengine.com"]):
        return SourceQuality(source_type="company_blog", score=65, reason="Company or vendor domain")
    return SourceQuality(source_type="unknown", score=50, reason="No strong quality signal")
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_source_quality.py -v
```

Expected: pass.

- [ ] **Step 5: 提交**

```bash
git add src/deepresearch/source_quality.py tests/test_source_quality.py
git commit -m "feat: add source quality scoring"
```

---

### Task 5: URL 去重工具

**Files:**
- Create: `src/deepresearch/utils/urls.py`
- Create: `tests/test_urls.py`

- [ ] **Step 1: 编写失败测试**

Create `tests/test_urls.py`:

```python
from deepresearch.utils.urls import normalize_url


def test_normalize_url_removes_www_and_trailing_slash():
    assert normalize_url("https://www.example.com/article/") == "https://example.com/article"


def test_normalize_url_removes_tracking_params():
    assert normalize_url("https://example.com/article?utm_source=x&gclid=y&id=123") == "https://example.com/article?id=123"


def test_normalize_url_lowercases_host_only():
    assert normalize_url("https://Example.com/CasePath") == "https://example.com/CasePath"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_urls.py -v
```

Expected: module missing.

- [ ] **Step 3: 实现 urls.py**

Create `src/deepresearch/utils/urls.py`:

```python
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"gclid", "fbclid", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or parsed.path
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in _TRACKING_KEYS or any(lowered.startswith(prefix) for prefix in _TRACKING_PREFIXES):
            continue
        query_items.append((key, value))
    query = urlencode(query_items)
    return urlunsplit((scheme, netloc, path, query, ""))
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_urls.py -v
```

Expected: pass.

- [ ] **Step 5: 提交**

```bash
git add src/deepresearch/utils/urls.py tests/test_urls.py
git commit -m "feat: add URL normalization"
```

---

### Task 6: Tavily client 支持 extract

**Files:**
- Modify: `src/deepresearch/clients/tavily.py`
- Modify: `tests/test_searching_node.py` or Create: `tests/test_tavily_client.py`

- [ ] **Step 1: 添加 protocol 测试/伪客户端测试**

Create `tests/test_tavily_client.py`:

```python
from deepresearch.clients.tavily import TavilySearchClient


class FakeTavilySDK:
    def __init__(self):
        self.search_calls = []
        self.extract_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return {
            "results": [
                {"title": "Title", "url": "https://example.com/a", "content": "Summary", "score": 0.9}
            ]
        }

    def extract(self, urls, **kwargs):
        self.extract_calls.append({"urls": urls, **kwargs})
        return {
            "results": [
                {"title": "Title", "url": "https://example.com/a", "raw_content": "Full markdown"}
            ],
            "failed_results": [],
        }


def test_tavily_search_client_uses_v02_search_defaults():
    client = TavilySearchClient(api_key="dummy")
    client._client = FakeTavilySDK()

    results = client.search("query", subquestion_id="q1", max_results=3)

    assert results[0].query == "query"
    assert client._client.search_calls[0]["search_depth"] == "basic"
    assert client._client.search_calls[0]["include_raw_content"] is False
    assert client._client.search_calls[0]["include_answer"] is False
    assert client._client.search_calls[0]["include_usage"] is True


def test_tavily_search_client_extracts_sources():
    client = TavilySearchClient(api_key="dummy")
    client._client = FakeTavilySDK()

    extracted = client.extract(["https://example.com/a"], subquestion_id="q1")

    assert extracted[0].url == "https://example.com/a"
    assert extracted[0].raw_content == "Full markdown"
    assert client._client.extract_calls[0]["format"] == "markdown"
    assert client._client.extract_calls[0]["extract_depth"] == "basic"
    assert client._client.extract_calls[0]["include_usage"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_tavily_client.py -v
```

Expected: fails because extract method missing and defaults not set.

- [ ] **Step 3: 更新 Tavily client**

Modify `src/deepresearch/clients/tavily.py`:

- Import `ExtractedSource`.
- Extend `SearchClient` protocol:

```python
    def extract(self, urls: list[str], *, subquestion_id: str) -> list[ExtractedSource]:
        ...
```

- Update search call:

```python
response = self._client.search(
    query=query,
    max_results=max_results,
    search_depth="basic",
    include_raw_content=False,
    include_answer=False,
    include_usage=True,
)
```

- Include `query=query` in `SearchResult`.

- Add extract method:

```python
def extract(self, urls: list[str], *, subquestion_id: str) -> list[ExtractedSource]:
    try:
        response = self._client.extract(
            urls,
            extract_depth="basic",
            format="markdown",
            include_usage=True,
        )
        return [
            ExtractedSource(
                subquestion_id=subquestion_id,
                url=item.get("url") or "",
                title=item.get("title") or "Untitled",
                raw_content=item.get("raw_content") or "",
                extract_depth="basic",
                format="markdown",
            )
            for item in response.get("results", [])
            if item.get("url") and item.get("raw_content")
        ]
    except Exception as exc:
        raise SearchError(str(exc)) from exc
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_tavily_client.py -v
```

Expected: pass.

- [ ] **Step 5: 提交**

```bash
git add src/deepresearch/clients/tavily.py tests/test_tavily_client.py
git commit -m "feat: add Tavily extract support"
```

---

### Task 7: prepare_evidence 节点

**Files:**
- Create: `src/deepresearch/nodes/prepare_evidence.py`
- Create: `src/deepresearch/prompts/evidence.py`
- Create: `tests/test_prepare_evidence_node.py`
- Create: `tests/test_evidence_prompt.py`

- [ ] **Step 1: 编写 evidence prompt 测试**

Create `tests/test_evidence_prompt.py`:

```python
from deepresearch.prompts.evidence import build_evidence_prompt
from deepresearch.state import ExtractedSource


def test_evidence_prompt_requires_evidence_cards():
    source = ExtractedSource(
        subquestion_id="q1",
        url="https://example.com/a",
        title="Source A",
        raw_content="RAG remains important for AI search.",
        source_type="industry_report",
        source_quality_score=85,
        source_quality_reason="Report-like source",
    )

    prompt = build_evidence_prompt("AI search", [source])

    assert "EvidenceCard" in prompt
    assert "supporting_snippet" in prompt
    assert "Do not create claims not supported by the source text" in prompt
    assert "https://example.com/a" in prompt
```

- [ ] **Step 2: 编写 prepare_evidence 测试**

Create `tests/test_prepare_evidence_node.py`:

```python
from tests.conftest import FakeLLMClient

from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node
from deepresearch.state import SearchResult, SubQuestion


class FakeSearchClient:
    def __init__(self, fail_extract=False):
        self.extracted_urls = []
        self.fail_extract = fail_extract

    def extract(self, urls, *, subquestion_id):
        self.extracted_urls.extend(urls)
        if self.fail_extract:
            raise Exception("extract failed")
        return []


def test_prepare_evidence_dedupes_scores_extracts_and_builds_cards():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"RAG remains important.","source_url":"https://example.com/report.pdf","source_title":"Report","supporting_snippet":"RAG remains important.","content_type":"extracted_content","source_type":"industry_report","source_quality_score":85,"evidence_reliability":"high","confidence":"high"}]}'
    ])
    search = FakeSearchClient()
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    state = {
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q1", title="Report", url="https://example.com/report.pdf", content="Summary"),
            SearchResult(subquestion_id="q1", query="q2", title="Report duplicate", url="https://www.example.com/report.pdf?utm_source=x", content="Summary duplicate"),
        ],
        "errors": [],
    }

    result = node(state)

    assert len(search.extracted_urls) == 1
    assert result["search_results"][0].source_type == "industry_report"
    assert result["evidence_cards"][0].id == "e1"
    assert result["evidence_metrics"]["raw_search_results"] == 2
    assert result["evidence_metrics"]["deduped_sources"] == 1
    assert result["evidence_metrics"]["duplicates_removed"] == 1


def test_prepare_evidence_falls_back_to_search_content_when_extract_fails():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Fallback claim.","source_url":"https://example.com/a","source_title":"A","supporting_snippet":"Summary","content_type":"search_content","source_type":"unknown","source_quality_score":50,"evidence_reliability":"low","confidence":"low"}]}'
    ])
    search = FakeSearchClient(fail_extract=True)
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [SearchResult(subquestion_id="q1", query="q", title="A", url="https://example.com/a", content="Summary")],
        "errors": [],
    })

    assert result["evidence_cards"][0].content_type == "search_content"
    assert result["evidence_cards"][0].evidence_reliability == "low"
    assert result["errors"]
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
uv run pytest tests/test_prepare_evidence_node.py tests/test_evidence_prompt.py -v
```

Expected: modules missing.

- [ ] **Step 4: 实现 evidence prompt**

Create `src/deepresearch/prompts/evidence.py`:

```python
from deepresearch.state import ExtractedSource


def build_evidence_prompt(question: str, sources: list[ExtractedSource]) -> str:
    return f"""
You extract EvidenceCard objects from source text for a research report.
Do not create claims not supported by the source text.
Each EvidenceCard must include a concrete claim, source_url, source_title, supporting_snippet, content_type, source_type, source_quality_score, evidence_reliability, and confidence.
If the source text is weak or only a search snippet, use low reliability.

Return only JSON:
{{"evidence_cards":[{{"id":"e1","subquestion_id":"q1","claim":"...","source_url":"...","source_title":"...","supporting_snippet":"...","content_type":"extracted_content","source_type":"industry_report","source_quality_score":85,"evidence_reliability":"high","confidence":"high"}}]}}

Question:
{question}

Sources:
{[source.model_dump() for source in sources]}
""".strip()
```

- [ ] **Step 5: 实现 prepare_evidence 节点**

Create `src/deepresearch/nodes/prepare_evidence.py` with:

- `EvidenceResponse(BaseModel)`
- `_dedupe_results(results)` using `normalize_url`
- `_apply_quality(results)` using `classify_source`
- `_select_by_subquestion(results, max_sources_per_subquestion)`
- `_fallback_extracted_sources(selected)`
- `make_prepare_evidence_node(search_client, llm, max_sources_per_subquestion)`

Required behavior:

```python
quality = classify_source(result)
result.source_type = quality.source_type
result.source_quality_score = quality.score
result.source_quality_reason = quality.reason
```

Extract selected URLs per subquestion. If extract raises, create fallback `ExtractedSource` from `SearchResult.content` with `content_type` represented later by EvidenceCard as `search_content` and low reliability.

Parse LLM JSON into `EvidenceCard` list. Validate card URLs are from selected/fallback sources; if invalid, record error and drop invalid cards.

Compute metrics:

```python
evidence_metrics = {
    "raw_search_results": len(raw),
    "deduped_sources": len(deduped),
    "duplicates_removed": len(raw) - len(deduped),
    "extracted_sources": len(extracted_sources),
    "evidence_cards": len(evidence_cards),
    "source_quality": {type: count},
    "evidence_reliability": {level: count},
}
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
uv run pytest tests/test_prepare_evidence_node.py tests/test_evidence_prompt.py -v
```

Expected: pass.

- [ ] **Step 7: 提交**

```bash
git add src/deepresearch/nodes/prepare_evidence.py src/deepresearch/prompts/evidence.py tests/test_prepare_evidence_node.py tests/test_evidence_prompt.py
git commit -m "feat: prepare extracted evidence cards"
```

---

### Task 8: Graph 接入 prepare_evidence

**Files:**
- Modify: `src/deepresearch/graph.py`
- Modify: `src/deepresearch/cli.py`
- Modify: `tests/test_graph_structure.py`
- Modify: `tests/test_integration_offline.py`

- [ ] **Step 1: 更新 graph tests**

Modify expected `NODE_SEQUENCE` in `tests/test_graph_structure.py`:

```python
assert NODE_SEQUENCE == [
    "plan_research",
    "search_web",
    "prepare_evidence",
    "synthesize_notes",
    "write_report",
    "review_report",
    "save_report",
]
```

Update compile test to pass `prepare_evidence=lambda state: {**state, "evidence_cards": []}`.

- [ ] **Step 2: 更新 integration fake workflow**

Modify `tests/test_integration_offline.py` to include fake prepare node or real node depending complexity. Simpler:

```python
prepare_evidence=lambda state: {**state, "evidence_cards": [EvidenceCard(...)] , "evidence_metrics": {...}}
```

- [ ] **Step 3: Run tests to fail**

```bash
uv run pytest tests/test_graph_structure.py tests/test_integration_offline.py -v
```

Expected: graph function missing prepare_evidence parameter.

- [ ] **Step 4: Update graph.py**

Add `prepare_evidence` to `NODE_SEQUENCE`, `build_research_graph`, `create_research_app`, and edges:

```python
graph.add_edge("search_web", "prepare_evidence")
graph.add_edge("prepare_evidence", "synthesize_notes")
```

- [ ] **Step 5: Update CLI**

Import `make_prepare_evidence_node` and wire it:

```python
prepare_evidence = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)
prepare_evidence=_with_progress("[3/7] Preparing evidence...", prepare_evidence)
```

Update labels to `[1/7]` ... `[7/7]`.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_graph_structure.py tests/test_integration_offline.py tests/test_cli.py -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/deepresearch/graph.py src/deepresearch/cli.py tests/test_graph_structure.py tests/test_integration_offline.py tests/test_cli.py
git commit -m "feat: add prepare evidence graph node"
```

---

### Task 9: synthesize_notes 使用 EvidenceCard

**Files:**
- Modify: `src/deepresearch/prompts/synthesizing.py`
- Modify: `src/deepresearch/nodes/synthesizing.py`
- Modify: `tests/test_synthesizing_node.py`

- [ ] **Step 1: 添加测试：synthesize uses evidence_cards**

Append to `tests/test_synthesizing_node.py`:

```python
def test_synthesize_notes_uses_evidence_cards():
    llm = FakeLLMClient([
        '{"notes":[{"subquestion_id":"q1","key_findings":["RAG remains important."],"source_urls":["https://example.com/a"],"confidence":"high"}]}'
    ])
    node = make_synthesize_notes_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", search_queries=["AI search"], rationale="Background")],
        "search_results": [],
        "evidence_cards": [EvidenceCard(
            id="e1",
            subquestion_id="q1",
            claim="RAG remains important.",
            source_url="https://example.com/a",
            source_title="A",
            supporting_snippet="RAG remains important.",
            content_type="extracted_content",
            source_type="industry_report",
            source_quality_score=85,
            evidence_reliability="high",
            confidence="high",
        )],
        "errors": [],
    })

    assert result["notes"][0].source_urls == ["https://example.com/a"]
    assert "EvidenceCard" in llm.prompts[0] or "evidence_cards" in llm.prompts[0]
```

- [ ] **Step 2: Run tests to fail**

```bash
uv run pytest tests/test_synthesizing_node.py -v
```

Expected: prompt still based on search_results.

- [ ] **Step 3: Update synthesizing prompt**

Modify `build_synthesizing_prompt` to accept `evidence_cards` instead of results, or add optional parameter. It must include evidence cards and instruction:

```text
Only summarize claims present in EvidenceCards. Do not introduce facts not supported by EvidenceCards.
Low reliability evidence cannot support high confidence findings.
```

- [ ] **Step 4: Update synthesizing node**

Use `state.get("evidence_cards", [])`. If no evidence cards, fallback notes low confidence.

Validate note source_urls against EvidenceCard source_url set, not search_results.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_synthesizing_node.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/deepresearch/prompts/synthesizing.py src/deepresearch/nodes/synthesizing.py tests/test_synthesizing_node.py
git commit -m "feat: synthesize notes from evidence cards"
```

---

### Task 10: write_report 只允许 EvidenceCard URLs

**Files:**
- Modify: `src/deepresearch/prompts/writing.py`
- Modify: `src/deepresearch/nodes/writing.py`
- Modify: `tests/test_writing_node.py`
- Modify: `tests/test_writing_prompt.py`

- [ ] **Step 1: Add test that non-EvidenceCard search result URL is rejected**

Append to `tests/test_writing_node.py`:

```python
def test_write_report_only_allows_evidence_card_urls():
    llm = FakeLLMClient([
        "# AI Search\n\nClaim.[1]\n\n## Sources\n\n[1] https://not-evidence.example",
        "# AI Search\n\nClaim.[1]\n\n## Sources\n\n[1] https://not-evidence.example",
    ])
    node = make_write_report_node(llm)
    state = _state()
    state["search_results"].append(SearchResult(subquestion_id="q1", title="Search only", url="https://not-evidence.example", content="Search only"))
    state["evidence_cards"] = [EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="Claim.",
        source_url="https://example.com",
        source_title="Source",
        supporting_snippet="Claim.",
        content_type="extracted_content",
        source_type="industry_report",
        source_quality_score=85,
        evidence_reliability="high",
        confidence="high",
    )]

    result = node(state)

    assert result["report_status"] == "failed_validation"
    assert result["validation_failures"][0]["reason"] == "invalid_source_urls"
```

- [ ] **Step 2: Run tests to fail**

```bash
uv run pytest tests/test_writing_node.py -v
```

Expected: fail because allowed URLs currently come from search_results.

- [ ] **Step 3: Update writing node allowed URLs**

In `write_report`, compute:

```python
evidence_cards = state.get("evidence_cards", [])
allowed_urls = {card.source_url for card in evidence_cards} or {result.url for result in results}
```

Use fallback to search_results only for backward compatibility in tests/old flows.

- [ ] **Step 4: Update writing prompt**

Pass evidence cards to prompt or include them in notes context. Update prompt test to assert `EvidenceCards` appears when provided.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_writing_node.py tests/test_writing_prompt.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/deepresearch/prompts/writing.py src/deepresearch/nodes/writing.py tests/test_writing_node.py tests/test_writing_prompt.py
git commit -m "feat: restrict report sources to evidence cards"
```

---

### Task 11: verbose 显示 evidence metrics

**Files:**
- Modify: `src/deepresearch/verbose.py`
- Modify: `tests/test_verbose.py`

- [ ] **Step 1: Add verbose metrics test**

Append to `tests/test_verbose.py`:

```python
def test_format_verbose_summary_includes_evidence_metrics():
    state = {
        "evidence_metrics": {
            "subquestions": 2,
            "total_queries": 5,
            "raw_search_results": 12,
            "deduped_sources": 8,
            "duplicates_removed": 4,
            "extracted_sources": 5,
            "evidence_cards": 9,
            "source_quality": {"official": 1, "industry_report": 2, "seo_content": 1},
            "evidence_reliability": {"high": 3, "medium": 4, "low": 2},
        }
    }

    summary = format_verbose_summary(state)

    assert "Search coverage:" in summary
    assert "raw search results: 12" in summary
    assert "deduped sources: 8" in summary
    assert "Source quality:" in summary
    assert "industry_report: 2" in summary
    assert "Evidence reliability:" in summary
    assert "high: 3" in summary
```

- [ ] **Step 2: Run tests to fail**

```bash
uv run pytest tests/test_verbose.py -v
```

Expected: fail.

- [ ] **Step 3: Implement verbose sections**

In `src/deepresearch/verbose.py`, add sections for evidence_metrics after Search results or before Review.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_verbose.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/verbose.py tests/test_verbose.py
git commit -m "feat: show evidence metrics in verbose output"
```

---

### Task 12: README 更新

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Add section:

```markdown
## Evidence pipeline

v0.2 uses an extract-based evidence pipeline:

```text
search → source scoring → selected extract → EvidenceCard → notes → report
```

Search results are treated as candidate sources. The tool does not assume Tavily `content` is full source text. Selected sources are extracted with Tavily `extract()` when possible, and evidence cards bind each claim to a source URL and supporting snippet.

Verbose mode reports search coverage, source quality distribution, and evidence reliability distribution.
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest -v
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document evidence pipeline"
```

---

### Task 13: Final offline verification

**Files:**
- No code changes unless fixes required.

- [ ] **Step 1: Run full tests**

```bash
uv run pytest -v
```

Expected: all pass.

- [ ] **Step 2: Run safe CLI checks**

```bash
uv run deepresearch --help
```

Expected options include existing options.

```powershell
$env:DEEPSEEK_API_KEY=$null; $env:TAVILY_API_KEY=$null; $env:PYTHON_DOTENV_DISABLED='1'; uv run deepresearch "AI search"
```

Expected non-zero missing key error.

- [ ] **Step 3: Check git status**

```bash
git status --short
```

Expected clean.

---

### Task 14: Online acceptance and report

**Files:**
- Create: `docs/superpowers/reports/2026-06-11-v0.2-online-acceptance-report.md`

- [ ] **Step 1: Get explicit authorization before API calls**

Run only after user confirms external API use.

- [ ] **Step 2: Run online commands**

```bash
uv run deepresearch "AI 搜索引擎的发展趋势" --verbose
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --verbose
uv run deepresearch "新能源汽车固态电池商业化进展" --verbose
```

- [ ] **Step 3: Record metrics**

For each success report record:

```text
result
output_path
EvidenceCard count
distinct source count
high/medium reliability ratio
review score
review passed
```

- [ ] **Step 4: Determine acceptance**

Pass if:

```text
at least 2/3 success
EvidenceCard >= 5 for each success
unique sources >= 3 for each success
high/medium reliability >= 60% for each success
review score >= 85 for each success
```

- [ ] **Step 5: Write report and commit**

```bash
git add docs/superpowers/reports/2026-06-11-v0.2-online-acceptance-report.md
git commit -m "docs: add v0.2 online acceptance report"
```

---

## Self-Review

Spec coverage:

- Multi-query planning: Tasks 1-3.
- Search executes all queries: Task 3.
- URL dedupe: Tasks 5 and 7.
- Source quality scoring: Task 4 and Task 7.
- Tavily extract: Task 6 and Task 7.
- EvidenceCard generation: Task 7.
- Graph prepare_evidence node: Task 8.
- Notes from EvidenceCards: Task 9.
- Report only cites EvidenceCard URLs: Task 10.
- Verbose evidence metrics: Task 11.
- README: Task 12.
- Offline verification: Task 13.
- Online acceptance: Task 14.

Placeholder scan:

- No placeholder tasks remain.
- All new code-facing tasks include concrete tests or implementation instructions.
- Online acceptance is gated by explicit authorization.

Type consistency:

- `SourceType`, `ContentType`, `EvidenceReliability` are defined in `state.py` and reused by source quality, extract, EvidenceCard, and verbose.
- `EvidenceCard.source_url` is the source of allowed report URLs.
- `evidence_metrics` is a dict consumed by verbose.
