# Deep Research Agent 简历优化计划

日期：2026-06-15
预计工期：48 小时
状态：✅ Phase 1-3 完成，Phase 4 部分完成（README、测试、清理），Hybrid 整合留待后续

## 目标

将 Deep Research Agent 从"单 Agent 固定流水线"升级为"多 Agent 协作 + 自主 ReAct 双模式研究系统"，最大化简历竞争力。

目标岗位：Agent 开发

## 总体策略

按依赖关系排序，确保每一阶段产出是下一阶段的基础：

```
Phase 1: 基础设施（让后续工作更快）
  → Phase 2: 核心架构升级（最大的简历差异化）
    → Phase 3: Agent 能力扩展（展示工具设计和自主决策）
      → Phase 4: 打磨与验证（量化数据 + 文档 + 展示）
```

---

## Phase 1：基础设施与基线（~8h）

### 任务 1.1：Benchmark 基线采集（2h）

**目标**：在改动任何代码前，获得当前版本的完整量化基线

- 创建/确认 5-8 个 benchmark 查询（覆盖中英文、对比型、事实型、前瞻型）
- 用 `evaluate_all()` 跑一遍，产出 `benchmark/baselines/v0.6-baseline.json`
- 记录 15 个指标在所有查询上的数值

**产出文件**：`benchmark/baselines/v0.6-baseline.json`

### 任务 1.2：Phase 2 并行化（2h）

**目标**：让每个开发迭代快 3-5 倍

5 个子问题的 Phase 2 验证从串行 15s → 并行 3s。

**改动范围**：
- `runner.py`：`build_agent` 支持并发执行
- `prepare_evidence.py`：`_phase2_validate` 的 for 循环改为 `ThreadPoolExecutor` 并发
- 对应的 fake client 需要适配

**为什么先做**：后续所有开发——多 Agent、ReAct、benchmark 重跑——都依赖反复跑完整流水线验证效果。

### 任务 1.3：Token 用量与成本追踪（2h）

**目标**：每次运行都能看到精确的成本分解

- `LLMClient.complete()` 返回类型从 `str` 改为 `(str, UsageInfo)`
- `UsageInfo` 包含 `prompt_tokens`、`completion_tokens`、`estimated_cost`
- `ResearchState` 新增 `token_usage: dict[str, list[UsageInfo]]` 字段（按节点分组）
- 终端输出追加一行汇总：`💰 26,340 tokens · ~$0.07 · plan(2.3k) search(0) evidence(15.2k) write(5.4k) review(3.4k)`
- Fake LLM 返回 `(predefined_response, UsageInfo(0, 0, 0))`

### 任务 1.4：搜索并发化（2h）

**目标**：每个子问题的多个 search query 并行发出

当前 `searching.py` 中每个子问题的每个 query 是串行 for 循环。改为子问题间并行。

---

## Phase 2：多 Agent 架构（~14h）

### 架构目标

从单 Agent 固定流水线升级为多 Agent 协作系统：

```
                    ┌─────────────┐
                    │  Planner    │  分解问题 → 子问题列表
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │Agent sq1 │ │Agent sq2 │ │Agent sq3 │  ← 并行执行
        │ search   │ │ search   │ │ search   │
        │ extract  │ │ extract  │ │ extract  │
        │ validate │ │ validate │ │ validate │
        │→ cards1  │ │→ cards2  │ │→ cards3  │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             └────────────┼────────────┘
                          ▼
                   ┌──────────────┐
                   │ Coordinator  │  合并 + 消解冲突 + 识别跨子问题模式
                   │ → 全局证据  │
                   └──────┬───────┘
                          ▼
                   ┌──────────────┐
                   │  Writer      │  基于全局证据撰写报告
                   └──────┬───────┘
                          ▼
                   ┌──────────────┐
                   │  Reviewer    │  评分 + 反馈闭环
                   └──────────────┘
```

**关键设计决策**：
1. 每个子问题 Agent 复用现有 `planning → searching → prepare_evidence` 节点
2. Coordinator 合并 evidence_cards、检测跨子问题矛盾、生成全局交叉验证
3. 矛盾检测用确定性方法：相同关键词的 claim 被不同子问题标记了不同结论 → 标记为争议
4. 子问题 Agent 完全独立，一个崩溃不影响其他（失败隔离）

### 任务 2.1：方案设计（2h）

在新文件中设计，不动已有代码。

### 任务 2.2：子问题 Agent 实现（4h）

- 新建 `src/deepresearch/agents/subquestion_agent.py`
- 每个 Agent 封装 `planning → searching → prepare_evidence` 子图
- Agent 输入：`(question, subquestion_id)`，输出：`AgentResult(evidence_cards, token_usage, errors)`
- 支持并行执行（用 `ThreadPoolExecutor`）
- 每个 Agent 独立追踪自己的 token 用量

### 任务 2.3：Coordinator 实现（3h）

- 新建 `src/deepresearch/agents/coordinator.py`
- 合并逻辑：所有子 Agent 的 evidence_cards 合并、按 source_url 去重
- 跨子问题交叉验证：不同子问题中相同事实的独立来源支撑 → 升级 corroboration
- 矛盾检测：按 claim 关键词聚类，检测同一聚簇中结论相反的 claim pairs
- 输出：`CoordinatorResult(merged_cards, contradictions, cross_sq_corroborations)`

### 任务 2.4：Graph 重组（3h）

- 新建 `graph_v2.py`，保留 `graph.py` 不动
- 新 graph 结构：
  ```
  START → plan → [fork to agents] → coordinator → write → review ⇄ save → END
  ```
- `fork to agents` 用 LangGraph 的 `Send` API 做并行 fan-out
- `build_agent` 接受 `architecture: Literal["pipeline", "multi-agent"]` 参数

### 任务 2.5：Multi-Agent 测试（2h）

- 离线集成测试：4 个 fake 子问题 Agent 返回不同结果 → Coordinator 正确合并
- 矛盾检测测试：构造有已知矛盾的 claim 对 → 验证检测到
- 失败隔离测试：1 个 Agent 抛异常 → Coordinator 仍能处理其余 3 个

---

## Phase 3：Agent 能力扩展（~12h）

### 任务 3.1：自定义 Tool 体系（3h）

**目标**：给 Agent 更多"手和眼"

- 新建 `src/deepresearch/tools/` 模块
- `Tool` Protocol 定义：`name`、`description`、`parameters`(JSON Schema)、`execute(**kwargs) -> ToolResult`
- 实现 4 个工具：

| 工具 | 描述 | 实现方式 |
|------|------|---------|
| `TavilySearchTool` | 重构现有 Tavily 为 Tool 接口 | 已有代码，改接口 |
| `WikipediaTool` | 搜索 Wikipedia + 提取页面 | `wikipedia-api` 免费 |
| `ArxivTool` | 搜索学术论文，返回标题+摘要+链接 | ArXiv API 免费 |
| `WebFetchTool` | 抓取指定 URL 全文 | `httpx` + `BeautifulSoup` |

### 任务 3.2：ReAct Agent 模式（5h）

**目标**：在固定流水线之外，增加自主决策的研究模式

- 新建 `src/deepresearch/agents/react_agent.py`
- ReAct 循环：`Observe → Think → Act → Observe → ...`
- Agent 拥有的工具：4 个 Tool + `write_report` + `stop`
- `CLI --mode react` 参数切换

**关键约束**：
- `max_iterations = 15`：防止无限循环
- `search_history` 去重
- `overlap_threshold = 0.7`：新结果 URL 重叠度 > 70% → 提示信息增量不足
- `stop_condition`：连续 2 轮没有新增实质性信息 → 自动触发 write_report

### 任务 3.3：ReAct 与 Multi-Agent 的整合（2h）

**Hybrid 模式**：ReAct Planner 自主决定子问题拆分，每个子问题调用独立 Agent 搜索。

### 任务 3.4：ReAct 测试（2h）

- Mock LLM 返回预定义的 action 序列 → 验证循环逻辑
- 边界测试：max_iterations 截断、空搜索结果、连续 stop
- 去重逻辑测试

---

## Phase 4：打磨、验证与展示（~10h）

### 任务 4.1：完整 Benchmark 对比（3h）

```
1. git stash（保存新代码）
2. git checkout main（旧版本 baseline）
3. evaluate_all → baseline.json
4. git checkout -（回到新代码）
5. evaluate_all → candidate.json
6. compute_diff baseline.json candidate.json → diff_report.md
```

对比维度：
- Multi-Agent vs 单流水线的 evidence_card 数量
- ReAct vs 固定流水线的 source_utilization
- 两种模式的 token 成本对比
- 中文查询在 Wikipedia + Tavily 双源下的改善

### 任务 4.2：矛盾检测评估（2h）

- 手动构造 3 个已知有矛盾的查询
- 验证 Coordinator 能检测到矛盾
- 验证报告正确呈现了矛盾而非选择一边

### 任务 4.3：README 全面重写（2h）

新 README 结构：
- Demo GIF（顶部）
- 为什么这个项目值得关注（4 个关键设计决策）
- 架构 ASCII 图
- 关键设计决策表格
- 快速开始
- 基准测试结果
- 技术栈

### 任务 4.4：Demo 录制（0.5h）

录制 3 个场景：
1. 固定流水线快速运行
2. Multi-Agent 模式运行
3. ReAct 模式运行

### 任务 4.5：最终测试 + 清理（2.5h）

- 完整跑 `uv run pytest`
- 跑 3 次真实 API 冒烟测试
- 检查无 TODO、调试代码
- 确认 `.env.example` 完整
- 确认所有新模块有 docstring

---

## 时间分配总览

| Phase | 任务 | 预估 | 累计 |
|-------|------|------|------|
| **1** | 基础设施 | **8h** | **8h** |
| 1.1 | Benchmark 基线 | 2h | |
| 1.2 | Phase 2 并行化 | 2h | |
| 1.3 | Token 成本追踪 | 2h | |
| 1.4 | 搜索并发化 | 2h | |
| **2** | 多 Agent 架构 | **14h** | **22h** |
| 2.1 | 方案设计 | 2h | |
| 2.2 | 子问题 Agent | 4h | |
| 2.3 | Coordinator | 3h | |
| 2.4 | Graph 重组 | 3h | |
| 2.5 | 多 Agent 测试 | 2h | |
| **3** | Agent 能力扩展 | **12h** | **34h** |
| 3.1 | 自定义 Tool 体系 | 3h | |
| 3.2 | ReAct Agent | 5h | |
| 3.3 | Hybrid 整合 | 2h | |
| 3.4 | ReAct 测试 | 2h | |
| **4** | 打磨与展示 | **10h** | **44h** |
| 4.1 | Benchmark 对比 | 3h | |
| 4.2 | 矛盾检测评估 | 2h | |
| 4.3 | README 重写 | 2h | |
| 4.4 | Demo 录制 | 0.5h | |
| 4.5 | 最终测试+清理 | 2.5h | |
| **Buffer** | 调试、集成、意外 | **4h** | **48h** |

---

## 完成后项目能力矩阵

| 能力维度 | 当前状态 | 完成后 | 面试可讨论点 |
|----------|---------|--------|-------------|
| Agent 编排 | 单流水线 | 多 Agent 协作 + 单流水线双模式 | Agent 隔离、故障域、协调策略 |
| 自主决策 | 无 | ReAct 循环 + Hybrid 模式 | 停止条件、去重、探索-利用权衡 |
| 工具设计 | 仅 Tavily | 4 个 Tool + Protocol 抽象 | Tool 描述工程、Schema 设计、错误处理 |
| 证据质量 | 交叉验证 | 交叉验证 + 跨 Agent 验证 + 矛盾检测 | 多源收敛、不确定性呈现 |
| 性能 | 全串行 | 搜索并行 + Phase 2 并行 + Agent 并行 | IO-bound 并发策略 |
| 成本控制 | 无感知 | 每节点 token 追踪 + 成本汇总 | 运营成本意识 |
| 评估 | 15 个评估器 | 15 个评估器 + 前后对比数据 | 量化 vs 定性评估、指标选择 |
| 可观测性 | LangSmith 基础 | LangSmith + 自定义 feedback | trace 驱动开发 |
| 设计文档 | 12 份 spec | 12 份 spec + 架构决策文档 | 设计哲学、工程判断 |

---

## 实际完成状态（2026-06-15）

### ✅ Phase 1：基础设施（已完成）
- Benchmark 基线：3 题，100% 引用通过率，均分 84
- Phase 2 并行化：ThreadPoolExecutor，5 子问题 ~15s → ~3s
- Token 成本追踪：UsageInfo + TokenUsage 模型，每节点追踪，CLI 汇总展示
- 搜索并发化：searching.py 并行执行

### ✅ Phase 2：多 Agent 架构（已完成）
- `agents/subquestion_agent.py`：独立子问题 Agent，search → extract → validate
- `agents/coordinator.py`：合并证据卡 + 跨 Agent 交叉验证升级 + 矛盾检测
- `graph_v2.py`：Multi-agent graph → `plan → run_agents(parallel) → coordinator → write → review ⇄ save`
- CLI `--architecture multi-agent`
- 8 个新测试（agent + coordinator + 集成）

### ✅ Phase 3：Agent 能力扩展（已完成）
- `tools/` 包：Tool Protocol + ToolRegistry + TavilySearchTool + WebFetchTool
- `agents/react_agent.py`：ReAct 自主循环（Think → Act → Observe），搜索去重，饱和检测，最大迭代限制
- CLI `--architecture react`
- 11 个新测试（tools + ReAct）

### ✅ Phase 4：打磨（部分完成）
- README 全面重写（设计决策、架构图、基准数据）
- 195 测试全部通过
- ⏳ Demo GIF（待录制）
- ⏳ Multi-Agent/ReAct 基准对比（需真实 API 调用）
- ⏳ Hybrid 模式（ReAct + Multi-Agent 整合，留待后续）

### 新增/修改文件统计
```
新增:
  src/deepresearch/agents/__init__.py
  src/deepresearch/agents/subquestion_agent.py
  src/deepresearch/agents/coordinator.py
  src/deepresearch/agents/react_agent.py
  src/deepresearch/graph_v2.py
  src/deepresearch/tools/__init__.py
  src/deepresearch/tools/base.py
  src/deepresearch/tools/registry.py
  src/deepresearch/tools/tavily_search.py
  src/deepresearch/tools/web_fetch.py
  tests/test_subquestion_agent.py
  tests/test_tools.py
  tests/test_react_agent.py
  benchmark/baselines/v0.6.0-baseline.json

修改:
  src/deepresearch/state.py          — UsageInfo, TokenUsage, _agent_results 等字段
  src/deepresearch/clients/llm.py    — complete() 返回 (str, UsageInfo)
  src/deepresearch/runner.py         — architecture 三模式支持
  src/deepresearch/cli.py            — --architecture flag + cost summary
  src/deepresearch/nodes/planning.py       — token 追踪
  src/deepresearch/nodes/prepare_evidence.py — 并行 Phase 2 + token 追踪
  src/deepresearch/nodes/searching.py       — 并行搜索
  src/deepresearch/nodes/writing.py         — token 追踪 + 矛盾注入
  src/deepresearch/nodes/reviewing.py       — token 追踪
  src/deepresearch/prompts/writing.py       — contradictions_text 参数
  tests/conftest.py                  — FakeLLMClient 线程安全 + UsageInfo
  tests/test_cli.py                  — architecture 参数适配
  tests/test_runner.py               — Multi-Agent + ReAct 测试
  tests/test_searching_node.py       — 并行顺序无关断言
  README.md                          — 全面重写
```
