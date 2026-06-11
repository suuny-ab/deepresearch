# Tavily 能力调研报告

日期：2026-06-11

## 1. 调研目的

本报告用于支撑 Deep Research Agent v0.2 的设计。

v0.2 计划围绕以下方向提升研究报告质量：

```text
搜索覆盖 + 来源可信度 + EvidenceCard 证据绑定
```

在设计 v0.2 前，需要先搞清楚当前搜索引擎 Tavily 的能力和限制，尤其是：

- `search()` 返回的 `content` 是什么
- 是否能获取网页原文或更完整内容
- `raw_content` 如何启用
- `extract()` 是否适合作为 EvidenceCard 的证据来源
- `score` 是否可以当作来源可信度
- 搜索深度、domain filter、topic 等参数如何影响结果
- 成本和延迟的大致影响

## 2. 调研方法

本次调研使用两种方法：

1. **本地 SDK 源码调研**
   - 读取本地 `.venv` 中安装的 `tavily-python` 源码
   - 不调用外部 API

2. **最小真实 API 探针**
   - 使用真实 Tavily API
   - 控制请求规模：`max_results=1`
   - 只打印字段名、长度、usage、response_time
   - 不打印大段网页正文

由于 Claude WebFetch 工具当前无法正常抓取公开网页，本次没有依赖 WebFetch。

## 3. SDK 基本信息

本地安装包：

```text
tavily-python 0.7.25
```

包路径：

```text
.venv/Lib/site-packages/tavily/
```

包说明：

```text
Python wrapper for the Tavily API
```

主页：

```text
https://github.com/tavily-ai/tavily-python
```

## 4. TavilyClient.search 参数能力

本地 SDK 显示 `TavilyClient.search()` 支持以下参数：

```python
TavilyClient.search(
    query: str,
    search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = None,
    topic: Literal["general", "news", "finance"] = None,
    time_range: Literal["day", "week", "month", "year"] = None,
    start_date: str = None,
    end_date: str = None,
    days: int = None,
    max_results: int = None,
    include_domains: Sequence[str] = None,
    exclude_domains: Sequence[str] = None,
    include_answer: bool | Literal["basic", "advanced"] = None,
    include_raw_content: bool | Literal["markdown", "text"] = None,
    include_images: bool = None,
    timeout: float = 60,
    country: str = None,
    auto_parameters: bool = None,
    include_favicon: bool = None,
    include_usage: bool = None,
    exact_match: bool = None,
    **kwargs
) -> dict
```

确认支持：

| 能力 | 支持情况 |
|---|---|
| 搜索深度 | `basic`, `advanced`, `fast`, `ultra-fast` |
| 主题 | `general`, `news`, `finance` |
| 时间过滤 | `time_range`, `start_date`, `end_date`, `days` |
| 结果数量 | `max_results` |
| 域名过滤 | `include_domains`, `exclude_domains` |
| 生成式答案 | `include_answer` |
| 原始内容 | `include_raw_content=True/markdown/text` |
| 图片 | `include_images` |
| 国家 | `country` |
| 自动参数 | `auto_parameters` |
| favicon | `include_favicon` |
| usage | `include_usage` |
| 精确匹配 | `exact_match` |

## 5. TavilyClient.extract 参数能力

本地 SDK 显示 `TavilyClient.extract()` 支持：

```python
TavilyClient.extract(
    urls: list[str] | str,
    include_images: bool = None,
    extract_depth: Literal["basic", "advanced"] = None,
    format: Literal["markdown", "text"] = None,
    timeout: float = 30,
    include_favicon: bool = None,
    include_usage: bool = None,
    query: str = None,
    chunks_per_source: int = None,
    **kwargs
) -> dict
```

返回结构至少包含：

```text
results
failed_results
```

结论：

```text
Tavily 不只是搜索工具，也提供对指定 URL 的内容抽取能力。
```

这对 v0.2 的 EvidenceCard 设计非常重要。

## 6. 默认 search 探针结果

命令逻辑：

```python
client.search(
    query="AI search trends",
    max_results=1,
    include_usage=True,
)
```

观察结果：

```text
response_keys:
- answer
- follow_up_questions
- images
- query
- request_id
- response_time
- results
- usage

usage: {'credits': 1}
response_time: 0.66
results_count: 1
```

第一条 result 字段：

```text
content
raw_content
score
title
url
```

字段观察：

```text
content length: 890
raw_content: None
score: 0.90289277
url: https://www.seo.com/blog/ai-search-trends
```

结论：

```text
默认 search 返回 content，但 raw_content 为 None。
当前项目使用的 content 不应视为完整网页原文。
```

## 7. include_raw_content 探针结果

命令逻辑：

```python
client.search(
    query="AI search trends",
    max_results=1,
    include_raw_content="markdown",
    include_answer=True,
    include_usage=True,
)
```

观察结果：

```text
answer length: 242
content length: 890
raw_content length: 13805
usage: {'credits': 1}
response_time: 2.84
```

另一次测试：

```python
include_raw_content="text"
```

观察结果：

```text
raw_content length: 10203
usage: {'credits': 1}
response_time: 2.28
```

结论：

```text
include_raw_content 可以让 search 返回 raw_content。
markdown 比 text 更长，保留更多结构。
```

但 raw_content 会显著增加返回体积，并可能增加响应时间。

## 8. extract 探针结果

使用默认 search 返回的 URL：

```text
https://www.seo.com/blog/ai-search-trends
```

命令逻辑：

```python
client.extract(
    url,
    format="markdown",
    extract_depth="basic",
    include_usage=True,
)
```

观察结果：

```text
response_keys:
- failed_results
- request_id
- response_time
- results
- usage

usage: {'credits': 0}
response_time: 0.01
results_count: 1
failed_count: 0
```

第一条 result 字段：

```text
images
raw_content
title
url
```

观察：

```text
raw_content length: 13805
```

测试组合：

| extract_depth | format | credits | raw_content length |
|---|---|---:|---:|
| basic | markdown | 0 | 13805 |
| basic | text | 0 | 10203 |
| advanced | markdown | 0 | 13805 |
| advanced | text | 0 | 10203 |

结论：

```text
extract 能对指定 URL 获取 raw_content。
本次样本中 extract 返回的 raw_content 与 search(include_raw_content) 一致。
```

注意：本次 `credits=0` 是单次样本结果，不应假设 extract 永远免费。

## 9. chunks_per_source 探针结果

测试：

```python
client.extract(
    url,
    extract_depth="advanced",
    format="markdown",
    chunks_per_source=1,
    include_usage=True,
)

client.extract(
    url,
    extract_depth="advanced",
    format="markdown",
    chunks_per_source=3,
    include_usage=True,
)
```

观察：

```text
raw_content length: 13805
```

结论：

```text
在本样本中，chunks_per_source 没有产生可见差异。
```

可能只在带 `query` 的 extract 或特定场景下生效，需要后续再测。

## 10. search_depth 探针结果

测试：

```python
search_depth="basic"
search_depth="advanced"
search_depth="fast"
search_depth="ultra-fast"
```

观察结果：

| search_depth | credits | response_time | 返回来源 | content length |
|---|---:|---:|---|---:|
| basic | 1 | 0.0s | seo.com | 890 |
| advanced | 2 | 1.61s | semrush.com | 2315 |
| fast | 1 | 0.26s | scrunch.com | 1386 |
| ultra-fast | 1 | 0.1s | scrunch.com | 2323 |

结论：

```text
advanced search 消耗更多 credits，并可能返回不同来源和更丰富内容。
```

v0.2 不宜默认所有 query 都使用 `advanced`，可考虑按需使用。

## 11. Domain include/exclude 探针结果

测试：

```python
include_domains=["seo.com"]
exclude_domains=["seo.com"]
```

结果：

```text
include_domains=seo.com → 返回 seo.com
exclude_domains=seo.com → 返回 semrush.com
```

结论：

```text
include_domains / exclude_domains 有效。
```

这对 v0.2 来源质量策略有价值。

## 12. topic 探针结果

测试：

```python
topic="general"
topic="news"
topic="finance"
```

结果：

| topic | 返回来源 | published_date |
|---|---|---|
| general | seo.com | 无 |
| news | Newsweek | 有 |
| finance | Yahoo Finance | 无 |

`topic="news"` 返回：

```text
published_date: Fri, 05 Jun 2026 14:35:00 GMT
```

结论：

```text
topic="news" 对新闻/时效信息有价值，并可能返回 published_date。
```

## 13. score 的含义与限制

探针中 `score=0.90` 的结果来自：

```text
https://www.seo.com/blog/ai-search-trends
```

这说明：

```text
Tavily score 更适合作为搜索相关性信号，而不是来源可信度信号。
```

不能把高 score 等同于高权威性。

v0.2 应区分：

```python
search_relevance_score = Tavily score
source_quality_score = 自定义来源可信度评分
```

## 14. include_answer 的定位

`include_answer=True` 返回：

```text
answer length: 242
```

这是 Tavily 的生成式答案或摘要。

建议：

```text
include_answer 可以作为调试/参考摘要，但不应作为 EvidenceCard 的证据来源。
```

EvidenceCard 应优先基于：

```text
extract raw_content
```

而不是 Tavily answer。

## 15. 对 v0.2 的设计建议

### 15.1 推荐流程

v0.2 建议采用：

```text
Search → Source Scoring → Extract → EvidenceCard → Notes → Report
```

而不是直接：

```text
SearchResult.content → Notes → Report
```

### 15.2 推荐搜索策略

默认：

```python
client.search(
    query=query,
    search_depth="basic",
    max_results=5,
    include_raw_content=False,
    include_answer=False,
    include_usage=True,
)
```

原因：

- 快
- credits 低
- 用于发现候选来源即可

如质量不足，可对部分 query 使用：

```python
search_depth="advanced"
```

### 15.3 推荐抽取策略

对筛选后的 URL 使用：

```python
client.extract(
    urls=selected_urls,
    extract_depth="basic",
    format="markdown",
    include_usage=True,
)
```

如果 markdown 噪声过多，再考虑：

```python
format="text"
```

### 15.4 推荐 EvidenceCard 来源

优先：

```text
extract.raw_content
```

fallback：

```text
search.content
```

但 fallback 必须标注低可靠性。

## 16. 建议数据结构

### 16.1 SearchResult 扩展

```python
class SearchResult(BaseModel):
    subquestion_id: str
    query: str
    title: str
    url: str
    content: str
    raw_content: str | None = None
    content_type: Literal["search_content", "raw_content", "extracted_content"] = "search_content"
    score: float | None = None
    published_date: str | None = None
    source_type: SourceType = "unknown"
    source_quality_score: int = 50
```

### 16.2 ExtractedSource

```python
class ExtractedSource(BaseModel):
    url: str
    title: str
    raw_content: str
    extract_depth: Literal["basic", "advanced"]
    format: Literal["markdown", "text"]
    source_type: SourceType
    source_quality_score: int
```

### 16.3 EvidenceCard

```python
class EvidenceCard(BaseModel):
    id: str
    subquestion_id: str
    claim: str
    source_url: str
    source_title: str
    supporting_snippet: str
    content_type: Literal["search_content", "extracted_content"]
    source_type: SourceType
    source_quality_score: int
    evidence_reliability: Literal["low", "medium", "high"]
    confidence: Literal["low", "medium", "high"]
```

## 17. 推荐 v0.2 范围修正

原本设想：

```text
搜索覆盖 + 来源质量 + EvidenceCard
```

调研后建议修正为：

```text
搜索覆盖 + 来源可信度 + Extract-based EvidenceCard
```

原因：

- search `content` 不是完整原文
- raw_content 需要显式获取
- extract API 更适合作为 EvidenceCard 的证据来源
- score 只能作为相关性，不能作为可信度

## 18. 仍需进一步确认的问题

本次探针已经足够支持 v0.2 设计，但还有一些细节可在实现前继续验证：

1. 批量 extract 多 URL 的返回形态。
2. extract 对失败 URL 的 `failed_results` 结构。
3. `extract(query=..., chunks_per_source=...)` 的实际效果。
4. 中文 query 下 raw_content 的质量。
5. 不同来源类型下 extract 成功率。
6. 大批量请求时的 credits 和延迟分布。

这些不阻塞 v0.2 设计，但会影响默认参数和成本控制。

## 19. 最终结论

Tavily 能力调研结论：

```text
默认 search.content 不是完整原文，不应直接作为高可靠证据。
Tavily 支持 include_raw_content，也支持 extract(url) 获取 raw_content。
extract 更适合作为 EvidenceCard 的证据来源。
search score 是相关性信号，不是来源可信度。
include_domains / exclude_domains 可用于来源控制。
topic=news 对时效性资料有价值。
advanced search 更贵，应按需使用。
```

对 v0.2 的建议：

```text
采用 search → source quality scoring → selected extract → EvidenceCard 的流程。
```
