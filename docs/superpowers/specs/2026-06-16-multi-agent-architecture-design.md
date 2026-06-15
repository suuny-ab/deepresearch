# Deep Research Agent v0.6 设计规格：多 Agent 协作架构

日期：2026-06-16

## 1. 背景

v0.5.2 的架构是单 Agent 固定 6 步流水线：

```
plan → search → prepare_evidence(Phase1+Phase2) → write → review ⇄ save
```

这个架构有两个根本限制：

1. **单点故障**：所有搜索结果共用一个提取+验证管线。一个子问题的 Tavily 调用失败不会阻塞全局，但证据管线是串行的——Phase 1 一次调用的 prompt 包含所有来源，Phase 2 的 N 次调用虽然是并行的，但共享同一个 LLM 客户端。没有真正的"故障隔离"。

2. **子问题间无协作**：每个子问题独立搜索，但提取和验证发生在全局层面。这导致子问题 A 的来源不太可能作为子问题 B 中某条声明的交叉验证源——因为 Phase 2 只在子问题内部做验证。跨子问题的印证关系被丢失了。

v0.6 引入多 Agent 架构，将每个子问题的研究任务分配给独立的子问题 Agent，由 Coordinator 汇总。

## 2. 新架构

```
                    ┌─────────────┐
                    │  Planner    │  分解问题 → 子问题列表
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │Agent sq1 │ │Agent sq2 │ │Agent sq3 │  ← 并行，ThreadPoolExecutor
        │ search   │ │ search   │ │ search   │
        │ extract  │ │ extract  │ │ extract  │
        │ validate │ │ validate │ │ validate │
        │→ cards1  │ │→ cards2  │ │→ cards3  │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             └────────────┼────────────┘
                          ▼
                   ┌──────────────┐
                   │ Coordinator  │  合并 + 跨Agent交叉验证 + 矛盾检测
                   │ → 全局证据  │
                   └──────┬───────┘
                          ▼
                   ┌──────────────┐
                   │  Writer      │  基于全局证据撰写报告
                   └──────┬───────┘
                          ▼
                   ┌──────────────┐
                   │  Reviewer    │  评分 + 反馈闭环（score < 70 触发重写）
                   └──────────────┘
```

CLI 通过 `--architecture` 参数切换：
```bash
--architecture pipeline      # 单流水线（默认）
--architecture multi-agent   # 多Agent协作
--architecture react         # 自主ReAct Agent
```

## 3. 子问题 Agent 设计

每个 Agent 独立执行：搜索 → 来源选择（相关性+域名多样性）→ 全文提取 → Phase 1 提取声明 → Phase 2 交叉验证 → 后校验。

### 3.1 故障隔离

Agent 之间完全独立。一个 Agent 崩溃不影响其他 Agent 的结果。Coordinator 收到的是部分 Agent 结果时，仍能生成报告（标记缺失部分为"信息不足"）。

### 3.2 与 Pipeline 的差异

| | Pipeline | Multi-Agent |
|---|---------|-------------|
| Phase 1 提取 | 1 次 LLM 调用，所有来源一起提取 | N 次调用，每个 Agent 独立提取 |
| Phase 2 验证 | N 次调用，每个子问题独立（但共享 LLM 客户端） | N 次调用，Agent 线程内串行，Agent 间并行 |
| 跨子问题验证 | 无 | ✅ Coordinator 检测跨 Agent 的相同事实 |
| 域名多样性 | 全局按子问题去重 | 每个 Agent 独立去重，全局域名更多样 |
| 失败容忍 | 单次 LLM 调用失败可能导致全局退化 | 单个 Agent 失败不影响其他 |

## 4. Coordinator 设计

### 4.1 合并逻辑

- 所有 Agent 的 evidence_cards 合并，按 card.id 去重
- 保留每个 card 的原始出处 Agent 信息

### 4.2 跨 Agent 交叉验证

当两个不同 Agent 独立从不同域名发现同一事实时，Coordinator 升级二者的 corroboration_level：
- single_source → weakly_corroborated
- weakly_corroborated → strongly_corroborated

检测方式：词法 word overlap（阈值 0.5）。跨 Agent 且跨域名的声明对被标记为"跨视角印证"。

### 4.3 矛盾检测

当两个 Agent 对同一话题产出方向相反的声明（word overlap ≥ 0.3 且包含矛盾标记词如"然而/但是/however"），标记为 Contradiction。

当前为词法级别（确定性、零成本）。已知漏检语义矛盾和隐含矛盾。

## 5. Graph 结构

```
START → plan_research → run_agents(并行) → coordinator → write → review ⇄ save → END
```

与 Pipeline 的区别：`search_web` 和 `prepare_evidence` 节点被 `run_agents` + `coordinator` 替代。

## 6. 文件变更

```
新增:
  src/deepresearch/agents/__init__.py
  src/deepresearch/agents/subquestion_agent.py
  src/deepresearch/agents/coordinator.py
  src/deepresearch/graph_v2.py
  tests/test_subquestion_agent.py

修改:
  src/deepresearch/runner.py         — 支持 architecture="multi-agent"
  src/deepresearch/cli.py            — --architecture 参数
  src/deepresearch/state.py          — _agent_results 等字段
```

## 7. 设计权衡

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent 间并行方式 | ThreadPoolExecutor | LLM + Tavily 都是 IO-bound，线程即可 |
| Phase 1 在每个 Agent 内独立执行 | 是 | 上下文小（只自己来源），提取更聚焦 |
| 跨 Agent 交叉验证 | 词法 word overlap | 确定性、零成本。已知漏检率 |
| 矛盾检测 | 词法正则 | 同上 |
| 代码复用 | 复制 prepare_evidence 逻辑到 agent | 技术债，后续重构为共享模块 |

## 8. 非目标

- 不修改 Write/Review/Save 节点
- 不修改引用校验逻辑
- 不做 Agent 动态数量分配（固定 = 子问题数）
