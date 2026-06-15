# Deep Research Agent v0.6 设计规格：三架构能力上限横向对比评估

日期：2026-06-16

## 1. 背景

v0.6 引入了三种执行架构（Pipeline、Multi-Agent、ReAct），但没有统一的评估框架来衡量三者之间的差异。v0.5.2 时代的评估体系（15 个确定性评估器）测的是"有没有出错"（引用合规、幻觉 URL），不区分架构差异。

需要一套新评估体系来回答：**"如果给足资源，每种架构能做到多好？"**

## 2. 核心设计原则

### 2.1 架构无关的数据源

所有质量指标从**最终报告文本**提取，不依赖架构特有的中间产物。

```
之前（有问题）：
  distinct_claims ← state["evidence_cards"]  ← Pipeline/Multi-Agent 有，ReAct 为 0
  → ReAct 在 45% 权重上结构性失分

现在（修复后）：
  distinct_claims ← LLM 从 report_markdown 提取 → 映射 [N] 到 Sources URL → 计算印证
  → 三种架构公平比较
```

### 2.2 测天花板而非性价比

- 给足 token 预算（ReAct max_iterations=15）
- 成本和时间仅记录，不入 composite
- 目标是发现每种架构在该问题类型上的质量上限

### 2.3 质量优先于排名

最终报告以"无银弹"为核心结论——三种架构在不同问题类型上各有优势，不产出绝对排名。

## 3. 五个评价维度

### 维度 1：事实深度（Factual Depth）

测量报告提供了多少可验证的、有来源支撑的事实。

| 指标 | 计算方式 |
|------|---------|
| `distinct_claims` | LLM 从报告提取的独立声明数 |
| `quality_weighted_claims` | Σ(每条声明 × corroboration_weight)，惩罚单源/不可验证声明 |
| `avg_sources_per_claim` | 每条声明平均支撑来源数 |
| `single_source_ratio` | 单源或无源声明占比 |
| `max_corroboration_depth` | max(每条声明的 unique_citation_domains) |

声明提取 prompt 要求 LLM 从报告正文提取所有独立事实声明，标注支撑的 `[N]` 引用编号。确定性后处理：解析 `## Sources` → 映射编号到 URL → 域名去重 → 计算印证等级。

### 维度 2：探索广度（Exploration Breadth）

测量报告引用的信息源多样性。

| 指标 | 计算方式 |
|------|---------|
| `unique_domains_cited` | `## Sources` 中独立域名数 |

> `fulltext_ratio` 保留但仅对 Pipeline 适用。Multi-Agent 和 ReAct 标记 N/A。

### 维度 3：交叉验证强度（Corroboration Strength）

测量报告的结论是单源还是多源印证。

| 指标 | 计算方式 |
|------|---------|
| `strong_corroboration_pct` | ≥3 个独立域名支撑的声明占比 |
| `weak_corroboration_pct` | 2 个独立域名支撑的声明占比 |
| `cross_perspective_pct` | 仅 Multi-Agent——跨 Agent 印证占比。Pipeline/ReAct 标记 N/A |
| `contradictions_acknowledged` | 报告中是否标注了矛盾观点（架构无关，从报告文本检测） |

印证权重（确定性、零 LLM）：
```
≥3 unique domains → strong (weight=1.0)
=2 unique domains → weak (weight=0.75)
=1 unique domain → single (weight=0.5)
=0 valid citations → unverifiable (weight=0.5)
```

### 维度 4：结构完整性（Structural Completeness）

LLM-as-Judge 评分。Judge 模型列出问题应覆盖的 5-8 个信息维度，逐维度评分 0.0/0.5/1.0。

### 维度 5：不确定性诚实度（Uncertainty Honesty）

LLM-as-Judge 评分（1-5 量表）。测量报告是否诚实呈现了"不知道"和"存在争议"。

### Composite 公式

```
composite = 0.25 × normalize(quality_weighted_claims, 0, 30)
          + 0.20 × normalize(unique_domains_cited, 0, 30)
          + 0.20 × (strong_corroboration_pct + weak_corroboration_pct)
          + 0.20 × coverage_score
          + 0.15 × (honesty_score / 5.0)
```

## 4. 报告引用解析

`_parse_citation_map()` 从 `## Sources`（或等效中文标题 `## 来源`、`## 参考来源`）节提取引用编号→URL 映射。支持三种格式：

1. `[N] https://...` — Pipeline / Multi-Agent 标准格式
2. `N. [Title](https://...)` — React Markdown 编号列表
3. `[N] Author, "Title", Year. URL` — React 引用格式（当前未完全支持，已知限制）

## 5. 过程指标

仅记录，不参与评分：

| 指标 | Pipeline/Multi-Agent | ReAct |
|------|---------------------|-------|
| `wall_time_seconds` | graph invoke 耗时 | agent run 耗时 |
| `total_tokens` | 从 state.token_usage 聚合 | 从 result.token_usage 聚合 |
| `llm_call_count` | token_usage 长度 | 同上 |
| `search_query_count` | search_results 数量 | 从 ReActStep 统计 action="search" |
| `pages_fetched` | extract 调用次数 | 从 ReActStep 统计 action="fetch" |
| `iterations` | N/A（填 0） | ReAct 循环轮次 |

## 6. 实验设计

### 6.1 题目设计

三题覆盖三种认知复杂度：

| ID | 类型 | 题目 | 测试焦点 |
|----|------|------|---------|
| Q1 | 事实密集型 | 固态电池 2026 商业化进展 | 提取精度 + 交叉验证 |
| Q2 | 对比型 | LangGraph vs CrewAI 技术选型 | 视角多样性 + 平衡性 |
| Q3 | 开放探索型 | 2026 AI Agent 核心工程挑战 | 搜索策略 + 自我纠正 |

### 6.2 执行矩阵

3 架构 × 3 题目 × 3 轮 = 27 次运行。每轮完整真实 API 调用（搜索 + LLM）。

### 6.3 控制

- LLM: DeepSeek v4-flash（所有架构相同）
- 搜索: Tavily Search API（双 Key Pool，自动故障切换）
- Judge: 同模型（已知自评偏差，Limitations 显式标注）
- max_subquestions=3, results_per_query=4

## 7. 已知限制

1. **自评偏差**：Judge 模型与生成模型相同 → coverage/honesty 天花板效应
2. **React 引用格式不稳定**：`## 来源` 中的 `[N] Author, Title. URL` 格式当前解析失败
3. **样本量不足**：每架构 9 数据点，不做统计检验
4. **事实正确性未验证**：测量方法论质量，不测量事实正确性
5. **矛盾检测词法级别**：正则匹配，漏检语义矛盾

## 8. 文件变更

```
新增:
  benchmark/capability_eval.py       — 五维度评分引擎
  benchmark/capability_compare.py    — 对比矩阵生成器
  benchmark/run_capability_eval.py   — 27 轮执行编排
  benchmark/capability_results/      — 原始数据 + FINAL_REPORT.md

修改:
  src/deepresearch/runner.py         — ReAct 返回 _react_steps + search_results
  src/deepresearch/clients/tavily_pool.py  — Key Pool 自动切换
```

## 9. 与旧评估体系的关系

v0.5.2 的 15 个确定性评估器（`evaluators.py`）仍然有效——它们验证引用合规性和格式正确性，是底线检查。新评估体系定位在"能力上限"层，两者是互补关系。
