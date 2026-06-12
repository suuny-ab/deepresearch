# Deep Research Agent v0.5.2 设计规格：Pending Issues 修复

日期：2026-06-12

## 1. 背景

v0.3 online acceptance 验收后记录了 7 个 pending issues。经过 v0.3.1～v0.5.1 的迭代，其中 5 个已自动解决：

| # | 问题 | 状态 |
|---|---|---|
| 1 | 提取+验证捆在一次调用 | ✅ v0.4 两阶段管线解决 |
| 2 | 子问题上下文丢失 | ✅ v0.3.1 解决 |
| 3 | Notes 全有或全无降级 | ✅ 节点已移除（commit 3f3b7ff） |
| 4 | 无数量期望 | ⚠️ 本次修复 |
| 5 | Review 无评分 Rubric | ✅ v0.5.1 解决 |
| 6 | Review 无反馈闭环 | ⚠️ 本次修复 |
| 7 | Notes 节点价值存疑 | ✅ 节点已移除 |

本次修复剩余 2 个问题。

## 2. 提取数量期望

### 问题

Phase 1 extraction prompt 当前指令为 "There is no minimum or maximum"，虽在 v0.4 两阶段管线后已无保守压制，但完全无下限可能导致 LLM 过于随意。

### 改动

在 `prompts/extraction.py` 的规则段落中增加 soft guideline：

```
Extract at least 2-4 claims per source on average.
Sources with rich content may support more; thin sources may support fewer.
```

这是 soft guideline，不设硬上限，不给 LLM 压力编造 claim。

### 涉及文件

- `src/deepresearch/prompts/extraction.py` — 改 1 行
- `tests/test_extraction_prompt.py` — 验证指令存在

## 3. Review 反馈闭环

### 问题

review_report 节点消耗 1 次 LLM 调用计算评分，但结果不触发任何行动。管线中唯一的"只观测不行动"节点。

### 目标流程

```
write_report → review_report → score ≥ 70 → save_report
                               score < 70 → rewrite_report (含 review 反馈) → review_report (再次评分)
                                            第二次 < 70 → save_report
```

### 关键设计

1. **阈值**：总分 < 70 触发重写
2. **最多 1 次重写**：总计最多 2 次 write + 2 次 review
3. **重写注入 review 反馈**：第二次 write 的 prompt 包含第一次 review 的 issues/suggestions
4. **重写不降低验证要求**：重写后的报告仍需通过 citation validation

### 边界情况

- 重写后 review 再次失败 → 直接保存，不二次重写
- review LLM 调用失败 → 视为 score=0，不触发重写
- 重写后 citation validation 失败 → 正常保存失败报告

### 状态变更

`ResearchState` 新增字段：
```python
review_feedback: str | None  # 格式化的 review issues/suggestions
```

### 图结构变更

```
review_report → rewrite? (conditional)
  ├─ score >= 70 → save_report
  └─ score < 70 → write_report (with review_feedback)
```

注意：write_report → review_report 是固定的。rewrite 走的是 `write_report → review_report` 路径，而不是单独的新节点。

### 涉及文件

| 文件 | 改动 |
|---|---|
| `src/deepresearch/state.py` | 新增 `review_feedback` 字段 |
| `src/deepresearch/graph.py` | 条件边 review → write or save |
| `src/deepresearch/nodes/writing.py` | 注入 review_feedback 到 rewrite prompt |
| `src/deepresearch/prompts/writing.py` | `build_writing_prompt` 接受可选 review_feedback |
| `src/deepresearch/cli.py` | verbose 展示 rewrite 信息 |
| `tests/test_graph_structure.py` | 条件边测试 |
| `tests/test_writing_node.py` | rewrite with review feedback 测试 |

## 4. 非目标

- 不修改 evidence 管线
- 不添加跨子问题综合
- 不修改搜索策略
- 不修改评分 Rubric

## 5. 验收标准

### 5.1 提取数量期望

- extraction prompt 包含 "at least 2-4 claims per source" 指令
- 离线测试验证指令存在

### 5.2 Review 反馈闭环

- review score < 70 触发重写
- 重写 prompt 包含 review feedback
- 最多 1 次重写
- review LLM 失败不触发重写
- 所有测试通过
