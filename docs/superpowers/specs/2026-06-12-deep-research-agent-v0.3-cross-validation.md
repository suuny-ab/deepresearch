# Deep Research Agent v0.3 设计规格：多源交叉验证证据管线

日期：2026-06-12

## 1. 背景

Deep Research Agent v0.2 实现了 Extract-based Evidence Pipeline：

```text
search → source scoring → selected extract → EvidenceCard → notes → report
```

v0.2 在线验收通过（2/3），但来源质量评分机制存在根本性设计缺陷：

1. **上下文无关**：`classify_source()` 是 `SearchResult → SourceQuality` 的纯函数，不看研究问题。同一个 openai.com 页面，研究"API 用法"时极度可靠，研究"行业竞争格局"时是利益相关方，但两次都被评为 `company_blog(65)`。
2. **域名预判代替内容判断**：不看正文全文就打分，只能依赖 URL 和 title。
3. **硬编码列表不可扩展**：全世界域名不可能枚举，未知域名一律 `unknown(50)`。
4. **来源级预判代言论断层级验证**：Nature 也曾撤稿，个人博客也可以包含准确的技术观察。"可靠性"是论断的属性，不是来源的属性。

参考业界方案（STORM 的 Wikipedia 规则过滤 + 独立 NLI 验证、GPT Researcher 的多来源频率聚合、DeepResearch-Lite 的独立 NLI Verifier、Lutum Veritas 的 Toulmin 论证 + 证据分级），v0.3 将可靠性判断从"入口预判"改为"出口交叉验证"。

## 2. 设计哲学

### 核心转变

```text
旧: 来源权威 → 内容可信（入口预判，硬过滤）
新: 多源交叉验证 + 论断可追溯 → 结论有据可查（出口检验，软加权）
```

### 三个原则

1. **入口不设卡，出口严把关**：搜索阶段不做可靠性预判。搜索引擎的 relevance score + 来源多样性约束就足以决定"读什么"。真正的可靠性判断发生在读到完整内容之后。

2. **信论断不信任来源**：不因为来源"权威"就给它的论断加分，也不因为来源"不可靠"就排除它的论断。验证粒度是 claim 级别，不是 source 级别。

3. **多源交叉验证是第一性原理**：如果三个独立域名来源对同一个事实说了同一件事，它们串通出错的概率极低。这比任何来源评分都可靠——可计算、上下文无关、不需要维护黑名单。

### 什么不变

- LangGraph 7 步流水线结构
- Extract → EvidenceCard → Notes → Report 的主链路
- 严格 `[n]` 引用 + citation validator
- `--verbose` 可观测性

### 什么会消失

- `classify_source()` 硬编码域名评分函数（`source_quality.py` 整个文件删除）
- `SourceType` 枚举（official/academic/blog/seo_content/...）
- `EvidenceReliability` 枚举
- `SearchResult.source_type`、`source_quality_score`、`source_quality_reason` 字段
- `ExtractedSource.source_type`、`source_quality_score`、`source_quality_reason` 字段
- `EvidenceCard.source_type`、`source_quality_score`、`evidence_reliability` 字段
- `ResearchState.extracted_sources` 字段（中间态，不需要在 State 中流转）
- 基于 `source_quality_score` 的 Top-N 选择逻辑
- `ContentType` 中的 `raw_content`（v0.2 未实际使用）

### 什么会新增

- 多样性驱动的来源选择（相关性 + 域名去重 + 语言平衡）
- EvidenceCard 级别的交叉验证信号（`corroboration_level`、`corroborating_sources`）
- 论断级别的多源支撑度替代来源级别的可靠性

## 3. 版本目标

v0.3 的目标是实现：

```text
Multi-source Cross-Validation Evidence Pipeline
```

具体目标：

1. 移除硬编码来源评分，改用搜索引擎相关性分数驱动来源选择。
2. 来源选择引入域名多样性约束，避免同域名重复。
3. 交叉验证作为 EvidenceCard 的核心信号，替代主观可靠性判断。
4. 下游节点（synthesize_notes、write_report）根据支撑度分层处理。
5. verbose 输出展示交叉验证分布，替代来源质量和证据可靠性分布。
6. 离线测试通过，在线验收不低于 v0.2 标准。

## 4. 非目标

v0.3 不做：

- 独立 NLI 验证器（独立 LLM 实例做事实核查）——可作为 v0.4 方向
- 矛盾检测和对比呈现
- claim-level 的自动事实核查
- 多 Agent
- 并发搜索
- 知识图谱 / DAG 表示

## 5. 数据模型变更

### 5.1 删除的内容

```python
# 整个删除
SourceType = Literal[
    "official", "academic", "industry_report", "reputable_media",
    "company_blog", "blog", "forum", "seo_content", "unknown",
]

EvidenceReliability = Literal["low", "medium", "high"]
```

### 5.2 SearchResult：精简

```python
class SearchResult(BaseModel):
    subquestion_id: str
    title: str
    url: str
    content: str
    query: str | None = None
    raw_content: str | None = None
    content_type: ContentType = "search_content"
    score: float | None = None                          # Tavily 相关性
    published_date: str | None = None
    # 删除: source_type, source_quality_score, source_quality_reason
```

### 5.3 ExtractedSource：精简

```python
class ExtractedSource(BaseModel):
    subquestion_id: str
    url: str
    title: str
    raw_content: str
    extract_depth: Literal["basic", "advanced"] = "basic"
    format: Literal["markdown", "text"] = "markdown"
    # 删除: source_type, source_quality_score, source_quality_reason
```

### 5.4 EvidenceCard：交叉验证替代可靠性

```python
class EvidenceCard(BaseModel):
    id: str
    subquestion_id: str
    claim: str
    source_url: str                                    # 主要来源
    source_title: str
    supporting_snippet: str
    content_type: Literal["search_content", "extracted_content"]
    corroboration_level: Literal[
        "single_source",                              # 仅一个来源提到
        "weakly_corroborated",                        # 2 个独立域名来源支持
        "strongly_corroborated",                      # 3+ 个独立域名来源支持
    ]
    corroborating_sources: list[str] = Field(default_factory=list)  # 交叉验证源 URL
    confidence: Literal["low", "medium", "high"]
```

### 5.5 ResearchState：减负

```python
class ResearchState(TypedDict, total=False):
    question: str
    subquestions: list[SubQuestion]
    search_results: list[SearchResult]
    # 删除: extracted_sources — 只在 prepare_evidence 内部使用
    evidence_cards: list[EvidenceCard]
    evidence_metrics: dict[str, Any]
    notes: list[ResearchNote]
    report_markdown: str
    report_status: Literal["success", "failed_validation"]
    rewrite_attempted: bool
    validation_attempts: int
    validation_failures: list[dict[str, Any]]
    review: ReviewResult
    output_path: str
    errors: list[str]
```

### 5.6 evidence_metrics：新统计维度

```python
{
    "raw_search_results": 45,
    "deduped_sources": 31,
    "duplicates_removed": 14,
    "extracted_sources": 12,
    "evidence_cards": 28,
    "corroboration": {
        "strongly_corroborated": 5,                   # 3+ independent domains agree
        "weakly_corroborated": 12,                    # 2 independent domains agree
        "single_source": 11,                          # only one source mentions this
    },
}
```

## 6. 来源选择设计

### 6.1 当前问题

v0.2 使用 `source_quality_score` 排序后取前三，存在：
- 不看相关性，只看域名评分
- 可能三条来源来自同一域名
- 小众优质来源被系统性排除

### 6.2 v0.3 选择逻辑

```text
第一步：按 Tavily relevance score 降序排列
第二步：贪心选择，同一域名只取第一条
第三步（可选）：语言平衡 —— 当子问题有英文 query 时确保至少一个英文域名来源
```

实现：

```python
def select_sources(results: list[SearchResult], max_sources: int,
                   has_english_query: bool = False) -> list[SearchResult]:
    candidates = sorted(results, key=lambda r: r.score or 0, reverse=True)
    selected = []
    selected_domains: set[str] = set()

    for candidate in candidates:
        if len(selected) >= max_sources:
            break
        domain = extract_domain(candidate.url)
        if domain not in selected_domains:
            selected.append(candidate)
            selected_domains.add(domain)

    # 语言平衡：该子问题有英文查询但无英文来源时，补一个
    if has_english_query and not any(is_english_domain(s.url) for s in selected):
        for candidate in candidates:
            if candidate not in selected and is_english_domain(candidate.url):
                # 替换掉相关性最低的非英文来源
                if len(selected) >= max_sources:
                    selected.pop()
                selected.append(candidate)
                break

    return selected
```

### 6.3 与旧逻辑对比

| | v0.2 旧逻辑 | v0.3 新逻辑 |
|---|---|---|
| 排序依据 | 硬编码域名评分 | Tavily 相关性分数 |
| 选择标准 | 纯分数排序 | 分数 + 域名去重 + 语言平衡 |
| 同域名处理 | 可能全选同一域名 | 最多 1 条 |
| 维护成本 | 持续维护域名列表 | 零维护 |
| 判断粒度 | 域名级别预判 | 不预判，只做结构性约束 |

## 7. 交叉验证设计

### 7.1 核心定义

交叉验证回答的问题是："除了这个来源，还有没有**其他独立域名**的来源说了同一件事？"

```text
corroboration_level:
  "single_source"             仅此一个来源提到该论断
  "weakly_corroborated"       2 个独立域名来源支持该论断
  "strongly_corroborated"     3+ 个独立域名来源支持该论断
```

关键约束：**两个同一域名的页面不算独立交叉验证。** 只有不同域名来源的收敛才构成有意义的交叉验证。

### 7.2 LLM 生成 EvidenceCard 时执行交叉验证

在 evidence prompt 中增加交叉验证指令：

```text
For each claim you extract, also check ALL other supplied sources 
(even those from different subquestions that cover related topics).

corroboration_level rules:
- "single_source"      Only this one source mentions this claim
- "weakly_corroborated"      One OTHER independent source (different domain) supports this claim
- "strongly_corroborated"    2+ OTHER independent sources (different domains) support this claim

CRITICAL: Two pages from the SAME domain (e.g., two openai.com pages) 
do NOT count as independent corroboration. Only DIFFERENT domain 
agreement constitutes meaningful cross-validation.

When asserting corroboration, you MUST:
1. Quote the supporting snippet from the corroborating source
2. Verify the corroborating source's domain is different from the primary source
3. Include corroborating source URLs in corroborating_sources

Each source is marked with content_type:
- "extracted_content" — full webpage text was available
- "search_content"   — only a search snippet was available (extract failed)

When assessing corroboration strength:
- Two full-text sources independently stating the same fact → strong signal
- One full text + one snippet → weaker but still valid
- Two snippets → treat as weakly_corroborated at best
- Label the strength honestly; do not inflate weak signals
```

### 7.3 代码层事后校验

LLM 输出 EvidenceCard 后，代码做硬边界检查：

```python
def validate_corroboration(
    card: EvidenceCard,
    extracted_urls: set[str],
    extracted_content_types: dict[str, str],
) -> EvidenceCard:
    # 校验 1: 验证源 URL 必须真实存在于 extracted sources 中
    valid_sources = []
    for url in card.corroborating_sources:
        if normalize_url(url) in extracted_urls:
            valid_sources.append(url)
        # 否则 LLM 编造了不存在的验证源 → 丢弃该验证源
    
    card.corroborating_sources = valid_sources

    # 校验 2: 验证源必须和主来源不同域名
    main_domain = extract_domain(card.source_url)
    distinct_sources = [
        url for url in valid_sources
        if extract_domain(url) != main_domain
    ]
    card.corroborating_sources = distinct_sources

    # 校验 3: strongly_corroborated 要求至少 2 个验证源是 full-text
    if card.corroboration_level == "strongly_corroborated":
        full_text_count = sum(
            1 for url in distinct_sources
            if extracted_content_types.get(url) == "extracted_content"
        )
        if full_text_count < 2:
            card.corroboration_level = "weakly_corroborated"

    # 校验 4: weakly_corroborated 要求至少 1 个有效验证源
    if card.corroboration_level == "weakly_corroborated" and not distinct_sources:
        card.corroboration_level = "single_source"

    return card
```

校验失败不丢弃卡片，诚实降级即可。

### 7.4 与旧可靠性评分的根本区别

| | v0.2 可靠性 | v0.3 交叉验证 |
|---|---|---|
| 判断依据 | 来源的身份（域名） | 来源之间的语义收敛关系 |
| 判断粒度 | 来源级别 | 论断级别 |
| 失败模式 | 系统性排除某些域名 | 单个论断可能被高估或低估 |
| 可审查性 | 不可审查（为什么 45 分？） | 可审查（核对 corroborating_sources） |
| 单来源论断 | 低可靠性 → 被过滤 | 保留但诚实标记为 single_source |
| 多来源一致 | 无法利用 | 自然获得高支撑度 |
| 维护成本 | 域名列表持续维护 | 零维护 |

## 8. extract 失败降级

extract 失败时的处理逻辑不变：仍然将失败的来源放入 ExtractedSource（raw_content 使用搜索摘要），仍然生成 EvidenceCard。

新设计下的区别在于交叉验证信号的诚实反映：

| 主来源内容 | 验证源内容 | 交叉验证有效性 |
|---|---|---|
| 完整原文 | 完整原文 | ✅ 完整有效 |
| 完整原文 | 搜索摘要 | ⚠️ 弱有效 |
| 搜索摘要 | 搜索摘要 | ⚠️ 弱有效 |
| 搜索摘要 | （无验证源） | ❌ 单来源 |

LLM 在生成 EvidenceCard 时根据 content_type 自行判断交叉验证信号质量，代码层在校验时确保 `strongly_corroborated` 必须有足够的 full-text 验证源。

## 9. 下游节点适配

### 9.1 synthesize_notes

将 EvidenceCard 分层呈现在 prompt 中：

```text
Strongly corroborated claims (3+ independent sources agree):
- [card1] claim A (supported by: url1, url2, url3)
- [card2] claim B (supported by: ...)

Weakly corroborated claims (2 independent sources agree):
- [card3] claim C (supported by: url4, url5)

Single-source claims (only one source mentions this):
- [card4] claim D (source: url6)

Guidelines:
- Strongly corroborated claims form the backbone of findings
- Single-source claims may be included but should be noted as lower confidence
- Never elevate a single-source claim to a key finding unless it is uniquely
  important and the source is a primary source for that specific fact
```

Fallback 逻辑调整：无 evidence_cards 时，按 corroboration_level 排序构建 fallback notes（强支撑度优先）。

### 9.2 write_report

allowed_urls 逻辑不变（仍来自 EvidenceCard source_url）。writing prompt 增加：

```text
When citing claims in the report body:
- Claims supported by multiple independent sources should be presented
  with higher certainty
- When a claim comes from a single source, consider using language like
  "According to [source]..." or "One perspective suggests..." rather than
  stating it as uncontested fact
- If different sources present conflicting views, present both sides
  rather than choosing one
```

### 9.3 verbose 输出

删除原来的 `Source quality:` 和 `Evidence reliability:` 两个段落，替换为：

```text
Evidence corroboration:
- strongly_corroborated: 5 (3+ independent sources agree)
- weakly_corroborated: 12 (2 independent sources agree)
- single_source: 11 (only one source mentions this)
```

### 9.4 review_report、save_report

这两个节点不涉及 EvidenceCard 或来源评分，保持不变。

## 10. prepare_evidence 节点变更

变更后的内部流程：

```text
输入: search_results, subquestions, question

Step A: URL 去重 (不变)
Step B: 来源选择 — 相关性排序 + 域名多样性 (替代旧的 _apply_quality + _select_by_subquestion)
Step C: Tavily extract (不变)
Step D: extract 失败 fallback (不变)
Step E: LLM 生成 EvidenceCard — 带交叉验证指令 (prompt 更新)
Step F: 交叉验证事后校验 (新增 validate_corroboration)
Step G: 计算 evidence_metrics — 改用 corroboration 分布 (更新 _build_metrics)

输出: search_results(精简), evidence_cards(带交叉验证), evidence_metrics(新维度)
```

## 11. 文件变更清单

### 新增

```text
（无新文件）
```

### 修改

```text
src/deepresearch/state.py              — 删除 SourceType/EvidenceReliability，精简模型，新增交叉验证字段
src/deepresearch/nodes/prepare_evidence.py  — 重写选择逻辑，新增校验函数，更新 metrics
src/deepresearch/prompts/evidence.py       — 重写 prompt，新增交叉验证指令
src/deepresearch/prompts/synthesizing.py   — 分层呈现 EvidenceCard
src/deepresearch/prompts/writing.py        — 增加支撑度相关写作指导
src/deepresearch/verbose.py                — 用 corroboration 分布替代旧指标
tests/test_state.py                        — 更新测试
tests/test_prepare_evidence_node.py        — 更新测试
tests/test_evidence_prompt.py              — 更新测试
tests/test_synthesizing_node.py            — 更新测试
tests/test_writing_node.py                 — 更新测试
tests/test_verbose.py                      — 更新测试
tests/test_integration_offline.py          — 更新集成测试
tests/test_graph_structure.py              — 确认 7 步节点序列不变
README.md                                  — 更新 evidence pipeline 说明
```

### 删除

```text
src/deepresearch/source_quality.py         — 整个文件删除
tests/test_source_quality.py               — 整个文件删除
```

## 12. 验收标准

### 12.1 离线工程验收

1. 离线测试全部通过。
2. `source_quality.py` 文件已删除。
3. `SourceType` 和 `EvidenceReliability` 枚举已从 state.py 删除。
4. `SearchResult` 不含 `source_type`、`source_quality_score`、`source_quality_reason`。
5. `EvidenceCard` 含 `corroboration_level` 和 `corroborating_sources`。
6. `ResearchState` 不含 `extracted_sources`。
7. 来源选择使用 Tavily relevance score + 域名多样性，不使用硬编码评分。
8. EvidenceCard 生成 prompt 包含交叉验证指令。
9. 代码层校验交叉验证信号（不存在的 URL 降级，同域名不算交叉验证）。
10. `synthesize_notes` prompt 分层呈现 EvidenceCard。
11. `write_report` allowed_urls 仍只来自 EvidenceCard。
12. `--verbose` 展示 `Evidence corroboration` 分布，不展示旧的 Source quality 和 Evidence reliability。
13. 默认测试不调用外部 API。

### 12.2 在线验收

使用 3 个相同问题：

```text
1. AI 搜索引擎的发展趋势
2. LangGraph 和 CrewAI 的适用场景
3. 新能源汽车固态电池商业化进展
```

通过标准：

```text
至少 2/3 成功。
```

每篇成功报告满足：

```text
EvidenceCard >= 5
不同来源 >= 3
strongly + weakly corroborated 占比 >= 50%（新指标，替代旧的 reliability 占比）
Review score >= 85
```

## 13. 风险与缓解

### 13.1 单来源论断不被重视

风险：小众领域或新话题可能找不到足够的独立来源进行交叉验证。

缓解：
- 单来源论断仍保留在 EvidenceCard 和报告中，只是标记为 single_source
- LLM 有自主判断权：如果某单来源论断在特定上下文中不可替代（如独家数据），仍可被引用
- 这是"诚实标记"策略，不是"排除"策略

### 13.2 LLM 可能编造交叉验证

风险：LLM 可能声称两个来源说了同一件事，但实际上没有。

缓解：
- 事后校验 1：验证源 URL 必须真实存在于 extracted sources 中
- 事后校验 2：验证源域名必须和主来源不同
- 事后校验 3：strongly_corroborated 必须有足够的 full-text 验证源
- corroborating_sources 列表对用户可见，可被人类审查

### 13.3 同领域来源可能有关联

风险：两个"不同域名"的来源可能实际上引用同一篇原始报道。

缓解：v0.3 不解决引用链追踪问题。这是 v0.4 独立验证器的范畴。但不同域名仍比同域名多一层独立性保障。

## 14. 与后续版本的衔接

v0.3 的交叉验证为后续增强打下基础：

- **v0.4 独立 NLI 验证器**：在交叉验证基础上，用一个独立 LLM 实例逐条验证"来源原文是否真的蕴含（entail）该论断"。
- **v0.5 矛盾检测**：当不同的 corroboration cluster 给出相反结论时，在报告中呈现矛盾而非选择一方。
- **v0.6 知识图谱表示**：将 corroboration 关系建模为 DAG，支持信任传播和脆弱性分析。

## 15. 推荐实现顺序

1. 删除 `source_quality.py` 和相关测试文件。
2. 更新数据模型（state.py）：删除枚举和字段，新增交叉验证字段。
3. 更新 prepare_evidence：新选择逻辑 + 新 prompt + 事后校验 + 新 metrics。
4. 更新 prompts（evidence、synthesizing、writing）。
5. 更新下游节点（synthesizing、writing）。
6. 更新 verbose 输出。
7. 更新 README。
8. 更新所有测试。
9. 运行离线测试。
10. 运行在线 3 题验收。

## 16. 总结

v0.3 不做加法，做减法：

```text
删除 source_quality.py（硬编码评分）
删除 SourceType 枚举
删除 EvidenceReliability 枚举
删除 source_quality_score / source_quality_reason
删除 extracted_sources（State 中间态）

新增 corroboration_level（交叉验证支撑度）
新增 corroborating_sources（可审查的验证源列表）
新增域名多样性选择逻辑
```

核心价值：

```text
从"我相信这个来源"变成"这些独立来源同时说了这件事"——
判断依据从一次性的身份预判变成可计算、可审查的多源收敛。
```
