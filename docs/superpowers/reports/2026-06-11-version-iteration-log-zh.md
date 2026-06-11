# Deep Research Agent 版本迭代记录

日期：2026-06-11

## 1. 项目概览

Deep Research Agent 是一个基于 LangGraph 的命令行深度研究助手。

用户输入研究问题后，系统自动完成：

```text
拆解子问题 → 搜索收集信息 → 整理研究笔记 → 撰写 Markdown 报告 → 质量审核 → 保存报告
```

技术栈：

- Python + uv
- LangGraph
- DeepSeek OpenAI-compatible API
- Tavily Search API
- Typer CLI
- Rich 输出
- pytest 测试

## 2. v0.1.0：MVP 工程版

### 2.1 目标

从零实现一个能跑通完整研究流程的 CLI MVP。

### 2.2 核心功能

- CLI 接收研究问题
- LangGraph 固定流程：

```text
plan_research → search_web → synthesize_notes → write_report → review_report → save_report
```

- DeepSeek 调用
- Tavily 搜索
- Markdown 报告生成
- Quality Review
- 报告保存到 `reports/`
- 基础来源 URL 校验
- 离线测试

### 2.3 主要设计文档

- `docs/superpowers/specs/2026-06-10-deep-research-agent-design.md`
- `docs/superpowers/plans/2026-06-10-deep-research-agent.md`

### 2.4 验收结果

v0.1.0 工程闭环完成，但真实运行暴露产品体验问题。

主要问题：

- 失败报告不可读
- 失败报告文件名看起来像正常报告
- CLI 进度提示一次性预打印
- 用户看不到中间工作流细节
- 在线报告成功率不稳定

## 3. v0.1.1：可观测性与失败反馈改进

### 3.1 目标

改善 v0.1.0 暴露的失败反馈和运行可观测性问题。

### 3.2 核心改进

- 失败报告中文化
- 失败报告列出失败原因和可用来源 URL
- 失败报告文件名增加 `-failed.md`
- CLI 区分成功与失败：

```text
Saved report to: ...
Report validation failed.
Saved failure report to: ...
```

- 进度提示改成节点实际执行前输出
- `--verbose` 展示中间工作流摘要：
  - 子问题
  - search query
  - 搜索结果数量
  - research notes 数量与置信度
  - review 分数
  - errors

### 3.3 主要设计文档

- `docs/superpowers/specs/2026-06-11-deep-research-agent-v0.1.1-improvements.md`
- `docs/superpowers/plans/2026-06-11-deep-research-agent-v0.1.1-improvements.md`
- `docs/superpowers/reports/2026-06-11-v0.1.1-acceptance-report.md`

### 3.4 验收结果

v0.1.1 改进验收通过。

但在线成功报告生成仍失败。

关键失败原因：

```text
模型生成的报告只在 Sources 部分列出来源，但正文关键论点没有引用来源。
```

结论：

```text
v0.1.1 解决了失败可观测性问题，但没有解决成功报告生成率问题。
```

## 4. v0.1.2：严格编号引用与一次自动重写

### 4.1 目标

解决 writer 输出格式与 validator 引用契约不一致的问题，提高在线成功报告生成率。

### 4.2 核心设计

#### 4.2.1 严格编号引用

正文只能使用编号引用：

```markdown
AI 搜索正在快速发展。[1]
```

Sources 映射 URL：

```markdown
## Sources

[1] https://example.com/source-a
```

#### 4.2.2 严格 citation validator

报告通过必须满足：

1. 有 `## Sources`
2. 正文至少有一个 `[n]`
3. 正文引用编号必须在 Sources 中定义
4. Sources 中每个编号必须被正文引用
5. Sources URL 必须来自 Tavily 搜索结果
6. 正文不允许裸 URL

#### 4.2.3 自动重写一次

流程：

```text
第一次写报告
→ citation validation
→ 如果失败，自动重写一次
→ 再次 citation validation
→ 成功则保存成功报告
→ 仍失败则保存失败报告
```

#### 4.2.4 Review 只审核最终报告

LangGraph 主结构不变：

```text
write_report → review_report → save_report
```

但 `write_report` 内部完成：

```text
write → validate → optional rewrite → validate
```

review 只接收最终报告。

#### 4.2.5 完整失败诊断

retry 后仍失败时，失败报告包含：

- 第一次失败原因
- 第二次失败原因
- body citations
- source citations
- undefined citations
- unused sources
- invalid source URLs
- bare body URLs
- allowed URLs

### 4.3 主要设计文档

- `docs/superpowers/specs/2026-06-11-deep-research-agent-v0.1.2-citation-retry.md`
- `docs/superpowers/plans/2026-06-11-deep-research-agent-v0.1.2-citation-retry.md`
- `docs/superpowers/reports/2026-06-11-v0.1.2-online-acceptance-report.md`
- `docs/superpowers/reports/2026-06-11-v0.1.2-acceptance-report-zh.md`

### 4.4 验收结果

离线测试：

```text
82 passed
```

在线 3 题验收：

| 问题 | 结果 | Retry | Review |
|---|---|---:|---|
| AI 搜索引擎的发展趋势 | success | 是，2 attempts | score=88 |
| LangGraph 和 CrewAI 的适用场景 | success | 否，1 attempt | score=92 |
| 新能源汽车固态电池商业化进展 | success | 否，1 attempt | score=95 |

通过标准：

```text
至少 2/3 成功。
```

实际结果：

```text
3/3 成功。
```

结论：

```text
v0.1.2 验收通过。
```

## 5. 版本能力对比

| 能力 | v0.1.0 | v0.1.1 | v0.1.2 |
|---|---|---|---|
| CLI 运行 | ✅ | ✅ | ✅ |
| LangGraph 固定流程 | ✅ | ✅ | ✅ |
| Tavily 搜索 | ✅ | ✅ | ✅ |
| DeepSeek 写作 | ✅ | ✅ | ✅ |
| Quality Review | ✅ | ✅ | ✅ |
| 基础来源校验 | ✅ | ✅ | ✅ |
| 失败报告中文化 | ❌ | ✅ | ✅ |
| `-failed.md` 文件名 | ❌ | ✅ | ✅ |
| 节点级进度提示 | ❌ | ✅ | ✅ |
| verbose 中间产物摘要 | ❌ | ✅ | ✅ |
| 严格编号引用 | ❌ | ❌ | ✅ |
| Citation validator | 基础 URL | 基础 URL | 严格 `[n]` |
| 自动重写一次 | ❌ | ❌ | ✅ |
| 完整失败诊断 | ❌ | 部分 | ✅ |
| 在线成功率验收 | 未通过 | 未通过 | 通过 |

## 6. 当前版本状态

当前版本：

```text
v0.1.2
```

当前分支：

```text
feature/v0.1.2-citation-retry
```

当前状态：

```text
离线测试通过，在线验收通过。
```

## 7. 后续路线建议

### v0.2：研究质量增强

建议方向：

- 一个子问题多个 search queries
- 中英文双语搜索
- 来源去重
- 来源质量评分
- 搜索结果 rerank
- review 失败后补充搜索
- 保存 trace JSON

### v0.3：产品化体验

建议方向：

- YAML 任务配置
- 报告模板
- 历史报告索引
- PDF/DOCX 导出
- Web UI
- 多模型配置
- 成本统计

## 8. 总结

Deep Research Agent 经过三个版本迭代：

```text
v0.1.0：完成工程 MVP
v0.1.1：提升失败反馈和可观测性
v0.1.2：统一引用契约并通过在线验收
```

当前 v0.1.2 已经具备：

- 完整在线研究流程
- 严格来源引用
- 自动重写一次
- 质量审核
- 失败诊断
- verbose 可观测性
- 离线测试覆盖
- 在线 3 题验收通过

可以作为后续质量增强和产品化工作的稳定基础。
