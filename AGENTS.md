# AGENTS.md

本文件为 Codex (Codex.ai/code) 在此仓库中工作时提供指引。

## 构建、测试与运行

```bash
uv sync                    # 安装全部依赖（含开发依赖）
uv run pytest              # 运行所有离线测试（不调用真实 API）
uv run deepresearch "..."  # 运行研究 agent（在线 — 会调用 DeepSeek + Tavily）
```

测试完全离线——使用 `FakeLLMClient`（返回预先配置的响应字符串列表）和 `FakeSearchClient`（返回桩搜索结果）。添加测试依赖用 `uv add --dev <package>`。

用真实 API 冒烟测试（消耗配额）：
```bash
uv run deepresearch "AI 搜索引擎的发展趋势" --max-subquestions 3 --results-per-query 3
```

## 架构：LangGraph 流水线

应用构建在 LangGraph 的 `StateGraph` 之上。每个节点是一个普通函数 `(ResearchState) -> ResearchState`，由 `make_*_node` 工厂函数创建，工厂函数通过闭包捕获依赖（LLM 客户端、搜索客户端、配置值）。

```
START → plan_research → search_web → prepare_evidence → write_report → review_report → save_report → END
                                                                   ↑                  |
                                                                   └──────────────────┘ （条件边：分数 < 70 时重写，已重写过则跳过）
```

`graph.py` 通过 `build_research_graph()` 构建图，节点函数以关键字参数形式传入——调用方可在测试中注入 fake。`cli.py` 注入真实客户端，并用 Rich 进度标签包装每个节点（`[1/6] 规划研究...`）。

## 状态模型（`state.py`）

`ResearchState` 是一个 `TypedDict(total=False)`。以下 Pydantic 模型表示流经流水线的结构化数据：

- **`SubQuestion`** — 分解后的子问题，包含 `search_queries`（每个 2-3 个不同角度的查询：中文、英文、报告/研究类）。`@model_validator` 在 `search_queries` 为空时用 `search_query` 回填。
- **`SearchResult`** — Tavily 原始搜索结果（`content_type: "search_content"`）。
- **`ExtractedClaim`** — 阶段一输出：从来源中提取的原始声明（尚未交叉验证）。`confidence` 仅反映来源文本质量。
- **`EvidenceCard`** — 阶段二输出：带 `corroboration_level`（`single_source` | `weakly_corroborated` | `strongly_corroborated`）和 `corroborating_sources` 列表的声明。
- **`ReviewResult`** — 评分审核结果（0–100），包含问题列表和改进建议。

## 证据流水线（`prepare_evidence` 核心逻辑）

`prepare_evidence.py` 实现了一个两阶段流水线，共 1 + N 次 LLM 调用：

1. **筛选**：搜索结果按 `(subquestion_id, normalized_url)` 去重，然后按 Tavily 相关性评分排序，并施加域名多样性约束（每个域名最多一条，每个子问题最多 `max_sources_per_subquestion` 条）。
2. **提取全文**：对筛选后的 URL 调用 Tavily `extract()`。提取失败时回退到搜索摘要内容。
3. **阶段一 — 提取声明**（1 次 LLM 调用）：一次性从所有子问题的所有来源中提取 `ExtractedClaim`。
4. **阶段二 — 交叉验证**（N 次 LLM 调用，每个子问题一次）：在子问题组内评估声明，检查其他不同域名的来源是否独立印证同一事实。
5. **后验证**：剔除来源 URL 无效的卡片；根据实际可用来源重新核验交叉验证级别。

## 引用校验（`citations.py`）

报告使用严格的 `[N]` 编号引用。`validate_citations(report, allowed_urls)` 按优先级检查 7 种失败模式：

1. 缺少 `## Sources` 部分
2. 正文中出现裸 URL
3. Sources 中存在重复编号
4. 正文中没有编号引用
5. 正文引用的 `[N]` 在 `## Sources` 中未定义
6. Sources 中的 URL 不在允许列表中（来自 Tavily 结果 / EvidenceCards）
7. `## Sources` 中定义的来源未被正文引用

写入节点最多尝试 2 次：若首次报告引用校验失败，则构建包含失败原因和允许 URL 列表的重写提示词再次尝试。若第二次仍失败，则保存 `-failed.md` 诊断报告。

## 客户端（`clients/`）

- **`DeepSeekLLMClient`** 封装了指向 DeepSeek API 的 OpenAI SDK。Protocol `LLMClient` 定义了 `complete(prompt: str) -> str`。LLM 调用失败抛出 `LLMError`。
- **`TavilySearchClient`** 封装 `tavily-python`。Protocol `SearchClient` 定义了 `search()` + `extract()`。搜索失败抛出 `SearchError`。

## 提示词（`prompts/`）

每个提示词模块导出一个 `build_*_prompt(...)` 函数，接受结构化数据并返回字符串。提示词引导 LLM 返回指定 Pydantic 结构的 JSON。`parse_json_object()` 工具负责从代码块或原始文本中提取 JSON。

## 项目约定

- Python ≥3.11，用 `uv` 管理（lockfile 已提交）。构建后端：`hatchling`。
- 所有源码位于 `src/deepresearch/`（命名空间包布局——包根目录不需要 `__init__.py`）。
- 配置通过 `.env` + `AppConfig.from_env()` 数据类，配合 `with_overrides()` 支持 CLI 参数覆盖。
- 错误类型化：`DeepResearchError` 基类 → `ConfigError`、`LLMError`、`SearchError`、`ReportWriteError`。
- 每个节点工厂遵循相同模式：`make_*_node(依赖项...) -> Callable[[ResearchState], ResearchState]`。
- 测试文件名与源模块一一对应（`test_citations.py` ↔ `citations.py`）。
