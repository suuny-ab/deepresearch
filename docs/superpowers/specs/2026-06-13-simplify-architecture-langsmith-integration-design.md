# Deep Research Agent 架构简化 & LangSmith 集成设计

日期：2026-06-13
版本：v1.0

## 1. 动机

当前 v0.5.2 的代码库中，约 30% 的代码服务于自建的观测和测试基础设施（`metrics.py`、`verbose.py`、`benchmark/gate.py`、`benchmark/compare.py`、`RunArtifact` 系列模型等）。这些代码与 Agent 核心功能深度耦合——观测数据和测试断言共享同一套 `ResearchState` 中间产物，导致每次修改 prompt 或调整 state 字段都需要同步调整测试阈值。

对于单人项目，核心精力应该投入在 Agent 的研究质量（证据提取、交叉验证、报告生成）上，而非维护基础设施。

**决策**：删除全部自建观测和测试代码，引入 LangSmith 承担 tracing 和后续在线测试。Agent 只保留核心研究功能。

## 2. 设计原则

- **Agent 只做 Agent 的事**：搜索、提取证据、交叉验证、撰写报告、审查、保存
- **观测和测试是平台的事**：LangSmith 自动 tracing，后续基于 LangSmith Experiment 构建在线测试
- **删除优先于重构**：不确定是否需要保留的功能一律删除，git 历史可恢复
- **本次只做简化 + 引入 LangSmith**：基于 LangSmith 的在线测试体系不在本次范围

## 3. 删除清单

### 3.1 删除的源文件

| 文件 | 原因 |
|------|------|
| `src/deepresearch/metrics.py` | 自建指标计算，LangSmith trace 替代 |
| `src/deepresearch/verbose.py` | 自建诊断输出，LangSmith trace 树替代 |
| `benchmark/` 整个目录 | gate.py, compare.py, queries.json, frozen/, baselines/, scripts/ 全部 |

### 3.2 删除的数据模型（state.py）

- `RunMeta` — 运行元信息
- `StandardMetrics` — 14 项质量指标
- `RunArtifact` — 统一输出格式
- `ResearchState` 中的 `evidence_metrics` 字段

### 3.3 删除的 CLI 参数（cli.py）

- `--verbose` — LangSmith trace 替代
- `--dry-run` — 证据提取中途停止，不再需要
- `--output` — JSON artifact 保存，LangSmith 自动持久化
- `--save-search` — 冻结搜索结果
- `--replay-search` — 回放冻结结果
- `--compare` — A/B 对比

### 3.4 删除的节点内部函数

- `prepare_evidence.py` 中的 `_build_metrics()` 
- `prepare_evidence.py` 中的 `_run_assertions()`
- `cli.py` 中的 `_with_progress()` 包装器（进度显示简化）
- `cli.py` 中的 `_run_compare()` 函数
- `cli.py` 中的 RunArtifact 组装逻辑

### 3.5 删除的测试文件

- `tests/test_gate.py`
- `tests/test_metrics.py`
- `tests/test_compare.py`（如果存在于 benchmark/tests/）
- 各测试文件中针对 `--verbose`、`--dry-run`、`--output`、`--save-search`、`--replay-search` 的测试用例

### 3.6 图结构简化（graph.py）

- 删除 `dry_run` 参数
- 删除 `replay_search` 参数
- 图拓扑回归为单一标准模式：`START → plan → search → evidence → write → review → save → END`
- 保留 `_review_router` 条件路由（审查评分 < 70 触发重写，验证失败跳过重写）

## 4. 保留清单

### 4.1 Agent 核心功能（不修改逻辑）

| 模块 | 说明 |
|------|------|
| `cli.py` | 精简为 question 输入 → 构建 graph → invoke → 打印报告 + 保存路径 |
| `graph.py` | 单一路径，保留 review 条件路由 |
| `state.py` | ResearchState + SubQuestion + SearchResult + ExtractedClaim + EvidenceCard + ExtractedSource + ReviewResult。**删除 RunArtifact/RunMeta/StandardMetrics/evidence_metrics** |
| `nodes/planning.py` | 不变 |
| `nodes/searching.py` | 不变 |
| `nodes/prepare_evidence.py` | 保留两阶段管线。删除 `_build_metrics` 和 `_run_assertions`。`_build_metrics` 调用处直接删除，不影响数据流 |
| `nodes/writing.py` | 保留引用校验 + 自动重写逻辑 |
| `nodes/reviewing.py` | 保留五维度审查 + 重写反馈 |
| `nodes/saving.py` | 不变 |
| `prompts/` 全部 5 个文件 | 不变 |
| `clients/llm.py` | 不变 |
| `clients/tavily.py` | 不变 |
| `citations.py` | 保留。引用校验是 Agent 核心功能，不是观测 |
| `config.py` | 保留。删除 `verbose` 字段 |
| `errors.py` | 不变 |
| `utils/json.py` | 不变 |
| `utils/urls.py` | 不变 |
| `utils/filenames.py` | 不变 |
| `utils/report_writer.py` | 不变 |

### 4.2 离线测试

保留 21 个离线测试文件（删 test_gate.py 和 test_metrics.py）。Mock 外部依赖，验证代码逻辑正确性。

### 4.3 ResearchState 精简后

```python
class ResearchState(TypedDict, total=False):
    question: str
    subquestions: list[SubQuestion]
    search_results: list[SearchResult]
    extracted_claims: list[ExtractedClaim]
    evidence_cards: list[EvidenceCard]
    report_markdown: str
    report_status: Literal["success", "failed_validation"]
    rewrite_attempted: bool
    validation_attempts: int
    validation_failures: list[dict[str, Any]]
    review: ReviewResult
    review_feedback: str | None
    review_rewritten: bool
    output_path: str
    errors: list[str]
```

删除字段：`evidence_metrics`

## 5. LangSmith 集成

### 5.1 依赖添加

```toml
# pyproject.toml
dependencies = [
    ...
    "langsmith>=0.1.0",
]
```

### 5.2 环境变量（.env.example 追加）

```env
# LangSmith (可观测性)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=deepresearch
```

### 5.3 行为

- LangSmith 在 LangGraph 框架层自动捕获每个 node 的输入/输出/耗时
- 无需在 Agent 代码中手动插入任何 tracing 调用
- 如果 `LANGCHAIN_API_KEY` 未设置，tracing 静默跳过，不影响 Agent 正常运行
- 每个 DeepSeek LLM 调用的 token 用量自动记录

### 5.4 本次不做的

- 不上传 Dataset
- 不创建 Experiment
- 不实现 Custom Evaluator
- 不配置 Prompt Hub
- 这些属于后续"基于 LangSmith 构建在线测试体系"的范围

## 6. CLI 精简后

### 6.1 命令签名

```bash
uv run deepresearch "研究问题" \
  --max-subquestions 5 \
  --results-per-query 5 \
  --output-dir reports \
  --model deepseek-v4-pro
```

只有 4 个可选参数。删除 `--verbose`、`--dry-run`、`--output`、`--save-search`、`--replay-search`、`--compare`。

### 6.2 输出行为

```
$ uv run deepresearch "AI 搜索引擎的发展趋势"

[1/6] Planning research...
[2/6] Searching web...
[3/6] Preparing evidence...
[4/6] Writing report...
[5/6] Reviewing report...
[6/6] Saving report...

Saved report to: reports/2026-06-13-143022-ai.md

# AI 搜索引擎发展趋势研究报告
...（完整 Markdown 报告）
```

精简后终端输出只包含：6 步进度 + 保存路径 + Markdown 报告全文。

## 7. 文件变更总览

```
删除:
  src/deepresearch/metrics.py
  src/deepresearch/verbose.py
  benchmark/                          (整个目录)
  tests/test_gate.py
  tests/test_metrics.py

修改:
  src/deepresearch/state.py           — 删除 RunArtifact, RunMeta, StandardMetrics, evidence_metrics
  src/deepresearch/config.py          — 删除 verbose 字段
  src/deepresearch/graph.py           — 删除 dry_run 和 replay_search 参数，单一拓扑
  src/deepresearch/cli.py             — 删除 6 个 CLI 标志和对应逻辑，精简为纯 Agent 调用
  src/deepresearch/nodes/prepare_evidence.py — 删除 _build_metrics 和 _run_assertions
  pyproject.toml                      — 添加 langsmith 依赖
  .env.example                        — 追加 LangSmith 环境变量
  README.md                           — 更新文档（删除已废弃的 flags 说明）
  tests/conftest.py                   — 如有引用已删除的函数需更新
  tests/test_cli.py                   — 删除针对已废弃 flags 的测试用例
  tests/test_prepare_evidence_node.py — 删除针对 _build_metrics/_run_assertions 的断言
  tests/test_graph_structure.py       — 删除 dry_run/replay_search 的拓扑测试
  tests/test_integration_offline.py   — 删除依赖已废弃功能的测试用例

不变:
  src/deepresearch/nodes/planning.py
  src/deepresearch/nodes/searching.py
  src/deepresearch/nodes/writing.py
  src/deepresearch/nodes/reviewing.py
  src/deepresearch/nodes/saving.py
  src/deepresearch/prompts/ (全部)
  src/deepresearch/clients/ (全部)
  src/deepresearch/citations.py
  src/deepresearch/errors.py
  src/deepresearch/utils/ (全部)
  tests/ 其他 21 个测试文件
```

## 8. 验收标准

### 8.1 离线测试

```bash
uv run pytest
```
所有保留的 21 个测试文件通过，零 regression。

### 8.2 基本功能

```bash
uv run deepresearch "AI 搜索引擎的发展趋势"
```

- 显示六步进度
- 生成 Markdown 报告
- 打印报告全文
- 保存报告到 `reports/`
- 打印保存路径

### 8.3 引用校验仍工作

- 如果报告引用未在 Sources 定义的编号 → 自动重写一次
- 重写仍失败 → 保存 `-failed.md` 诊断报告
- 非引用校验失败不触发重写

### 8.4 审查重写仍工作

- 审查评分 < 70 且未重写过 → 触发质量重写
- 重写后的报告再次通过引用校验

### 8.5 LangSmith 集成

- 设置 `LANGCHAIN_API_KEY` 后运行 → LangSmith UI 可见完整 trace 树
- 不设置 `LANGCHAIN_API_KEY` → Agent 正常运行，无报错
- 每个 node 的输入输出在 trace 中可见

### 8.6 代码清理

- `grep -r "RunArtifact\|RunMeta\|StandardMetrics\|evidence_metrics" src/` 无结果（除注释）
- `grep -r "verbose\|dry.run\|save.search\|replay.search" src/deepresearch/cli.py` 无结果（除注释）
- `pyproject.toml` 包含 `langsmith` 依赖
- `.env.example` 包含 LangSmith 环境变量

## 9. 非目标（明确不做）

- ❌ 不创建 LangSmith Dataset 或 Experiment
- ❌ 不实现 Custom Evaluator
- ❌ 不迁移 prompt 到 Prompt Hub
- ❌ 不构建在线测试体系
- ❌ 不保留 frozen replay 的任何代码（包括 `benchmark/frozen/` 数据）
- ❌ 不保留 `--dry-run` 的证据摘要展示

## 10. 后续规划

本次重构完成后，系统处于"Agent 核心干净 + LangSmith tracing 就绪"的状态。后续迭代可以基于 LangSmith 逐步构建：

1. 上传 benchmark 查询为 LangSmith Dataset
2. 实现 Custom Evaluator（citation coverage、corroboration rate 等）
3. 用 LangSmith Experiment 做版本间对比
4. 如有需要，重新实现 frozen replay（作为 LangSmith 外挂机制）
