# Deep Research Agent 测试系统设计

> 为 LLM Agent 建立可量化、可自动化的质量保障体系。

## 1. 背景与问题

### 1.1 现状

Deep Research Agent v0.5.2 的测试停留在静态检查：

- **Offline tests**（23 个测试文件）：Mock 全部外部依赖，验证代码逻辑正确性。不涉及真实 LLM 或搜索 API。
- **人工验收**：版本开发完成后，手动运行几条查询，读报告，凭感觉判断"好不好"。
- **Benchmark 雏形**：已有 `--save-search` / `--replay-search` / `--output` / `compare.py`，但不成体系——数据不全、对比维度少、没有门禁逻辑、没有集成到开发流程。

### 1.2 核心挑战：LLM Agent 无法用传统方式测试

传统软件的测试模式是：

```
给定输入 → 断言输出 == 预期值
```

LLM Agent 的特点是：

```
给定输入 → 每次输出不同（措辞、侧重点、证据选择都变化）
```

同样的问题跑两次，两篇报告可能都正确，但内容不完全相同。你不能 `assert output == expected`。

因此需要一套**完全不同的测试思路**：不是断言"输出应该是什么"，而是度量"输出好不好"。把"质量"拆成可量化的维度，比较改动前后的指标变化，判断是变好了还是变差了。

### 1.3 约束条件

| 约束 | 说明 |
|------|------|
| 单人项目 | 没有专门的 QA，测试和开发是同一个人 |
| API 成本 | DeepSeek + Tavily 每次调用有费用 |
| 时间成本 | 一次完整运行 1-2 分钟，多轮多查询需要数十分钟 |
| 首次开发 | 开发者在学习过程中，测试系统需要渐进式落地 |

---

## 2. 核心设计思想：控制变量 + 多维度度量

### 2.1 为什么不能直接对比两次 live 运行

```
v0.5.2: 搜索 "固态电池" → 返回 12 条结果 → LLM 产出 14 张 evidence cards
v0.6.0: 搜索 "固态电池" → 返回 8 条结果（Tavily 索引变了）→ LLM 产出 9 张 cards
```

14 → 9，cards 减少了。但这是因为你的代码变差了，还是因为搜索返回的结果本身就少了？**你分不出来。** 搜索 API 的不确定性混入了代码变更的效果中，污染了结论。

### 2.2 解决方案：冻结搜索作为对照组

```
v0.5.2  replay:  同一份 frozen data  → 真实 LLM  → 旧代码逻辑  → 14 cards
v0.6.0  replay:  同一份 frozen data  → 真实 LLM  → 新代码逻辑  → 17 cards
                                    ↑                        ↑
                              不确定性对称              差异来自代码变更
```

两个版本收到完全相同的输入（同一批搜索结果），LLM 各自是不确定的，但面对相同的输入条件，它们的不确定性程度是同一量级的。产出的差异只能来自你的代码/prompt 变更。**这就把 LLM 的不确定性从对比中隔离掉了。**

### 2.3 为什么度量很多维度而不是一个总分

你的改动通常是定向的。比如你修改了 evidence 提取 prompt，预期证据数量上升、来源利用更充分。但如果同时 review 评分下降了，你需要知道这两个信息。一个总分（"综合质量 82 分"）掩盖了"证据更好了但报告逻辑变差了"这种需要你干预的情况。

因此度量是多维并行的：证据质量、报告质量、结构正确性、鲁棒性，每个维度独立追踪。

---

## 3. 三层测试体系

### 3.1 为什么分层

测试中存在一个不可能三角：

```
        快 + 便宜
           /\
          /  \
         /    \
        /      \
       /________\
   可靠          真实
```

任何单层测试只能满足两个角，牺牲第三个。分层让每层覆盖不同的两个角，加起来覆盖全部。

### 3.2 Layer 1 — Offline Tests

**满足：快 + 便宜 + 可靠。牺牲：真实。**

| 属性 | 说明 |
|------|------|
| 目的 | 验证代码逻辑的正确性——单个函数、prompt 模板、状态转换是否正确 |
| 范围 | 纯代码逻辑，不调用任何外部 API |
| 方式 | Mock DeepSeek LLM、Mock Tavily Search，用假数据喂给节点函数 |
| 时间 | < 30 秒 |
| 成本 | 0 |
| 触发 | 每次 commit |

**为什么能达到目的：**

你测的是自己写的逻辑，不依赖 LLM。如果 prompt 模板缺了 `{question}` 占位符，LLM 收不到问题，这是 bug——单元测试能抓到。如果 citation 验证函数写错了判断条件，错误报告被标记为通过，这也是 bug——单元测试能抓到。这些是确定性问题，传统测试方法完全够用。

**但测不了什么：**

Prompt 改得好不好、证据提取质量如何、审查评分是否合理——这些问题只有 LLM 看到 prompt 后产生的真实输出才能回答。这是 Layer 2 的职责。

**已有基础：** 23 个测试文件，覆盖 nodes、prompts、state、clients、citations 等。后续持续扩展。

### 3.3 Layer 2 — Replay Tests + Gate

**满足：真实（LLM 部分）+ 可靠。牺牲：速度。**

| 属性 | 说明 |
|------|------|
| 目的 | 隔离测试代码/prompt 变更的效果，在受控条件下量化对比新旧版本 |
| 范围 | 完整 pipeline，但搜索使用预冻结数据 |
| 方式 | 用同一份 frozen search data 回放，调用真实 DeepSeek API 完成 evidence 提取、报告撰写、审查评分 |
| 时间 | ~5 分钟（5 queries × 1 run） |
| 成本 | LLM API 调用费用（可控，5 次完整运行） |
| 触发 | PR 提交时 |

**为什么能达到目的：**

这是整个测试体系的核心门禁层。用冻结搜索消除了搜索 API 的不确定性，用真实 LLM 调用保留了 prompt/逻辑变更的可观察效果。对比是公平的——两个版本面对完全相同的输入，差异只能来自代码变更。

**Gate（门禁）逻辑：**

门禁回答一个问题：**这个 PR 能合并吗？**

度量指标分两类：

**硬阻断（FAIL = 不能合并）**——保护的是底线：

| 指标 | 阈值 | 原因 |
|------|------|------|
| citation_coverage | = 1.0 | 正文引用必须在 Sources 中全部定义，缺一个都是事实错误风险 |
| orphan_url_count | = 0 | Sources 中的 URL 不在搜索结果里 = 幻觉 URL |
| error_count | = 0 | 运行中崩溃 = 功能不可用 |
| claims_per_source | ≥ 1.5 | 每个来源至少要产出 1.5 条 claim，低于此说明 LLM 严重浪费搜索信息 |
| source_utilization | ≥ 0.8 | 至少 80% 的搜索结果被实际使用 |

**软警告（WARN = 注意但不阻断）**——关注的是波动：

| 指标 | 阈值 | 原因 |
|------|------|------|
| review_score 下降 | < 5 分 | LLM 评分不是精确度量，小幅波动正常 |
| rewrite_rate 上升 | < 20% | 可能因为 query 本身变难而非代码变差 |
| domain_diversity 下降 | < 20% | 可能因为某次搜索结果本身域名集中 |

**按 query 独立判定：**

```
不独立：q1 18 张 cards + q2 3 张 cards → 平均 10.5 → 看起来还行 → 合并 ✗ 错误！
独立：  q1 18 张 PASS / q2 3 张 FAIL → q2 退化暴露 → 阻断 ✗ → 必须检查 q2  ✓ 正确
```

每个 query 独立过门禁，退化不被平均掩盖。任何一个 query 硬阻断 FAIL，整体就不允许合并。

**为什么硬软分流：**

硬阻断防的是**肯定变差了**——引用不完整、幻觉 URL、崩溃。这些一旦退化，无论其他指标多好，系统都不可靠。

软警告防的是**过度敏感**——LLM 评分有随机性，一个 85 分的报告和 82 分的报告可能质量差不多。对这些指标设死线会造成大量误杀（明明没变差却被阻断）。

### 3.4 Layer 3 — Live Tests

**满足：真实 + 全面。牺牲：速度和确定性。**

| 属性 | 说明 |
|------|------|
| 目的 | 检测外部依赖变化，验证端到端健康状态 |
| 范围 | 完整 pipeline，真实搜索 + 真实 LLM |
| 方式 | 完整查询 × 3-5 轮取统计分布 |
| 时间 | ~30 分钟 |
| 成本 | 较高（API 费用） |
| 触发 | 发布前手动 / 每周定时 |

**为什么 Layer 2 不够，还需要 Layer 3：**

Layer 2 有一个盲区：它用的是冻结的旧搜索数据。真实世界中 Tavily 索引在变化、网站内容在更新。你的系统需要对当下的搜索结果产出好报告，而不是对上个月的搜索结果。Prompt 可能在旧数据上表现好，但在搜索结果性质变化后（新闻内容变了、新网站出现）表现变差。

Layer 3 不做精确的版本间对比（因为搜索数据不同，无法控制变量），而是回答：**新版本在真实世界中能正常工作吗？** 检测的是：不崩溃、不返回空结果、citation 不大量失败、审查分数不系统性下降。

**为什么多轮取分布：**

```
Run 1: score 72, 13 cards
Run 2: score 88, 15 cards
Run 3: score 65, 11 cards
→ 均值 75, 标准差 11.7
```

你看到的不是一个点，而是一个范围。当时序数据出现明显偏移（如连续几周评分均值从 80+ 降到 50+），那就是外部依赖可能发生了重大变化（搜索 API 改版、模型更新）。

---

## 4. 数据基础：RunArtifact 与 Metrics

### 4.1 为什么要统一输出格式

三层测试体系依赖同一套数据格式。Layer 2 的 gate.py 需要读 Layer 2 的 replay 输出和 Layer 3 的 live 输出——如果格式不一致，每个消费者都要写兼容逻辑。统一 RunArtifact schema 意味着：**所有模式产出一致结构，所有消费者只理解一种格式。**

### 4.2 设计原则

**度量与业务解耦：**

```
节点层 (nodes/*.py)           → 产出原始 state 数据
运行统计层 (节点自带)          → 记录节点处理了多少、去重了多少（已有 _build_metrics）
度量层 (metrics.py，新增)     → 从 state 计算质量指标（纯函数，无副作用）
消费层 (cli.py / gate.py)     → 组装 artifact，做对比决策
```

- 节点不知道有人在度量它——它只产出 `evidence_cards`、`extracted_claims` 这些数据结构
- metrics 模块不知道数据是怎么产出的——它只接收 state dict，输出数字
- 测试可以单独给 metrics 模块喂假 state，验证计算结果——不涉及 LLM 调用

### 4.3 RunArtifact Schema

```text
RunArtifact
├── meta                       一次运行的身份信息
│   ├── app_version            "v0.6.0"
│   ├── schema_version         1（artifact 格式版本，格式变了就 +1）
│   ├── timestamp              ISO 8601
│   ├── mode                   "live" | "dry-run" | "replay"
│   └── config                 {max_subquestions, results_per_query, model}
│
├── inputs                     输入了什么
│   ├── question               用户的问题
│   └── subquestions           LLM 分解的子问题列表
│
├── pipeline                   中间产物（全部来自 state）
│   ├── search_results         搜索结果（live 是新搜的，replay 是注入的）
│   ├── extracted_claims       Phase 1 提取的原始 claim
│   ├── evidence_cards         Phase 2 验证后的 evidence cards
│   └── evidence_metrics       节点自带的运行统计（已有 _build_metrics）
│
├── standard_metrics           metrics.py 计算的质量指标
│   ├── evidence_card_count    证据卡总数
│   ├── claims_per_source      每来源平均 claim 数
│   ├── source_utilization     被使用的搜索来源比例
│   ├── corroboration_strong   强交叉验证数
│   ├── corroboration_weak     弱交叉验证数
│   ├── corroboration_single   单一来源数
│   ├── domain_diversity       独立域名数
│   ├── review_score           审查评分
│   ├── review_passed          审查是否通过
│   ├── rewrite_triggered      是否触发了重写
│   ├── citation_coverage      正文引用覆盖率
│   ├── source_citation_rate   Sources 被引用率
│   ├── orphan_url_count       非搜索结果 URL 数
│   └── validation_first_pass  首次是否通过 citation 校验
│
├── output                     最终产出
│   ├── report_markdown        完整报告正文（新增，之前 --output 没存）
│   ├── report_status          "success" | "failed_validation"
│   ├── review                 审查结果 {score, passed, issues, suggestions}
│   ├── validation_failures    citation 校验失败详情
│   └── output_path            报告保存路径
│
└── timing                     [待办：将来实现]
    ├── plan_research_ms
    ├── search_web_ms
    ├── prepare_evidence_ms
    ├── write_report_ms
    ├── review_report_ms
    └── total_ms
```

### 4.4 `--output` 行为

`--output` 是一个附加的数据采集通道，不是输出模式切换。加了 `--output` 只额外保存一份 JSON artifact，终端行为完全不变（该打印报告打印报告）。

三种运行模式下均可使用：

```
# Live 模式
uv run deepresearch "固态电池进展" --output result.json

# Dry-run 模式
uv run deepresearch "固态电池进展" --dry-run --output result.json

# Replay 模式
uv run deepresearch --replay-search frozen/q2.json --output result.json
```

---

## 5. 落地路线

### 5.1 第一阶段：数据基础（本次实现）

**产出：** `src/deepresearch/metrics.py` + 修改 `state.py`（新模型）+ 修改 `cli.py`（`--output` 重构）+ 测试

- 新增 `RunArtifact`、`RunMeta`、`StandardMetrics` 三个 Pydantic 模型
- 新建 `metrics.py`：纯函数 `compute_standard_metrics(state: dict) -> StandardMetrics`
- 重写 `cli.py` 的 `--output`：三种模式通用、组装完整 RunArtifact、调用 metrics 计算
- 新建 `tests/test_metrics.py`：纯粹数据测试，不依赖 LLM
- 删除 `benchmark/results/` 旧格式文件（从头开始，不兼容旧格式）
- 保留 `benchmark/frozen/`（replay 输入数据）

### 5.2 第二阶段：基准线回填

**产出：** `benchmark/baselines/v0.3.1/` ~ `v0.5.2/` 的标准 RunArtifact

- 对每个历史版本 checkout → 用同一份 frozen search data 回放 → 产出标准 artifact
- v0.3.1 使用 `benchmark/scripts/replay_v031.py` 适配器
- 基线文件存入 `benchmark/baselines/`，纳入版本管理

### 5.3 第三阶段：Gate 脚本

**产出：** `benchmark/gate.py` + `tests/test_gate.py`

- 接收 `--new-version` 和 `--baseline` 参数
- 实时 run replay 获取两个版本的 artifact（保证对比条件一致）
- 逐 query 逐指标对比，输出结构化 gate report
- 按硬阻断/软警告规则判定 PASS/FAIL/WARN
- 返回 exit code 0（全部 PASS）或 1（有 FAIL）

### 5.4 第四阶段：CI 集成

**产出：** GitHub Actions workflow

- PR 提交 → Layer 1 (pytest) → Layer 2 (replay + gate)
- Layer 1 失败则跳过 Layer 2（尽早失败）
- Gate report 贴到 PR 页面
- API 密钥通过 GitHub Secrets 注入
- 成本：每 PR ~5 次完整 LLM 调用

### 5.5 第五阶段：Live Tests（后续）

**产出：** 定时任务脚本 + 指标时间序列追踪

- 每周一次完整 live 运行（5 queries × 3 runs）
- 记录 metrics 到时间序列
- 异常检测：指标出现大幅偏移时告警
- 不在 PR 路径上（太慢太贵）

---

## 6. 待办事项

- [ ] timing 字段（每个节点的耗时统计）
- [ ] crash 时的 partial artifact 保存
- [ ] Live Tests 定时任务

---

## 7. 关键决策汇总

| 决策 | 选择 | 为什么 |
|------|------|--------|
| 核心对比机制 | Frozen replay（非 live） | 消除搜索 API 不确定性，隔离 prompt/logic 变更效果 |
| 度量位置 | 独立 metrics.py 模块 | 与业务节点解耦，纯函数可独立测试 |
| 数据格式 | 统一 RunArtifact schema | 所有模式、所有版本产出一致结构，消费者只理解一种格式 |
| 门禁粒度 | 按 query 独立判定 | 避免退化被平均值掩盖 |
| 硬软分流 | citation/error 硬阻断，score 软警告 | 结构正确不容退化，评分波动是 LLM 固有特性 |
| `--output` 行为 | 附加保存，不改变终端输出 | 数据采集通道，不是模式切换 |
| 旧数据兼容 | 删除，从头开始 | 不背历史包袱，新系统不需要兼容旧格式 |
| 旧版本回填 | 用同一份 frozen data 重跑 | 保证对比条件一致性 |
| 落地节奏 | 渐进式，分四阶段 | 单人项目，一次做太多容易失控 |
