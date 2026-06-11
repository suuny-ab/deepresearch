# Deep Research Agent v0.1.2 设计规格：严格编号引用与一次自动重写

日期：2026-06-11

## 1. 背景

v0.1.1 已经通过改进验收，主要解决了以下问题：

- 失败报告可读性提升
- 失败报告文件名增加 `-failed.md`
- CLI 能区分成功与失败
- 进度提示不再提前一次性打印
- `--verbose` 能展示子问题、搜索 query、搜索结果数量、notes、review 与 errors

但在线真实运行仍暴露出核心产品问题：

```text
在线成功研究报告生成率不足。
```

最近一次在线 `--verbose` 冒烟测试中，系统完整执行了：

```text
plan_research → search_web → synthesize_notes → write_report → review_report → save_report
```

但最终保存的是失败报告：

```text
reports/2026-06-11-114823-ai-failed.md
```

失败原因是：

```text
模型生成的报告只在 Sources 部分列出来源，但正文关键论点没有引用来源。
```

根本问题不是搜索失败，也不是工作流中断，而是：

```text
writer 输出格式与 validator 引用契约不一致。
```

当前 writer prompt 允许“source URL or footnote”，但当前 validator 只认可正文中直接出现 allowed URL。模型倾向生成 `[1]` 编号引用，并把 URL 放在 `## Sources` 中，因此经常被 validator 拒绝。

v0.1.2 的目标是统一引用格式契约，并通过一次自动重写提高在线成功报告生成率。

## 2. 目标

v0.1.2 要实现：

1. 明确定义严格编号引用格式。
2. 修改 writer prompt，使模型只使用 `[1]`、`[2]` 这类编号引用。
3. 修改 validator，使其校验编号引用与 `## Sources` 的映射关系。
4. 第一次报告引用校验失败时，自动重写一次。
5. review 节点只审核最终报告。
6. 如果重写后仍失败，保存包含完整失败链路的失败报告。
7. `--verbose` 显示 retry 情况和每次校验失败原因。
8. 使用 3 个在线 smoke test 问题进行验收，至少 2/3 成功。

## 3. 非目标

v0.1.2 不做：

- 多次 retry 或无限循环。
- review 失败后自动补充搜索。
- 并发搜索。
- 多 query per subquestion。
- 搜索结果 rerank。
- 来源质量评分。
- trace JSON 文件。
- Web UI。
- PDF/DOCX 导出。
- 多 Agent 协作。

这些可以放到 v0.2 或后续版本。

## 4. 核心设计结论

本轮头脑风暴已确认以下设计决策：

| 主题 | 决策 |
|---|---|
| 引用格式 | 只支持 `[1]` 编号引用 |
| 校验模式 | 严格模式 |
| 自动重写 | 第一次校验失败后自动重写一次 |
| retry 次数 | 最多一次 |
| review 时机 | 只审核最终报告 |
| 主 LangGraph 结构 | 保持不变 |
| retry 后仍失败 | 保存完整失败报告 |
| 在线验收 | 3 个问题，至少 2 个成功 |

## 5. 新引用契约

### 5.1 正文引用格式

正文中的关键论点必须使用编号引用：

```markdown
AI 搜索正在从关键词匹配转向生成式答案。[1]
RAG、多模态检索和 Agent 化是主要技术趋势。[2][3]
```

正文中不允许出现裸 URL。

不推荐正文 Markdown link：

```markdown
[来源](https://example.com)
```

v0.1.2 的成功标准只认可编号引用。

### 5.2 Sources 格式

报告必须包含 `## Sources` 部分。

格式：

```markdown
## Sources

[1] https://example.com/source-a
[2] https://example.com/source-b
[3] https://example.com/source-c
```

可接受的 Sources 行格式：

```markdown
[1] https://example.com/source-a
[1]: https://example.com/source-a
- [1] https://example.com/source-a
```

不要求 Sources 中带标题，但允许在 URL 后出现标题说明：

```markdown
[1] https://example.com/source-a - Source title
```

validator 只需要提取编号和 URL。

## 6. 严格校验规则

报告通过校验，当且仅当满足以下全部条件。

### 6.1 必须存在 `## Sources`

没有 `## Sources`：失败。

### 6.2 正文必须至少有一个编号引用

正文指 `## Sources` 之前的内容。

如果正文没有任何 `[n]`：失败。

### 6.3 正文每个引用编号都必须在 Sources 中定义

示例：

```markdown
正文引用 [1][2]

## Sources

[1] https://example.com/a
```

失败原因：正文引用了 `[2]`，但 Sources 没有定义 `[2]`。

### 6.4 Sources 中每个编号都必须被正文引用

示例：

```markdown
正文引用 [1]

## Sources

[1] https://example.com/a
[2] https://example.com/b
```

失败原因：Sources 中的 `[2]` 没有在正文中使用。

这是严格模式，已在头脑风暴中确认。

### 6.5 Sources 中每个 URL 必须来自 allowed URLs

allowed URLs 来自 Tavily 搜索结果。

如果 Sources 中出现不在 allowed URLs 中的 URL：失败。

### 6.6 正文不允许裸 URL

正文中出现 `http://` 或 `https://`：失败。

URL 只能出现在 `## Sources` 部分。

## 7. CitationValidationResult 数据结构

建议新增内部数据结构：

```python
@dataclass(frozen=True)
class CitationValidationResult:
    passed: bool
    reason: Literal[
        "missing_sources_section",
        "missing_body_citations",
        "undefined_citations",
        "unused_sources",
        "invalid_source_urls",
        "bare_urls_in_body",
    ] | None
    message: str
    body_citations: set[int]
    source_citations: set[int]
    undefined_citations: set[int]
    unused_sources: set[int]
    invalid_source_urls: list[str]
    bare_body_urls: list[str]
    allowed_urls: list[str]
```

也可以拆成：

```python
CitationMap
CitationValidationFailure
CitationValidationResult
```

具体实现可按代码清晰度决定，但必须能表达：

- 正文引用了哪些编号
- Sources 定义了哪些编号
- 哪些正文编号未定义
- 哪些 Sources 编号未使用
- 哪些 URL 不在 allowed URLs
- 正文有哪些裸 URL

## 8. Writer Prompt 更新

当前 prompt 应从：

```text
Every key conclusion should include a source URL or footnote.
```

改成更严格的格式契约。

建议核心提示：

```text
请使用中文撰写结构化 Markdown 研究报告。

引用规则必须严格遵守：
1. 正文中的每个关键论点必须使用编号引用，例如 [1]、[2]。
2. 正文中不要出现裸 URL。
3. 所有 URL 只能出现在 ## Sources 部分。
4. ## Sources 中必须用 [1]、[2] 映射到 allowed source URLs。
5. 正文中使用的每个编号都必须在 ## Sources 中定义。
6. ## Sources 中列出的每个编号都必须在正文中出现。
7. 只能使用 Allowed source URLs 列表中的 URL。

Citation rules:
- Use numbered citations in the body: [1], [2], [3].
- Do not put raw URLs in the body.
- URLs may only appear in the ## Sources section.
- Every citation number used in the body must be defined in ## Sources.
- Every source listed in ## Sources must be cited in the body.
- Only use URLs from the allowed source URL list.
```

中英混合是刻意设计：中文说明任务目标，英文强化格式约束，降低模型误解概率。

## 9. 自动重写一次

### 9.1 新 write_report 内部流程

LangGraph 主图保持不变：

```text
write_report → review_report → save_report
```

但 `write_report` 节点内部变成：

```text
生成初稿
↓
校验编号引用
↓ 通过
返回成功报告
↓ 失败
构造重写 prompt
↓
生成重写报告
↓
再次校验编号引用
↓ 通过
返回成功报告
↓ 失败
返回完整失败报告
```

### 9.2 retry 限制

- 最多 retry 一次。
- 不做无限循环。
- retry 只针对 citation validation failure。
- 如果 LLM 调用本身失败，沿用现有错误处理，不伪装成 citation failure。

### 9.3 retry prompt

重写 prompt 应包含：

- 原始研究问题
- 当前报告草稿
- 失败原因
- 具体失败细节
- allowed URLs
- 明确要求重新生成完整报告
- 明确禁止裸 URL
- 明确要求严格 `[n]` 编号引用

示例：

```text
你刚才生成的报告未通过引用校验。

失败原因：Sources 中存在未被正文引用的编号：[4]

请重新生成完整 Markdown 报告。
必须遵守：
- 正文关键论点使用 [1]、[2] 编号引用。
- 正文不允许出现裸 URL。
- URL 只能出现在 ## Sources 部分。
- Sources 中每个编号都必须在正文中使用。
- 只能使用 allowed URLs。
```

## 10. Review 时机

review 节点只审核最终报告。

最终报告可能是：

1. 第一次生成且校验通过的成功报告
2. retry 后校验通过的成功报告
3. retry 后仍失败的失败报告

review 不审核被丢弃的中间草稿。

主 LangGraph 结构不变，不新增 validate/rewrite 节点。

## 11. 状态模型扩展

当前已有：

```python
report_status: "success" | "failed_validation"
```

v0.1.2 建议新增：

```python
rewrite_attempted: bool
validation_attempts: int
validation_failures: list[CitationValidationFailure]
```

如果不想把内部 dataclass 放入 `ResearchState`，也可以保存为可序列化 dict：

```python
validation_failures: list[dict[str, Any]]
```

推荐使用可序列化结构，方便 verbose 输出和未来 trace JSON。

成功场景：

```python
report_status = "success"
rewrite_attempted = False | True
validation_attempts = 1 | 2
validation_failures = [] | [first_failure]
```

失败场景：

```python
report_status = "failed_validation"
rewrite_attempted = True
validation_attempts = 2
validation_failures = [first_failure, second_failure]
```

## 12. 完整失败报告

如果 retry 后仍失败，保存完整失败报告。

格式：

```markdown
# 研究报告生成失败

本次报告经过自动重写后仍未通过来源校验，因此没有发布研究报告正文。

## 第一次失败原因

正文没有使用编号引用，例如 [1]、[2]。

## 第二次失败原因

Sources 中存在未被正文引用的编号：[4]

## 详细诊断

### 第一次诊断

- reason: missing_body_citations
- body citations: None
- source citations: [1], [2], [3]
- undefined citations: None
- unused sources: [1], [2], [3]
- invalid source URLs: None
- bare body URLs: None

### 第二次诊断

- reason: unused_sources
- body citations: [1], [2], [3]
- source citations: [1], [2], [3], [4]
- undefined citations: None
- unused sources: [4]
- invalid source URLs: None
- bare body URLs: None

## 可用来源 URL

- https://example.com/a
- https://example.com/b

## 你可以怎么做

- 重新运行一次。
- 使用更具体的问题。
- 增加 `--results-per-query`。
- 使用 `--verbose` 查看子问题和搜索结果摘要。
```

## 13. Verbose 输出更新

`--verbose` 应显示 citation retry 元数据：

```text
Report validation:
- rewrite_attempted: True
- validation_attempts: 2
- final_status: failed_validation
- attempt 1: missing_body_citations
- attempt 2: unused_sources
```

如果 retry 后成功：

```text
Report validation:
- rewrite_attempted: True
- validation_attempts: 2
- final_status: success
- attempt 1: missing_body_citations
```

如果第一次成功：

```text
Report validation:
- rewrite_attempted: False
- validation_attempts: 1
- final_status: success
- failures: None
```

## 14. 在线验收标准

v0.1.2 在线验收采用多题 smoke test 成功率标准。

### 14.1 题集

```text
1. AI 搜索引擎的发展趋势
2. LangGraph 和 CrewAI 的适用场景
3. 新能源汽车固态电池商业化进展
```

### 14.2 通过标准

```text
至少 2/3 生成成功报告。
```

成功报告定义：

- 输出文件不是 `-failed.md`
- `report_status = success`
- 报告包含标题、摘要、关键结论、深度分析、Sources、Quality Review
- 正文使用 `[n]` 编号引用
- Sources 中每个编号都被正文引用
- Sources 中每个 URL 都来自 allowed URLs
- Quality Review 不要求满分，但不能是失败报告的 0 分 review

### 14.3 每题记录项

每个问题记录：

| 字段 | 说明 |
|---|---|
| question | 测试问题 |
| result | success / failed_validation |
| output_path | 输出文件 |
| rewrite_attempted | 是否发生自动重写 |
| validation_attempts | 1 或 2 |
| validation_failures | 失败原因列表 |
| review_score | Quality Review 分数 |
| review_passed | Quality Review 是否通过 |

## 15. 测试策略

### 15.1 Citation parser / validator 单元测试

必须覆盖：

1. 正文 `[1]` + Sources `[1] allowed URL` → 通过
2. 缺少 `## Sources` → 失败
3. 正文无 `[n]` → 失败
4. 正文 `[2]` 未在 Sources 定义 → 失败
5. Sources `[2]` 未被正文引用 → 失败
6. Sources URL 不在 allowed URLs → 失败
7. 正文包含裸 URL → 失败
8. 支持 `[1] URL`、`[1]: URL`、`- [1] URL` 三种 Sources 行格式

### 15.2 Writer prompt 测试

检查 prompt 包含：

- numbered citations
- no raw URLs in body
- URLs only in Sources
- every body citation defined in Sources
- every Source cited in body
- only allowed URLs

### 15.3 Retry 测试

必须覆盖：

1. 第一次校验通过 → 不 retry
2. 第一次失败，第二次通过 → 保存成功报告，`rewrite_attempted=True`
3. 第一次失败，第二次仍失败 → 保存完整失败报告
4. retry prompt 包含失败原因和 allowed URLs
5. review 节点只收到最终报告

### 15.4 Verbose 测试

覆盖：

- 第一次成功时显示 `rewrite_attempted=False`
- retry 后成功时显示 attempt 1 失败原因
- retry 后失败时显示两个失败原因

### 15.5 在线验收

在线 smoke test 不放进默认 pytest。

单独运行：

```bash
uv run deepresearch "AI 搜索引擎的发展趋势" --verbose
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --verbose
uv run deepresearch "新能源汽车固态电池商业化进展" --verbose
```

记录 3 个结果，至少 2 个成功。

## 16. 验收标准

v0.1.2 通过条件：

1. 离线测试全部通过。
2. citation validator 覆盖所有严格规则。
3. writer prompt 明确要求 `[n]` 编号引用。
4. 第一次校验失败时自动重写一次。
5. retry 成功时保存成功报告。
6. retry 仍失败时保存完整失败报告。
7. review 只审核最终报告。
8. `--verbose` 显示 retry 情况和失败原因。
9. 在线 3 题 smoke test 至少 2 题成功。
10. 默认测试不调用外部 API。

## 17. 推荐实现顺序

1. 抽离 citation parser / validator 模块。
2. 为 validator 写完整单元测试。
3. 修改 writer prompt 为严格编号引用。
4. 修改 write_report 节点，先做一次 validate。
5. 添加 rewrite prompt 与一次 retry。
6. 扩展 state metadata。
7. 更新失败报告为完整失败链路。
8. 更新 verbose 输出 retry 信息。
9. 确保 review 节点只审最终报告。
10. 运行离线测试。
11. 运行 3 题在线 smoke test。
12. 写 v0.1.2 验收报告。

## 18. 开放问题

当前已确认核心设计，无剩余阻塞型开放问题。

可在实施计划阶段进一步细化：

- Citation parser 的具体正则实现。
- Sources 行格式支持范围。
- validation failure 的 dict 序列化格式。
- retry prompt 的最终措辞。
