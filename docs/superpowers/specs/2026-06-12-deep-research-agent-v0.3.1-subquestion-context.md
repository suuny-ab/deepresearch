# Deep Research Agent v0.3.1 设计规格：子问题上下文传递 + 轻量测试

日期：2026-06-12

## 1. 背景

v0.3 在线验收暴露了一个结构性问题：子问题在 `plan_research` 中被精心拆解为 5 个维度，每个有明确的研究意图和角度，但在 `prepare_evidence` 的证据提取 prompt 中，这个结构被丢弃了——LLM 看到一个扁平的 15 篇原文列表，每篇只带裸 `subquestion_id`（如 `"q1"`），但完全不知道 `"q1"` 问的是什么。

这导致 LLM 在交叉验证时只能依赖文本表面相似度进行判断。"固态电池"这种事实型话题不受影响（同一个事实数字跨子问题的一致性很高），但"LangGraph vs CrewAI"这种对比型话题受到严重冲击——同一组概念在不同子问题中含义不同，LLM 在无法区分语境的情况下选择了保守策略（只产出 4 张 100% 确定的卡片）。

同时，当前在线验证流程太重（15 分钟三题全流程），需要一个轻量的、可 A/B 测的测试手段。

## 2. 版本目标

1. **子问题上下文传递**：将子问题的研究意图传递到证据提取 prompt 中，让 LLM 在做交叉验证时知道每篇来源在回答什么问题。
2. **轻量测试模式**：新增 `--dry-run` 标志，流水线在 `prepare_evidence` 完成后停止并输出证据卡片摘要，2 分钟出结果。

## 3. 非目标

- 不解耦提取和交叉验证
- 不加 EvidenceCard 数量下限
- 不修 Notes 降级逻辑
- 不调 review 评分

## 4. 设计

### 4.1 子问题上下文传递

**当前 prompt 结构（v0.3）：**

```text
Original question: AI搜索引擎的发展趋势

Sources:
[{subquestion_id:"q1", url:"...", raw_content:"..."},
 {subquestion_id:"q2", url:"...", raw_content:"..."},
 ...]  ← 扁平的 15 篇，子问题只有 ID 没有内容
```

**新 prompt 结构（v0.3.1）：**

```text
Original question: AI搜索引擎的发展趋势

Research subquestions:
1. [q1] AI搜索引擎的核心技术趋势是什么？
2. [q2] 当前AI搜索引擎的产品竞争格局和商业化趋势如何？
3. [q3] AI搜索引擎如何改变用户交互与体验？
...

Sources (grouped by subquestion):
━━━ q1: AI搜索引擎的核心技术趋势是什么？ ━━━
  - Source from example.com: "...full text..."
  - Source from arxiv.org: "...full text..."

━━━ q2: 当前AI搜索引擎的产品竞争格局 ━━━
  - Source from 36kr.com: "...full text..."
  - Source from market.us: "...full text..."
...
```

**关键设计选择：**

- 来源按子问题分组呈现，组头显示子问题文本
- 组与组之间用可视分隔符（`━━━`）隔离
- 来源仍保留 `content_type` 标记
- 交叉验证指令不变，但 LLM 现在可以借助子问题上下文判断两个来源的"同一件事"是否在同一个语义维度上

### 4.2 轻量测试模式

新增 CLI 参数 `--dry-run`：

```
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --dry-run --verbose
```

流水线行为：`plan_research → search_web → prepare_evidence → STOP`

停止时输出：

```text
[Dry run] Evidence extraction complete.

EvidenceCards: 7
Evidence corroboration:
- strongly_corroborated: 3 (3+ independent sources agree)
- weakly_corroborated: 3 (2 independent sources agree)
- single_source: 1 (only one source mentions this)

Evidence card summaries:
1. [e1] LangGraph excels at fine-grained control... (corroboration: strongly, sources: 3)
2. [e2] CrewAI is better for role-based task decomposition... (corroboration: weakly, sources: 2)
...
```

**实现方式**：

`graph.py`：新增 `build_research_graph` 参数 `dry_run: bool = False`。当 `dry_run=True` 时，`prepare_evidence` 边连到 `END` 而非 `synthesize_notes`。

`cli.py`：`--dry-run` 标志传给 graph。在 invoke 后如果 `dry_run`，不调 writer/review/save 的输出，打印证据摘要。

`nodes/prepare_evidence.py`：输出 state 中增加 `dry_run: True` 标志，CLI 据此判断输出格式。

### 4.3 轻量测试参数建议

```bash
# 轻量验证（~2 min）
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" \
  --dry-run --verbose \
  --max-subquestions 2 --results-per-query 2

# 通过后标准验证（对比型，完整流程）
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --verbose
```

## 5. 文件变更

```text
修改:
  src/deepresearch/prompts/evidence.py       — 新增 subquestions 参数，分组呈现来源
  src/deepresearch/nodes/prepare_evidence.py — 传入 subquestions 到 prompt
  src/deepresearch/graph.py                  — 新增 dry_run 参数
  src/deepresearch/cli.py                    — 新增 --dry-run 标志，输出证据摘要
  tests/test_evidence_prompt.py              — 更新测试
  tests/test_prepare_evidence_node.py        — 更新测试
  tests/test_graph_structure.py              — 新增 dry_run 图结构测试
```

## 6. 验收标准

### 6.1 离线测试

- 全部测试通过
- `build_evidence_prompt` prompt 中包含子问题文本和分组结构
- `--dry-run` 模式下图在 `prepare_evidence` 后停止

### 6.2 轻量在线验证

```
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --dry-run --verbose --max-subquestions 2 --results-per-query 2
```

验证：
- EvidenceCard >= 5
- 交叉验证分布合理
- 执行时间 < 3 分钟

### 6.3 标准在线验证

轻量通过后，用原参数重跑对比型话题：

```
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --verbose
```

验证：
- EvidenceCard >= 5（对比型基线从 4 提升）
- Review score >= 85

## 7. A/B 测基线

| 指标 | v0.3 基线（对比型） | v0.3.1 目标 |
|---|---|---|
| EvidenceCard 数 | 4 | >= 5 |
| 交叉验证率 | 100% | 保持高（允许 single_source 出现但不应主导） |
| 报告评分 | 95 | 保持高 |

## 8. 风险

- **改不了**：如果子问题上下文传递后卡片数仍为 4，说明 prompt 层面的优化已到天花板，确认需要架构级改动（拆开提取+验证）。这是**正向信息**——A/B 测给出了明确信号。
- **改坏了**：交叉验证质量下降（LLM 拿了更多上下文后放松了严格性，产出更多但支撑不足的卡片）。回滚到 v0.3 即可。
