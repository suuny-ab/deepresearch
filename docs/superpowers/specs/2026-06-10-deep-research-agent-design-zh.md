# 深度研究智能体设计

日期：2026-06-10

## 1. 概述

基于 LangGraph 构建一个 Python 命令行深度研究智能体。用户通过命令行参数提供研究问题，智能体执行固定工作流：

1. 将问题拆解为子问题
2. 使用 Tavily 搜索网络
3. 综合研究笔记
4. 撰写结构化 Markdown 报告
5. 审查报告质量
6. 保存并打印最终报告

第一版为 MVP 稳定版本，优先考虑可靠性、可观测性、清晰的状态转换、基于来源的写作和可测试性，而非自主多智能体行为或迭代自我改进。

已确认的决策：

- 项目类型：Python CLI 工具
- 包管理器：uv
- 工作流框架：LangGraph
- 搜索后端：Tavily Search API
- LLM 提供商：通过 OpenAI 兼容 API 调用 DeepSeek v4 pro
- CLI 输入：命令参数，例如 `deepsearch "研究问题"`
- 输出：在终端打印完整 Markdown 报告并保存至 `reports/` 目录
- 第一版工作流：固定线性 MVP 流水线

## 2. 目标

第一版应实现：

- 从 CLI 接收研究问题
- 运行确定性的 LangGraph 工作流
- 使用 DeepSeek 进行规划、综合、撰写和审查
- 使用 Tavily 收集网络搜索结果
- 生成结构化 Markdown 研究报告
- 在报告中包含来源 URL
- 将报告保存到磁盘
- 在终端打印完整报告
- 清晰地暴露失败，而非假装成功
- 提供足够的测试以验证核心工程行为

## 3. 非目标

第一版不会实现：

- Web 界面
- 数据库持久化
- 向量数据库或本地文档 RAG
- 用户账户
- 交互式聊天模式
- YAML/JSON 任务文件
- 自动研究重试循环
- 多智能体协作
- 并发搜索
- PDF/DOCX 导出
- 搜索结果缓存
- 历史报告索引

这些是可能的后续扩展。

## 4. 架构

项目使用四层架构：

```text
CLI 层
  ↓
LangGraph 工作流层
  ↓
节点业务逻辑层
  ↓
外部服务适配器层
```

### 4.1 CLI 层

CLI 接收研究问题和可选的运行时参数。它加载配置、初始化工作流、执行工作流、打印进度、打印最终 Markdown 报告，并显示保存的输出路径。

示例：

```bash
deepsearch "分析 2026 年 AI 搜索引擎的发展趋势"
```

### 4.2 LangGraph 工作流层

图为固定线性工作流：

```text
START
  → plan_research（规划研究）
  → search_web（搜索网络）
  → synthesize_notes（综合笔记）
  → write_report（撰写报告）
  → review_report（审查报告）
  → save_report（保存报告）
END
```

MVP 不根据审查结果分支。审查结果会被保留和展示，但即使审查未通过，报告仍会保存。

### 4.3 节点业务逻辑层

每个节点是一个聚焦的函数，接受并返回 `ResearchState` 更新。

节点：

| 节点 | 职责 |
|---|---|
| `plan_research` | 将用户问题拆解为子问题和搜索查询 |
| `search_web` | 运行 Tavily 搜索并规范化结果 |
| `synthesize_notes` | 将搜索结果转化为基于来源的研究笔记 |
| `write_report` | 生成最终结构化 Markdown 报告 |
| `review_report` | 审查报告质量并生成结构化反馈 |
| `save_report` | 持久化 Markdown 报告并返回输出路径 |

### 4.4 外部服务适配器层

外部服务通过适配器隔离：

| 适配器 | 职责 |
|---|---|
| `llm_client` | 通过 OpenAI 兼容 API 调用 DeepSeek v4 pro |
| `search_client` | 调用 Tavily Search API |
| `report_writer` | 生成文件名并保存 Markdown 文件 |
| `config` | 加载默认值、环境变量和 CLI 覆盖 |

这使工作流代码独立于供应商特定的 API。

## 5. 初始目录结构

```text
deepsearch/
  pyproject.toml
  README.md
  .env.example
  src/
    deepresearch/
      __init__.py
      cli.py
      config.py
      graph.py
      state.py
      nodes/
        __init__.py
        planning.py
        searching.py
        synthesizing.py
        writing.py
        reviewing.py
        saving.py
      clients/
        __init__.py
        llm.py
        tavily.py
      prompts/
        __init__.py
        planning.py
        synthesizing.py
        writing.py
        reviewing.py
      utils/
        __init__.py
        citations.py
        filenames.py
  tests/
    test_state.py
    test_filenames.py
    test_graph_structure.py
    test_report_writer.py
    test_json_parsing.py
  reports/
    .gitkeep
  docs/
    superpowers/
      specs/
```

## 6. 数据模型

LangGraph 状态使用 `TypedDict`，结构化中间对象使用 Pydantic 模型。

### 6.1 ResearchState

```python
class ResearchState(TypedDict, total=False):
    question: str
    subquestions: list[SubQuestion]
    search_results: list[SearchResult]
    notes: list[ResearchNote]
    report_markdown: str
    review: ReviewResult
    output_path: str
    errors: list[str]
```

### 6.2 SubQuestion

由 `plan_research` 生成。

```python
class SubQuestion(BaseModel):
    id: str
    question: str
    search_query: str
    rationale: str
```

### 6.3 SearchResult

来自 Tavily 的规范化结果。

```python
class SearchResult(BaseModel):
    subquestion_id: str
    title: str
    url: str
    content: str
    score: float | None = None
    published_date: str | None = None
```

### 6.4 ResearchNote

基于来源的综合笔记。

```python
class ResearchNote(BaseModel):
    subquestion_id: str
    key_findings: list[str]
    source_urls: list[str]
    confidence: Literal["low", "medium", "high"]
```

### 6.5 ReviewResult

报告审查输出。

```python
class ReviewResult(BaseModel):
    passed: bool
    score: int
    issues: list[str]
    suggestions: list[str]
```

实现应将 `score` 约束在 0-100 范围内。

## 7. 引用策略

报告只能引用出现在 `SearchResult.url` 中的 URL。`write_report` 的提示必须要求基于来源的论断和 `Sources` 部分。

首选报告格式：

```markdown
AI 搜索引擎正在从"链接排序"转向"答案生成"。[^1]

[^1]: https://example.com/article
```

MVP 也可以使用内联 Markdown 链接（如果更简单）。关键规则是：不编造 URL。

## 8. 节点行为

### 8.1 plan_research（规划研究）

输入：

- `question`

输出：

- `subquestions`

行为：

- 调用 DeepSeek v4 pro
- 生成 3-6 个子问题，受配置上限约束
- 为每个子问题生成一个 Tavily 搜索查询
- 返回解析为 `SubQuestion` 的结构化 JSON

失败处理：

- 如果 JSON 解析失败，回退为使用原始问题作为问题和搜索查询的单个子问题
- 在 `errors` 中记录解析错误

### 8.2 search_web（搜索网络）

输入：

- `subquestions`

输出：

- `search_results`

行为：

- 为每个 `search_query` 调用 Tavily
- 默认每个查询返回 5 条结果
- 将结果规范化为 `SearchResult`

失败处理：

- 如果一个查询失败，记录错误并继续
- 如果所有查询失败或没有可用结果，以明确的致命错误停止工作流

MVP 按顺序搜索以便调试。

### 8.3 synthesize_notes（综合笔记）

输入：

- `question`
- `subquestions`
- `search_results`

输出：

- `notes`

行为：

- 按 `subquestion_id` 分组搜索结果
- 调用 DeepSeek 提取关键发现和来源 URL
- 要求每个发现可追溯到提供的 URL
- 将置信度标记为 `low`、`medium` 或 `high`

失败处理：

- 如果结构化解析失败，从结果标题/内容生成保守的回退笔记
- 将回退置信度标记为 `low`
- 记录错误

### 8.4 write_report（撰写报告）

输入：

- `question`
- `subquestions`
- `notes`
- `search_results`

输出：

- `report_markdown`

报告结构：

```markdown
# <研究问题标题>

## 摘要

## 关键结论

## 背景与问题拆解

## 深度分析

### 1. <子问题一>

### 2. <子问题二>

## 风险、不确定性与不同观点

## 结论

## Sources
```

规则：

- 每个关键结论应包含至少一个来源 URL
- 来源必须来自 `search_results`
- 如果证据不足，应明确说明不确定性
- 不编造 URL 或无支撑的论断

失败处理：

- 如果笔记或搜索结果不足，生成一个失败风格的 Markdown 报告，解释局限性而非编造发现

### 8.5 review_report（审查报告）

输入：

- `question`
- `report_markdown`
- `search_results`

输出：

- `review`

行为：

- 调用 DeepSeek 审查质量
- 返回 `passed`、`score`、`issues` 和 `suggestions`

审查标准：

- 与原始问题的相关性
- 子问题的覆盖度
- 基于来源的论断
- 避免无支撑的断言
- Markdown 可读性
- 清晰的结论和不确定性讨论

MVP 不使用审查结果进行分支。

### 8.6 save_report（保存报告）

输入：

- `question`
- `report_markdown`
- `review`

输出：

- `output_path`

行为：

- 确保输出目录存在
- 生成安全的时间戳文件名
- 写入 UTF-8 Markdown
- 在保存的报告中追加 `Quality Review`

示例路径：

```text
reports/2026-06-10-153000-ai-search-trends.md
```

## 9. 配置

配置优先级：

```text
默认值 < 环境/.env < CLI 参数
```

`.env.example`：

```env
# DeepSeek OpenAI 兼容 API
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro

# Tavily Search API
TAVILY_API_KEY=your_tavily_api_key

# 运行时默认值
DEEPRESEARCH_MAX_SUBQUESTIONS=5
DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY=5
DEEPRESEARCH_OUTPUT_DIR=reports
```

## 10. CLI 接口

基础命令：

```bash
deepsearch "你的研究问题"
```

可选参数：

| 参数 | 默认值 | 描述 |
|---|---:|---|
| `question` | 必填 | 研究问题 |
| `--max-subquestions` | `5` | 最大生成的子问题数 |
| `--results-per-query` | `5` | 每个查询的 Tavily 结果数 |
| `--output-dir` | `reports` | Markdown 输出目录 |
| `--model` | `DEEPSEEK_MODEL` | 覆盖默认 DeepSeek 模型 |
| `--verbose` | `false` | 打印调试详情 |

推荐库：

- `typer` 用于 CLI 解析
- `rich` 用于进度和 Markdown 显示

`pyproject.toml` 应暴露：

```toml
[project.scripts]
deepsearch = "deepresearch.cli:app"
```

## 11. 错误处理

### 11.1 致命错误

致命错误以清晰的消息终止工作流：

| 错误 | 示例 |
|---|---|
| 缺少 API 密钥 | `DEEPSEEK_API_KEY` 或 `TAVILY_API_KEY` 缺失 |
| LLM 不可用 | 认证失败、超时、错误模型 |
| 搜索不可用 | 所有 Tavily 搜索失败 |
| 报告写入失败 | 输出目录权限错误 |

CLI 应显示清晰的面向用户的错误，在正常模式下避免不必要的堆栈跟踪。

### 11.2 非致命错误

非致命错误存储在 `ResearchState.errors` 中，工作流在可能时继续：

| 错误 | 处理方式 |
|---|---|
| 一个搜索查询失败 | 继续其他查询 |
| LLM JSON 解析失败 | 使用回退数据 |
| 一个子问题缺少好的来源 | 低置信度笔记 |
| 审查分数低 | 保存报告并附带审查反馈 |

### 11.3 项目异常

使用项目特定的异常类型：

```python
class LLMError(Exception):
    pass

class SearchError(Exception):
    pass

class ReportWriteError(Exception):
    pass
```

## 12. LLM 输出解析

MVP 解析策略：

```text
尝试将完整响应解析为 JSON
  ↓ 失败
尝试提取围栏 ```json 代码块
  ↓ 失败
使用保守回退
```

Pydantic 验证解析后的结构。

第一版避免实现复杂的 JSON 修复智能体。

## 13. 可观测性

正常模式应打印进度：

```text
[1/6] 规划研究...
[2/6] 搜索网络...
[3/6] 综合笔记...
[4/6] 撰写报告...
[5/6] 审查报告...
[6/6] 保存报告...
```

详细模式可打印：

- 生成的子问题
- 搜索查询
- 结果数量
- 审查分数和问题

绝不打印：

- API 密钥
- 密钥
- 默认情况下的完整原始 API 响应
- 过长的搜索载荷

## 14. 测试策略

使用 `pytest`。

### 14.1 单元测试

`test_state.py`：

- 验证 `SubQuestion`
- 验证 `SearchResult`
- 验证 `ResearchNote` 置信度枚举
- 验证 `ReviewResult` 分数范围

`test_filenames.py`：

- 安全 slug 生成
- 特殊字符移除
- 空或非 ASCII 问题有回退文件名
- 文件名包含时间戳

`test_report_writer.py`：

- 创建输出目录
- 写入 UTF-8 Markdown
- 返回已存在的路径
- 追加质量审查

`test_graph_structure.py`：

- 图编译
- 节点顺序正确

`test_json_parsing.py`：

- 解析原始 JSON
- 解析围栏 JSON 代码块
- 无效 JSON 时回退
- 处理缺少的必填字段

### 14.2 离线集成测试

使用伪客户端运行完整图，无需外部 API 调用。

预期行为：

- 输入问题进入状态
- 伪规划返回子问题
- 伪搜索返回结果
- 生成笔记
- 生成 Markdown 报告
- 生成审查
- 保存报告文件

### 14.3 可选在线冒烟测试

需要真实凭据的手动命令：

```bash
uv run deepsearch "AI 搜索引擎的发展趋势"
```

目的：

- 确认 CLI 启动
- 确认环境变量
- 确认 DeepSeek 连接
- 确认 Tavily 连接
- 确认图端到端运行
- 确认 Markdown 保存和打印

这不属于默认测试，因为它依赖外部 API、网络、成本和非确定性的模型输出。

## 15. 验收标准

运行：

```bash
uv run deepsearch "分析 AI 搜索引擎在 2026 年的发展趋势"
```

应：

- 显示六个进度阶段
- 生成 Markdown 报告
- 在终端打印报告
- 将报告保存至 `reports/`
- 打印保存路径

报告应包含：

- 标题
- 摘要
- 关键发现
- 背景与问题拆解
- 深度分析
- 风险、不确定性或不同观点
- 结论
- 来源
- 质量审查

引用验收：

- 搜索成功时至少 3 个来源 URL
- Sources 部分列出引用的 URL
- 关键论断包含引用或来源链接
- 不编造搜索结果之外的 URL

错误验收：

- 缺少 `TAVILY_API_KEY` 给出清晰错误
- 缺少 `DEEPSEEK_API_KEY` 给出清晰错误
- 一个搜索查询失败不会中止所有工作
- 所有搜索失败时产生清晰的失败提示而非虚假报告

## 16. 第一版质量策略

MVP 质量通过以下方式保证：

- 固定、可预测的工作流
- 结构化的中间数据
- 来源 URL 约束
- 明确的质量审查节点
- 保守的回退行为
- 清晰的致命与非致命错误区分
- 单元测试和离线集成测试
- 可选的真实 API 冒烟测试

MVP 不保证完美的事实准确性或专家级的研究深度。它保证的是一个稳定的、可检查的、基于来源的研究流水线，可以在后续扩展。

## 17. 未来扩展

可能的 MVP 后改进：

1. 审查失败条件循环
2. 根据审查反馈添加额外搜索查询
3. 并发 Tavily 搜索
4. 多个搜索后端
5. 可配置的报告模板
6. 搜索结果缓存
7. YAML 研究任务文件
8. Web 界面
9. 多智能体规划/审查
10. PDF/DOCX 导出
11. 历史报告索引
12. 来源可信度评分
