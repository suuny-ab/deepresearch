# Deep Research Agent v0.2 设计规格：Extract-based Evidence Pipeline

日期：2026-06-11

## 1. 背景

Deep Research Agent v0.1.2 已经完成以下能力：

- 固定 LangGraph 研究流程
- Tavily 搜索
- DeepSeek 规划、写作、审核
- 严格 `[n]` 编号引用
- citation validator
- 一次自动重写
- review 只审核最终报告
- 在线 3 题验收通过

v0.1.2 解决了“能否稳定生成带合规引用的报告”的问题。

下一步 v0.2 的目标是提升研究报告质量，重点不是“能不能生成”，而是：

```text
生成的报告是否基于更全面、更可靠、更可追溯的证据。
```

本轮 Tavily 能力调研已经确认：

- 默认 `search().results[].content` 不是完整网页原文。
- 默认 `search()` 返回 `raw_content=None`。
- Tavily 支持 `include_raw_content="markdown" | "text"`。
- Tavily 支持 `extract(urls, format="markdown" | "text")` 获取 `raw_content`。
- Tavily `score` 更适合作为搜索相关性，不应当作来源可信度。
- `include_domains` / `exclude_domains` 有效。
- `topic="news"` 对时效信息有价值，并可能返回 `published_date`。

因此，v0.2 应从当前的：

```text
SearchResult.content → Notes → Report
```

升级为：

```text
Search → Source Scoring → Extract → EvidenceCard → Notes → Report
```

## 2. 版本目标

v0.2 的目标是实现：

```text
Extract-based Evidence Pipeline
```

具体目标：

1. 提升搜索覆盖范围。
2. 识别和标注来源可信度。
3. 对筛选后的高价值 URL 执行 Tavily extract。
4. 基于 extracted content 构建 EvidenceCard。
5. 让 notes 和 report 基于 EvidenceCard，而不是直接基于搜索摘要。
6. 在 verbose 中展示搜索覆盖、来源质量、证据可靠性等指标。
7. 在线验收不只看报告是否成功，还看 EvidenceCard 数量、来源数量、可靠性占比和 review score。

## 3. 非目标

v0.2 不做：

- claim-level validation。
- review 后自动补充搜索。
- 多 Agent。
- 并发搜索。
- trace JSON。
- PDF/DOCX 导出。
- Web UI。
- 搜索结果长期缓存。
- 来源真实性人工验证。

这些可作为 v0.3 或后续版本方向。

## 4. 总体设计

v0.2 采用单节点方案，在主图中新增一个节点：

```text
plan_research
→ search_web
→ prepare_evidence
→ synthesize_notes
→ write_report
→ review_report
→ save_report
```

`prepare_evidence` 内部完成：

```text
URL 去重
→ 来源可信度评分
→ 选择高价值来源
→ Tavily extract
→ EvidenceCard 生成
```

选择单节点方案的原因：

- 对现有主流程影响小。
- 避免一次引入过多 LangGraph 节点。
- 便于先验证证据管线价值。
- 后续如逻辑变复杂，可以再拆成多个节点。

## 5. 搜索覆盖设计

### 5.1 当前问题

当前每个子问题只有一个搜索 query：

```python
search_query: str
```

这会导致：

- 覆盖角度单一。
- 中文/英文资料不平衡。
- 报告、白皮书、新闻、技术文档等来源类型覆盖不足。
- 单个 query 质量差会影响整个子问题。

### 5.2 v0.2 设计

将 `SubQuestion` 扩展为支持多个 query：

```python
class SubQuestion(BaseModel):
    id: str
    question: str
    search_query: str
    search_queries: list[str]
    rationale: str
```

保留 `search_query` 是为了兼容旧代码；`search_queries` 是 v0.2 的主字段。

规则：

- 每个子问题至少 2 个 query。
- 每个子问题最多 3 个 query。
- query 应覆盖不同角度。

推荐 query 类型：

1. 中文通用 query
2. 英文通用 query
3. 报告/研究型 query

示例：

```json
{
  "id": "q1",
  "question": "AI 搜索引擎在技术层面有哪些趋势？",
  "search_queries": [
    "AI 搜索 技术趋势 RAG 多模态 Agent",
    "AI search engine technology trends RAG multimodal agents 2026",
    "AI search technology report RAG agent multimodal"
  ],
  "rationale": "覆盖中文、英文和研究报告来源"
}
```

### 5.3 成本控制

默认建议：

```text
每个子问题最多 3 个 query
每个 query max_results=3
总 search results 上限 50
```

这些限制可后续暴露为 CLI 参数，但 v0.2 可以先作为配置默认值。

## 6. Tavily Search 策略

### 6.1 默认 search 参数

调研结果显示，默认 search 快且便宜，适合候选来源发现。

推荐默认：

```python
client.search(
    query=query,
    search_depth="basic",
    max_results=3,
    include_raw_content=False,
    include_answer=False,
    include_usage=True,
)
```

原因：

- `content` 足够用于初筛。
- 不拉取 raw_content，减少返回体积。
- `usage` 可用于记录成本。

### 6.2 advanced search 使用策略

`search_depth="advanced"` 在探针中消耗更多 credits：

```text
basic: 1 credit
advanced: 2 credits
```

v0.2 不默认对所有 query 使用 advanced。

可选策略：

- 当 basic 返回结果不足时，重试 advanced。
- 当 query 类型是报告/研究型 query 时，使用 advanced。
- 后续通过 CLI 或配置暴露。

v0.2 初版建议：

```text
全部默认 basic，保留 search_depth 配置点。
```

### 6.3 domain filter

Tavily 支持：

```python
include_domains
exclude_domains
```

v0.2 初版不强制默认过滤，但 `SearchClient` 应支持把这些参数透传，为后续来源策略做准备。

## 7. URL 去重

### 7.1 目标

同一个 URL 不应重复进入 evidence pipeline。

### 7.2 规则

- 去重 key 使用规范化 URL：忽略 `www.`、末尾 `/`、常见 tracking query 参数。
- 同 URL 多次出现时，只保留一个 `SearchResult`。
- 保留该 URL 来自哪些 query 的元数据。

### 7.3 数据建议

可在 `SearchResult` 中增加：

```python
query: str
```

也可在 prepare 阶段生成：

```python
source_queries: list[str]
```

v0.2 初版可以简单保留第一次出现的 query，同时在 verbose 中报告重复数量。

## 8. 来源可信度设计

### 8.1 SourceType

新增来源类型：

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
```

### 8.2 SourceQuality

新增：

```python
class SourceQuality(BaseModel):
    source_type: SourceType
    score: int
    reason: str
```

`score` 范围：0-100。

### 8.3 初始评分规则

| 类型 | 默认分数 |
|---|---:|
| official | 95 |
| academic | 90 |
| industry_report | 85 |
| reputable_media | 75 |
| company_blog | 65 |
| unknown | 50 |
| blog | 45 |
| forum | 35 |
| seo_content | 20 |

### 8.4 评分信号

初版使用启发式规则，不使用 LLM 打分。

信号包括：

- 域名后缀
- 已知官方/学术/媒体域名
- URL path
- title 关键词
- 是否 PDF
- 是否包含 report / research / whitepaper / 报告 / 白皮书
- 是否明显 SEO 域名或内容农场

### 8.5 注意事项

Tavily `score` 不等于来源质量。

因此要区分：

```python
search_relevance_score: float | None
source_quality_score: int
```

## 9. Extract 策略

### 9.1 为什么需要 extract

调研确认：

```text
默认 search.content 不是完整原文。
```

EvidenceCard 不应直接依赖 search.content 作为高可靠证据。

### 9.2 v0.2 Extract 策略

流程：

```text
SearchResult candidates
→ source quality scoring
→ select top sources
→ Tavily extract
→ ExtractedSource
```

### 9.3 选择哪些 URL 进行 extract

初版建议：

- 每个子问题最多 extract 3 个 URL。
- 优先选择 `source_quality_score` 高的来源。
- 同时保留来源多样性，避免同域名过多。

### 9.4 extract 参数

推荐默认：

```python
client.extract(
    urls=selected_urls,
    extract_depth="basic",
    format="markdown",
    include_usage=True,
)
```

原因：

- markdown 保留结构。
- basic 在探针样本中已经能得到完整 raw_content。
- advanced 可作为后续优化。

### 9.5 extract 失败处理

如果 extract 失败：

- 不终止整个流程。
- 记录错误。
- fallback 到 `SearchResult.content`。
- 标记 `content_type="search_content"`。
- `evidence_reliability="low"`。

## 10. 数据模型设计

### 10.1 SearchResult 扩展

```python
class SearchResult(BaseModel):
    subquestion_id: str
    query: str | None = None
    title: str
    url: str
    content: str
    raw_content: str | None = None
    content_type: Literal["search_content", "raw_content", "extracted_content"] = "search_content"
    score: float | None = None
    published_date: str | None = None
    source_type: SourceType = "unknown"
    source_quality_score: int = 50
    source_quality_reason: str = ""
```

### 10.2 ExtractedSource

```python
class ExtractedSource(BaseModel):
    subquestion_id: str
    url: str
    title: str
    raw_content: str
    extract_depth: Literal["basic", "advanced"]
    format: Literal["markdown", "text"]
    source_type: SourceType
    source_quality_score: int
    source_quality_reason: str
```

### 10.3 EvidenceCard

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

### 10.4 ResearchState 扩展

```python
class ResearchState(TypedDict, total=False):
    ...
    extracted_sources: list[ExtractedSource]
    evidence_cards: list[EvidenceCard]
    evidence_metrics: dict[str, Any]
```

## 11. prepare_evidence 节点设计

新增节点：

```python
make_prepare_evidence_node(extract_client, max_sources_per_subquestion: int)
```

输入：

```python
search_results
subquestions
```

输出：

```python
search_results   # 带 source quality
extracted_sources
evidence_cards
evidence_metrics
errors
```

内部步骤：

```text
1. URL 去重
2. source quality scoring
3. 每个子问题选择 top sources
4. 调用 extract
5. extract 失败 fallback 到 search.content
6. 调用 LLM 或规则抽取 EvidenceCard
7. 计算 evidence_metrics
```

v0.2 初版可以把 EvidenceCard 生成作为 LLM 节点逻辑，也可以在 `prepare_evidence` 中调用 LLM。

推荐：

```text
prepare_evidence 负责准备 extracted sources；
synthesize_notes 负责从 extracted sources 生成 evidence cards + notes。
```

但如果要保持节点数少，也可以让 prepare_evidence 同时生成 EvidenceCard。

本次设计采用：

```text
prepare_evidence 生成 EvidenceCard。
```

原因：v0.2 的核心就是 evidence pipeline，集中在一个节点便于验收。

## 12. synthesize_notes 改造

当前：

```text
search_results → ResearchNote
```

v0.2：

```text
evidence_cards → ResearchNote
```

规则：

- notes 只能总结 EvidenceCard 中的 claim。
- 如果某个子问题没有 EvidenceCard，生成低置信 note 或记录错误。
- 低 reliability evidence 不能支撑 high confidence note。

## 13. write_report 改造

`write_report` 的 allowed URLs 应来自：

```text
EvidenceCard.source_url
```

而不是全部 search results。

规则：

- 未进入 EvidenceCard 的 URL 不能出现在最终 Sources。
- 报告关键结论必须引用 EvidenceCard 对应来源。
- 继续使用 v0.1.2 的严格 `[n]` citation validator。
- 继续保留一次自动重写。

## 14. verbose 输出

v0.2 `--verbose` 应新增：

```text
Search coverage:
- subquestions: 5
- total queries: 15
- raw search results: 45
- deduped sources: 31
- duplicates removed: 14
- extracted sources: 12
- evidence cards: 28

Source quality:
- official: 2
- academic: 1
- industry_report: 4
- reputable_media: 5
- company_blog: 3
- blog: 8
- forum: 2
- seo_content: 2
- unknown: 4

Evidence reliability:
- high: 8
- medium: 14
- low: 6
```

## 15. 验收标准

v0.2 通过条件：

### 15.1 离线工程验收

1. 离线测试全部通过。
2. Graph 包含 `prepare_evidence`，位置在 `search_web` 和 `synthesize_notes` 之间。
3. 每个子问题支持 2-3 个 search queries。
4. `search_web` 执行所有 search queries，并记录 query。
5. `prepare_evidence` 对 URL 去重。
6. 每个 source 有 `source_type`、`source_quality_score`、`source_quality_reason`。
7. 选中来源会调用 Tavily extract。
8. extract 失败 fallback 到 search.content，并标记 low reliability。
9. 生成 EvidenceCard，包含 claim、source_url、supporting_snippet、reliability、confidence。
10. `synthesize_notes` 使用 evidence_cards。
11. `write_report` 只引用 EvidenceCard source URLs。
12. `--verbose` 显示搜索覆盖、来源质量、证据可靠性分布。
13. 默认测试不调用外部 API。

### 15.2 在线验收

使用 3 个问题：

```text
1. AI 搜索引擎的发展趋势
2. LangGraph 和 CrewAI 的适用场景
3. 新能源汽车固态电池商业化进展
```

通过标准：

```text
至少 2/3 成功。
```

每篇成功报告还必须满足：

```text
EvidenceCard >= 5
不同来源 >= 3
高/中 reliability EvidenceCard 占比 >= 60%
Review score >= 85
```

## 16. 不纳入 v0.2 的事项

- claim-level validation
- review 后补充搜索
- 多 Agent
- 并发搜索
- trace JSON
- PDF/DOCX
- Web UI
- 长期缓存

## 17. 风险与权衡

### 17.1 成本增加

多 query 和 extract 会增加 Tavily 调用量。

缓解：

- 限制每个子问题 query 数量。
- 限制每个子问题 extract URL 数量。
- 默认 basic search。
- 记录 usage。

### 17.2 Token 增加

raw_content 可能很长。

缓解：

- EvidenceCard 抽取时只传入必要内容片段或截断内容。
- 不把全部 raw_content 直接传给 writer。
- writer 只看 EvidenceCard。

### 17.3 来源评分误判

启发式 source scoring 可能误判。

缓解：

- 保留 source_quality_reason。
- verbose 输出来源分布。
- 后续可引入 LLM/人工规则优化。

## 18. 推荐实现顺序

1. 扩展数据模型。
2. 修改 planning prompt 生成多 query。
3. 修改 search_web 支持多 query 并记录 query。
4. 实现 source_quality.py。
5. 实现 URL 去重。
6. 实现 Tavily extract client 方法。
7. 实现 prepare_evidence 节点。
8. 修改 graph。
9. 修改 synthesize_notes 使用 EvidenceCard。
10. 修改 write_report 只允许 EvidenceCard URLs。
11. 扩展 verbose 输出。
12. 更新 README。
13. 运行离线测试。
14. 运行在线 3 题验收。
15. 写 v0.2 验收报告。

## 19. 开放问题

以下问题不阻塞规格确认，但实施计划中需要细化：

1. EvidenceCard 是由 prepare_evidence 直接生成，还是由 synthesize_notes 生成。
   - 本规格建议 prepare_evidence 生成。
2. raw_content 截断长度。
3. source quality 初始域名规则列表。
4. EvidenceCard 最多数量。
5. 是否暴露 CLI 参数控制 extract 数量。

## 20. 结论

v0.2 应聚焦：

```text
Extract-based Evidence Pipeline
```

核心价值是：

```text
让报告不再直接依赖搜索摘要，而是依赖可追溯、带来源质量和证据片段的 EvidenceCard。
```

这将为后续 v0.3 的 claim-level validation 和 review 后补救打下基础。
