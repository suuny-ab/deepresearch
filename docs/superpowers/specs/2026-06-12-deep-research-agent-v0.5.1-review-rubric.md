# Deep Research Agent v0.5.1 设计规格：Review 评分 Rubric

日期：2026-06-12

## 1. 背景

v0.1 以来的 `review_report` 节点有两个设计缺陷：

1. **评分无 rubric**：prompt 只列出了五个维度名称，没有锚点定义。LLM 凭感觉打 0-100 整数，方差大。
2. **入参错误**：reviewer 拿到的 allowed URL 列表是 `search_results`（~74 个搜索返回 URL），而不是 `evidence_cards`（~10 个报告实际使用的来源 URL）。

本轮修复两个问题。review 保持纯观测角色，不引入反馈闭环。

## 2. 五维评分 Rubric

| 维度 | 权重 | 锚点 |
|---|---|---|
| 来源支撑 | 30% | 90+: 所有关键结论有编号引用且 URL 来自 EvidenceCard；60-89: 多数有引用；30-59: 大量无引用；0-29: 基本无引用 |
| 交叉验证覆盖 | 20% | 90+: 主要结论由 strongly/weakly corroborated 支撑；60-89: 部分有交叉验证 |
| 完整性 | 20% | 90+: 覆盖所有子问题核心论点；60-89: 覆盖多数但遗漏某些角度 |
| 结构与清晰度 | 15% | 90+: 章节齐全逻辑清晰；60-89: 章节齐全但某节薄弱 |
| 相关性与聚焦 | 15% | 90+: 全部内容紧扣问题；60-89: 大部分相关 |

总分 = 各维度分 × 权重求和。

## 3. 入参修正

`search_results` → `evidence_cards`。reviewer 看到的是实际证据卡片来源而非全部搜索返回。

## 4. 文件变更

```text
修改: src/deepresearch/prompts/reviewing.py
修改: src/deepresearch/nodes/reviewing.py
修改: tests/test_reviewing_node.py
```

## 5. 验收

- 离线测试通过
- 在线运行 review score 方差缩小
