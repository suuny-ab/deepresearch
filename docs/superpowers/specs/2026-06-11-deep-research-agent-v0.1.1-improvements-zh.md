# Deep Research Agent v0.1.1 改进设计

日期：2026-06-11

## 1. 背景

v0.1.0 MVP 满足了原始的工程验收标准：它运行固定的 LangGraph 工作流，使用 DeepSeek 和 Tavily，保存 Markdown 报告，强制执行来源 URL 约束，包含质量审查输出，并且通过了离线测试。

实际使用暴露了几个产品和可观察性问题，应该在更广泛使用之前在 v0.1.1 中解决：

1. 进度消息在工作流实际运行之前一次性全部打印。
2. 当报告验证失败时，保存的失败报告难以理解。
3. 失败报告没有显示导致拒绝的具体非法 URL。
4. 失败报告文件名看起来像正常报告文件名。
5. CLI 输出无法区分成功报告和验证失败报告。
6. 用户无法从终端轻松检查中间工作流输出。

v0.1.1 的目标是在不改变核心 MVP 工作流或添加自动研究循环的情况下，改进反馈、可观察性和失败清晰度。

## 2. 目标

v0.1.1 应该：

- 保持现有的固定 LangGraph 管道。
- 保持现有的来源安全行为。
- 使进度输出诚实且有用。
- 使验证失败对用户可理解。
- 使失败的报告文件在视觉上与成功报告可区分。
- 改进 `--verbose` 输出，以便用户可以检查关键中间工件。
- 保留所有当前测试并添加新行为的回归测试。

## 3. 非目标

v0.1.1 将不会实现：

- 验证失败后的自动报告重写。
- 审查驱动的重试循环。
- 审查后的额外 Tavily 搜索。
- 多智能体协作。
- 并发搜索。
- Web UI。
- 追踪 JSON 文件。
- PDF/DOCX 导出。
- 搜索结果缓存。

这些是 v0.2 或更高版本的候选功能。

## 4. 验收决策背景

当前的 v0.1.0 版本被接受为 MVP 工程实现，但它存在产品质量问题。v0.1.1 是一个改进包，而不是重新定义原始 MVP。

最重要的区别：

- v0.1.0 正确拒绝发布不安全的报告。
- v0.1.1 应该清楚地解释这些拒绝，并使运行时行为更容易检查。

## 5. 设计概述

v0.1.1 引入了三个小的设计更改：

1. **运行状态模型**
   - 向最终状态添加轻量级元数据，指示输出是成功报告还是失败的验证工件。

2. **改进的报告验证反馈**
   - 保留结构化的验证失败详细信息，例如非法 URL 和原因代码。
   - 在面向用户的失败报告中呈现这些详细信息。

3. **CLI 可观察性改进**
   - 用诚实的工作流开始/结束消息或节点感知进度替换误导性的预打印进度。
   - 扩展 `--verbose` 以打印子问题、搜索查询、结果计数、笔记计数、审查分数和错误。

## 6. 报告验证失败处理

### 6.1 当前行为

当前的失败报告如下所示：

```markdown
# Research report not published

The report generation failed validation, so no unsupported report was published from that generation.
Invalid source URLs were detected in the generated report, so no report was published from that generation.

Only the following source URLs were available for a valid report:

- https://...
```

问题：

- 在其他面向中文的工作流中仅输出英文。
- 没有列出非法 URL。
- 没有告诉用户重试是否有帮助。
- 无法将保存的文件与成功报告区分开来。

### 6.2 新的失败报告格式

当生成的报告验证失败时，保存一个中文面向用户的失败报告：

```markdown
# 研究报告生成失败

本次报告没有发布，因为生成内容未通过来源校验。

## 失败原因

模型生成的报告包含未被搜索结果支持的来源 URL，因此系统拒绝保存该报告正文。

## 非法来源 URL

- https://invalid.example/source-a
- https://invalid.example/source-b

## 可用来源 URL

以下 URL 来自本次 Tavily 搜索结果，报告只能引用这些来源：

- https://allowed.example/source-1
- https://allowed.example/source-2

## 你可以怎么做

- 重新运行一次同样的问题。
- 使用更具体的研究问题。
- 增加 `--results-per-query` 以提供更多可用来源。
- 使用 `--verbose` 查看子问题、搜索 query 和搜索结果数量。
```

对于其他验证失败，使用相同的结构但更改原因：

| 失败 | 原因文本 |
|---|---|
| 非法 URL | `模型生成的报告包含未被搜索结果支持的来源 URL。` |
| 无引用 | `模型生成的报告没有在正文中引用任何可用来源。` |
| 缺少 Sources 部分 | `模型生成的报告缺少 ## Sources 来源部分。` |
| 正文引用缺失 | `模型生成的报告只在 Sources 部分列出来源，但正文关键论点没有引用来源。` |

### 6.3 结构化验证结果

引入一个小的内部模型或数据类：

```python
@dataclass(frozen=True)
class ReportValidationFailure:
    reason: Literal[
        "invalid_urls",
        "no_citations",
        "missing_sources_section",
        "missing_body_citations",
    ]
    message: str
    invalid_urls: list[str]
    allowed_urls: list[str]
```

除非有用，否则此对象不需要成为公共状态模型的一部分。它可以保留在 `nodes/writing.py` 内部。

## 7. 失败报告文件名

### 7.1 当前行为

成功和失败的输出都使用如下文件名：

```text
reports/2026-06-11-092627-ai.md
```

### 7.2 新行为

成功报告保持现有格式：

```text
reports/2026-06-11-093242-ai.md
```

验证失败报告使用：

```text
reports/2026-06-11-092627-ai-failed.md
```

### 7.3 设计

扩展文件名/报告写入器实用程序以接受状态标志：

```python
make_report_filename(question: str, *, failed: bool = False, now: datetime | None = None) -> str
```

行为：

- `failed=False`：`2026-06-11-093242-ai.md`
- `failed=True`：`2026-06-11-093242-ai-failed.md`

`save_report()` 应该接受相同的标志并返回最终路径。

## 8. CLI 成功与失败消息传递

### 8.1 当前行为

CLI 总是打印：

```text
Saved report to: reports/xxx.md
```

### 8.2 新行为

如果报告生成成功：

```text
Saved report to: reports/2026-06-11-093242-ai.md
```

如果报告验证失败：

```text
Report validation failed.
Saved failure report to: reports/2026-06-11-092627-ai-failed.md
Run again or use --verbose to inspect intermediate workflow details.
```

### 8.3 状态信号

保存节点需要知道它是在保存成功报告还是失败报告。

向 `ResearchState` 添加一个字段：

```python
report_status: Literal["success", "failed_validation"]
```

规则：

- `write_report` 在报告通过验证时设置 `report_status="success"`。
- `write_report` 在用失败报告替换报告时设置 `report_status="failed_validation"`。
- `save_report` 使用 `report_status` 选择文件名后缀。
- CLI 使用 `report_status` 选择终端消息。

如果缺少该字段以保持向后兼容性，则将其视为 `"success"`。

## 9. 进度显示

### 9.1 当前行为

CLI 在调用图之前打印所有进度阶段：

```text
[1/6] Planning research...
[2/6] Searching web...
[3/6] Synthesizing notes...
[4/6] Writing report...
[5/6] Reviewing report...
[6/6] Saving report...
```

然后实际工作流运行。

这是误导性的，因为终端在任何工作可见完成之前似乎就达到了 `[6/6]`。

### 9.2 v0.1.1 最低行为

用诚实的工作流级别输出替换假的每阶段输出：

```text
Starting research workflow...
This may take a few minutes while calling DeepSeek and Tavily.
```

完成后：

```text
Research workflow completed.
Saved report to: ...
```

这是最低可接受的 v0.1.1 修复，因为它避免了虚假的精确性。

### 9.3 可选的节点感知进度

如果实现简单，使用 LangGraph 流式传输或节点包装器在每个阶段实际开始时打印：

```text
[1/6] Planning research...
[2/6] Searching web...
[3/6] Synthesizing notes...
[4/6] Writing report...
[5/6] Reviewing report...
[6/6] Saving report...
```

与 v0.1.0 不同，每一行必须在相应节点运行之前立即打印。

推荐实现：

- 在 CLI 中构建节点时添加一个小包装器：

```python
def with_progress(label: str, node: Node) -> Node:
    def wrapped(state: ResearchState) -> ResearchState:
        console.print(label)
        return node(state)
    return wrapped
```

- 包装六个 CLI 创建的节点函数。
- 保持图结构不变。

这比更深入的 LangGraph 插桩更受欢迎，因为它简单、可测试，并且保留了架构。

## 10. 详细输出

### 10.1 当前行为

`--verbose` 仅在工作流完成后打印 `errors`。

### 10.2 新行为

启用 `--verbose` 时，在工作流完成后打印一个紧凑摘要：

```text
Workflow details:

Subquestions:
1. <question>
   query: <search_query>
2. ...

Search results:
- q1: 5 result(s)
- q2: 4 result(s)

Research notes:
- q1: confidence=high, findings=3, sources=2
- q2: confidence=medium, findings=2, sources=2

Review:
- passed: True
- score: 92
- issues: 0
- suggestions: 2

Errors:
- ...
```

规则：

- 不要打印 API 密钥。
- 不要打印完整的原始 Tavily 响应。
- 不要打印长完整源内容。
- 保持摘要简短。

## 11. 测试策略

添加或更新测试以涵盖：

### 11.1 失败报告内容

- 非法 URL 失败报告包括：
  - 中文标题 `研究报告生成失败`
  - 具体非法 URL
  - 允许的 URL 列表
  - 用户后续步骤

### 11.2 失败文件名

- `make_report_filename(..., failed=True)` 返回以 `-failed.md` 结尾的文件名。
- `save_report(..., failed=True)` 写入 `-failed.md` 路径。

### 11.3 状态状态

- 成功的 `write_report` 设置 `report_status="success"`。
- 验证失败设置 `report_status="failed_validation"`。
- 保存节点使用 `report_status` 选择失败文件名。

### 11.4 CLI 消息传递

- 成功的假工作流打印 `Saved report to:`。
- 失败验证的假工作流打印 `Report validation failed.` 和 `Saved failure report to:`。

### 11.5 进度输出

如果使用基于包装器的节点进度：

- CLI 测试或单元测试验证进度标签按执行顺序由包装器发出。

如果使用最低诚实进度：

- CLI 测试验证它打印 `Starting research workflow...` 并且在执行之前不预先打印所有六个误导性阶段行。

### 11.6 详细输出

- 给定具有子问题、搜索结果、笔记、审查和错误的假结果状态，详细格式化程序打印紧凑摘要，而不包含源内容或机密。

## 12. 验收标准

v0.1.1 通过当：

1. 所有现有测试仍然通过。
2. 失败报告、失败文件名、CLI 失败消息传递和详细摘要的新测试通过。
3. 验证失败报告清楚地标记为失败。
4. 验证失败文件名以 `-failed.md` 结尾。
5. CLI 输出区分成功和验证失败。
6. CLI 进度输出不再误导。
7. `--verbose` 提供足够的中间细节，以便用户确认规划、搜索、综合、写作和审查已发生。
8. 默认测试中没有进行外部 API 调用。

## 13. 推荐实现顺序

1. 向 `ResearchState` 添加 `report_status`。
2. 将报告验证失败生成重构为结构化助手。
3. 将失败报告文本更新为中文并包含非法 URL。
4. 在 `filenames.py` 和 `report_writer.py` 中添加失败文件名支持。
5. 更新保存节点，当 `report_status="failed_validation"` 时传递 `failed=True`。
6. 更新 CLI 成功/失败消息。
7. 用基于包装器的节点进度或诚实的工作流级别进度替换误导性进度输出。
8. 添加详细摘要格式化程序和测试。
9. 运行完整的离线测试套件。

## 14. 开放决策

### 决策 1：进度实现

推荐：CLI 中基于包装器的节点进度。

替代：仅工作流级别的诚实进度。

### 决策 2：详细计时

推荐：在工作流完成后打印详细摘要。

替代：在每个节点完成时打印详细信息，这需要更深入的节点插桩。

### 决策 3：重试

v0.1.1 的推荐：无自动重试。

原因：重试增加了 LLM 成本和控制流复杂性。它应该为 v0.2 单独设计。