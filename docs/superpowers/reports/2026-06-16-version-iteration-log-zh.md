# Deep Research Agent 版本迭代记录

日期：2026-06-16
覆盖版本：v0.1.0 ~ v0.6.x

## 1. 项目概览

Deep Research Agent 是一个基于 LangGraph 的命令行深度研究助手。

用户输入研究问题后，系统自动完成：

```text
拆解子问题 → 搜索收集信息 → 提取证据 → 撰写 Markdown 报告 → 质量审核 → 保存报告
```

技术栈：Python + uv + LangGraph + DeepSeek + Tavily + Pydantic + Typer + Rich + pytest + LangSmith

---

## 2. v0.1.0：MVP 工程版（2026-06-10）

### 目标

从零实现能跑通完整研究流程的 CLI MVP。

### 核心功能

- CLI 接收研究问题
- LangGraph 固定 6 步流程：plan → search → synthesize → write → review → save
- DeepSeek 调用 + Tavily 搜索
- Markdown 报告生成 + Quality Review
- 基础来源 URL 校验 + 离线测试

### 主要设计文档

- `docs/superpowers/specs/2026-06-10-deep-research-agent-design.md`

---

## 3. v0.1.1：可观测性与失败反馈改进（2026-06-11）

### 目标

改善 v0.1.0 暴露的失败反馈和运行可观测性问题。

### 核心改进

- 失败报告中文化 + `-failed.md` 文件名
- 节点级渐进式进度打印（不再一次性预打印）
- `--verbose` 展示中间产物摘要

### 验收

离线测试通过，但在线成功报告生成率未达标。

---

## 4. v0.1.2：严格编号引用与自动重写（2026-06-11）

### 目标

解决 writer 输出格式与 validator 引用契约不一致的问题。

### 核心改进

- 严格 `[N]` 编号引用 + `## Sources` 映射 URL
- 7 维度 citation validator（缺少 Sources、裸 URL、重复编号、未定义引用、无效 URL、未使用来源等）
- 自动重写一次：write → validate → fail → rewrite → validate
- 完整失败诊断报告

### 验收

3/3 在线验收通过。首次建立可验证的质量底线。

---

## 5. v0.2：基于提取的证据管线（2026-06-11）

### 目标

从"搜索摘要直接写作"升级为"提取全文 → 生成证据卡 → 写作"。

### 核心改进

- Tavily extract 获取网页全文
- EvidenceCard 模型：结构化证据卡（claim + source + confidence）
- 来源质量评分（硬编码域名评分：office=95, blog=30...）
- 中英文双语搜索（每个子问题 2-3 个不同角度的 query）
- SearchResult 去重 + 域名多样性选择

### 设计文档

- `docs/superpowers/specs/2026-06-11-deep-research-agent-v0.2-evidence-pipeline.md`

---

## 6. v0.3：多源交叉验证（2026-06-12）

### 哲学转变

```
旧: 来源权威 → 内容可信（入口预判，硬编码域名评分）
新: 多源交叉验证 → 结论可查（出口检验，计算多源收敛信号）
```

### 核心改进

- 删除整个 `source_quality.py`（硬编码域名评分）
- 新增 `corroboration_level`（single_source / weakly_corroborated / strongly_corroborated）
- 来源选择改为 Tavily 相关性 + 域名多样性（不预判可靠性）
- 代码层后校验：验证源 URL 必须真实存在、同域名不算交叉验证

### 设计哲学

三个原则：
1. 入口不设卡，出口严把关
2. 信论断不信任来源——验证粒度是 claim 级别
3. 多源交叉验证是第一性原理——3 个独立域名同时说同一件事，串通出错的概率接近零

### 设计文档

- `docs/superpowers/specs/2026-06-12-deep-research-agent-v0.3-cross-validation.md`

---

## 7. v0.3.1：子问题上下文恢复（2026-06-12）

### 问题

v0.3 的证据 prompt 只传递了 bare `subquestion_id`，丢失了子问题文本。对比型话题（LangGraph vs CrewAI）受影响最大——LLM 在无上下文池子里做交叉验证。

### 修复

- 在证据 prompt 中按子问题分组呈现来源，每组包含子问题原文
- 对比型话题卡片数从 4 恢复到 12

---

## 8. v0.4：两阶段证据管线 + A/B 测试基础设施（2026-06-12）

### 问题

v0.3 将提取（claim extraction）和交叉验证捆在一次 LLM 调用中。两个任务认知需求互斥——提取倾向发散（越多越好），交叉验证倾向收敛（保守标记）。

### 核心改进

```
Phase 1（1 次 LLM 调用）：纯提取 ExtractedClaim[]，不含交叉验证指令
Phase 2（N 次 LLM 调用）：每个子问题独立交叉验证 → EvidenceCard[]
```

- 新增 `--save-search` / `--replay-search` / `--compare` A/B 测试基础设施
- 自动监测断言（每来源至少 1 条 claim、交叉验证率 ≥ 60%、分布偏差 ≤ 3x）

### 设计文档

- `docs/superpowers/specs/2026-06-12-deep-research-agent-v0.4-two-phase-evidence.md`

---

## 9. v0.5.1：Review 评分 Rubric（2026-06-12）

### 问题

Review 评分无锚点（LLM 凭感觉打 0-100），入参使用了错误的 URL 集合（search_results 而非 evidence_cards）。

### 核心改进

- 五维度加权 rubric：来源支撑 30% + 交叉验证覆盖 20% + 完整性 20% + 结构 15% + 相关性 15%
- 入参从 search_results 改为 evidence_cards

### 设计文档

- `docs/superpowers/specs/2026-06-12-deep-research-agent-v0.5.1-review-rubric.md`

---

## 10. v0.5.2：Review 反馈闭环 + 提取数量期望（2026-06-12）

### 核心改进

- Review 评分 < 70 触发自动重写（含 review issues/suggestions），最多 1 次
- Phase 1 提取 prompt 增加 soft quantity expectation（2-4 claims/source）
- v0.3 记录的 7 个 pending issues 全部解决

### 设计文档

- `docs/superpowers/specs/2026-06-12-deep-research-agent-v0.5.2-pending-issues.md`

---

## 11. v0.6：架构简化 + LangSmith 集成（2026-06-13）

### 问题

~30% 代码服务于自建观测和测试基础设施（metrics.py、verbose.py、benchmark/ 目录等），与 Agent 核心功能深度耦合。

### 核心改进

- 删除 6 个 CLI 参数（--verbose、--dry-run、--output、--save-search、--replay-search、--compare）
- 删除 4 个数据模型（RunArtifact、RunMeta、StandardMetrics、evidence_metrics）
- 删除 2 个源文件（metrics.py、verbose.py）和整个 benchmark/ 目录
- 引入 LangSmith 自动 tracing
- 图结构回归单一标准拓扑

### 设计文档

- `docs/superpowers/specs/2026-06-13-simplify-architecture-langsmith-integration-design.md`

---

## 12. v0.6.x：多 Agent 架构 + ReAct Agent + 能力上限评估（2026-06-15~16）

### 12.1 三模式执行架构

在原有固定流水线基础上，新增两种执行模式：

```
pipeline:      plan → search → evidence(2-phase) → write → review ⇄ save
multi-agent:   plan → [Agent₁ | Agent₂ | Agent₃] → coordinator → write → review ⇄ save
react:         Think ⇄ Act(search/fetch/write) — 自主工具调用循环
```

CLI 通过 `--architecture` 参数切换。

### 12.2 Multi-Agent 架构

- 每个子问题分配独立 Agent（search → extract → validate），ThreadPoolExecutor 并行
- Coordinator 合并 evidence_cards，执行跨 Agent 交叉验证和矛盾检测
- 故障隔离：单 Agent 崩溃不影响其他

### 12.3 ReAct Agent

- 自主工具调用循环（TavilySearchTool + WebFetchTool）
- 搜索去重、饱和检测、max_iterations=15 约束
- 搜索结果从 ReActStep 构造，供评估使用

### 12.4 工具体系

- `Tool` Protocol（name、description、parameters JSON Schema、execute）
- `ToolRegistry`：工具注册、按名查找、错误处理
- 实现：TavilySearchTool、WebFetchTool

### 12.5 三架构能力上限横向对比

- 五维度评估体系：事实深度、探索广度、交叉验证强度、结构完整性、不确定性诚实度
- 所有指标从最终报告文本提取（架构无关）
- 27 轮真实 API 运行（3 题 × 3 架构 × 3 轮）
- 双 Key Pool 自动故障切换
- 核心结论：**无银弹**——三种架构在不同问题类型上各有优势
  - Pipeline：确定型/对比型最强，强印证率 8.7%
  - Multi-Agent：声明数最高（38.6），覆盖度最高
  - React：诚实度最高（4.8），速度最快（101s），成本最低（$0.02），探索广度 Q3 最高（12.3 域名）

### 12.6 基础设施增强

- Phase 2 并行化（ThreadPoolExecutor，5 子问题 ~15s → ~3s）
- Token 成本追踪（UsageInfo + TokenUsage 模型，每节点精确追踪）
- 搜索并发化（子问题间并行搜索）
- Tavily Key Pool（双 Key 自动故障切换，~1050 次调用容量）

### 设计文档

- `docs/superpowers/specs/2026-06-16-multi-agent-architecture-design.md`
- `docs/superpowers/specs/2026-06-16-capability-evaluation-design.md`
- `docs/superpowers/plans/2026-06-15-resume-optimization-plan.md`
- `benchmark/capability_results/FINAL_REPORT.md`

---

## 13. 版本能力演进总览

| 能力 | v0.1 | v0.2 | v0.3 | v0.4 | v0.5 | v0.6 |
|------|------|------|------|------|------|------|
| LangGraph 流水线 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Tavily 搜索 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 全文提取 | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| 来源质量评分 | — | ✅ | ❌ 删除 | — | — | — |
| 多源交叉验证 | — | — | ✅ | ✅ | ✅ | ✅ |
| 两阶段证据管线 | — | — | — | ✅ | ✅ | ✅ |
| 严格 [N] 引用 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 自动重写 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Review 反馈闭环 | — | — | — | — | ✅ | ✅ |
| Review Rubric | — | — | — | — | ✅ | ✅ |
| 多 Agent 协作 | — | — | — | — | — | ✅ |
| ReAct 自主循环 | — | — | — | — | — | ✅ |
| 工具体系 | — | — | — | — | — | ✅ |
| 并行执行 | — | — | — | — | — | ✅ |
| Token 成本追踪 | — | — | — | — | — | ✅ |
| Key Pool | — | — | — | — | — | ✅ |
| 三架构评估 | — | — | — | — | — | ✅ |
| LangSmith tracing | — | — | — | — | — | ✅ |

---

## 14. 关键架构决策时间线

```
v0.1.0  建立四层架构（CLI → Graph → Node → Adapter）
v0.1.2  引入 [N] 引用契约 → 可验证的质量底线
v0.3    删除域名评分 → 交叉验证替代源预判（最大哲学转变）
v0.4    提取与验证解耦 → 两阶段管线（消除认知冲突）
v0.5.2  Review 反馈闭环 → review 从"观测"变成"行动"
v0.6    删除 30% 代码 → 拥抱 LangSmith（平台能力 > 自建）
v0.6.x  多 Agent + ReAct + 能力上限评估 → 三架构并存，"无银弹"
```

---

## 15. 总结

Deep Research Agent 经过 12 个版本迭代，从单 Agent 固定流水线演进为三架构并存的研究系统。

核心演进路线：

```text
工程闭环(v0.1) → 引用质量(v0.1.2) → 证据哲学(v0.3) → 管线解耦(v0.4)
→ 质量闭环(v0.5.2) → 简化+v0.6 → 多Agent+ReAct+评估(v0.6.x)
```

当前 v0.6.x 具备：
- 三种执行架构（Pipeline / Multi-Agent / ReAct）
- 两阶段证据管线 + 多源交叉验证
- 严格引用校验 + 自动重写
- Review 五维 Rubric + 反馈闭环
- 15 维度确定性评估（底线检查）
- 五维度能力上限评估（架构对比）
- Token 成本追踪 + Key Pool 自动切换
- LangSmith tracing
- 195 离线测试（<2s）
- 双语言（中英文）研究能力
