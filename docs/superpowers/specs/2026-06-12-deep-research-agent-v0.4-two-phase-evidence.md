# Deep Research Agent v0.4 设计规格：两阶段证据管线 + A/B 测试基础设施

日期：2026-06-12

## 1. 背景

v0.3 将硬编码域名评分替换为多源交叉验证，但将提取（claim extraction）和验证（cross-validation）捆在一次 LLM 调用中。这两个任务的认知需求是互斥的：

- **提取**偏好发散——越多越好，漏掉一个真实 claim = 报告缺失信息
- **交叉验证**偏好收敛——"不确定就别标，不要谎称有多源支撑"

同一个 LLM 同时承担二者 → 验证压制提取 → 保守输出。v0.3.1 通过传递子问题上下文缓解了症状（对比型话题卡片数从 4 回升到 12），但利益冲突未消除。

v0.4 将提取和验证拆成两个独立的 LLM 调用，每个调用只承担单一任务。

同时，当前的在线验证无法做 A/B 对比——每次搜索返回不同结果，无法区分"设计改了"和"搜到不同内容"。v0.4 新增搜索结果冻结+回放+自动比对的基础设施。

## 2. 版本目标

1. **解耦提取与验证**：Phase 1 纯提取（1 次调用），Phase 2 每个子问题独立验证（N 次调用），不再有利益冲突。
2. **A/B 测试基础设施**：`--save-search` 冻结搜索结果，`--replay-search` 回放，`--compare` 自动比对。
3. **自动监测断言**：`--dry-run` 结束时自动执行 3 个断言，不通过则 warning。
4. **离线测试通过 + 在线 A/B 测证明提取压制解除**。

## 3. 非目标

- 不跨子问题做交叉验证（子问题独立验证，跨子问题的"交叉验证"常为假阳性）。
- 不改动 synthesize_notes、write_report、review_report、save_report 节点。
- 不修 Notes 全有或全无降级、Review 评分（后续版本）。

## 4. 两阶段证据管线

### 4.1 流程概述

```
当前 (v0.3.1):
  1次 LLM 调用 → EvidenceCard[] (带 corroboration)

v0.4:
  Phase 1: 1次 LLM 调用 → ExtractedClaim[] (无 corroboration)
  Phase 2: N次 LLM 调用 (每个子问题1次) → EvidenceCard[] (带 corroboration)
```

### 4.2 Phase 1: Claim Extraction

**任务**：读原文，尽可能多地提取可被引用的主张。没有交叉验证指令。

**入参**：extracted_sources（按子问题分组）、subquestions、question

**输出**：`ExtractedClaim[]`

**关键设计**：
- prompt 中**不含**任何交叉验证、corroboration_level、corroborating_sources 相关指令
- 指令 "Extract as many distinct, citable claims as each source contains. There is no minimum or maximum."
- 每条 claim 必须有 `supporting_snippet` 和 `source_url`

### 4.3 Phase 2: Per-Subquestion Cross-Validation

**任务**：对一个子问题的所有 claim，在该子问题的来源中进行独立域名交叉验证。

**入参**：该子问题的 ExtractedClaim[] + extracted_sources[] + 子问题文本

**每个子问题调用一次**（典型：5 个并行 or 串行调用）

**输出**：该子问题的 EvidenceCard[]（带 corroboration）

**关键设计**：
- 来源已由选择逻辑保证为不同域名（v0.3 的 `_select_sources` 按域名去重），Phase 2 天然只在独立来源间验证
- `corroboration_level` 逻辑不变：strongly (2+)、weakly (1)、single_source (0)
- 保留 `supporting_snippet`、`source_url` 等字段，仅新增 corroboration 字段

### 4.4 数据模型变更

新增 `ExtractedClaim`（state.py）：

```python
class ExtractedClaim(BaseModel):
    id: str
    subquestion_id: str
    claim: str
    source_url: str
    source_title: str
    supporting_snippet: str
    content_type: Literal["search_content", "extracted_content"]
    confidence: Confidence
```

EvidenceCard 不变。ResearchState 新增可选字段 `extracted_claims: list[ExtractedClaim]`（用于 Phase 1→2 传递，也用于 `--dry-run` 展示）。

### 4.5 API 调用量

| | 当前 | 新设计 |
|---|---|---|
| Phase 1 | — | DeepSeek ×1 |
| Phase 2 | — | DeepSeek ×N_subquestions (典型 5) |
| 合计 | DeepSeek ×1 | DeepSeek ×6 |

每次 Phase 2 调用范围小（3 篇来源 + 该子问题的 claim），单次 token 量远小于当前的全量调用。

### 4.6 事后校验

代码层保留 4 个校验（`_validate_corroboration`），但简化：

- Check 1：corroborating_sources URL 必须存在于 extracted_sources ✅ 保留
- Check 2：同域名不能算交叉验证 — **删除**（Phase 2 天然保证）
- Check 3：strongly_corroborated 需要≥2 个 full-text 验证源 ✅ 保留
- Check 4：weakly_corroborated 需要≥1 个有效验证源 ✅ 保留

## 5. A/B 测试基础设施

### 5.1 `--save-search`

将 Tavily 搜索结果序列化保存，供回放使用：

```bash
uv run deepresearch "..." --dry-run --save-search search_dump.json
```

保存内容：`search_results: list[SearchResult]` + `subquestions: list[SubQuestion]` + `question: str`

### 5.2 `--replay-search`

跳过 `plan_research` 和 `search_web`，直接用冻结的搜索结果：

```bash
uv run deepresearch "..." --dry-run --replay-search search_dump.json
```

图结构变更：`START → prepare_evidence → END`（跳过前两步）。

### 5.3 `--compare`

对比两次 `--dry-run` 的输出：

```bash
# 基线
git checkout v0.3.1
uv run deepresearch "..." --dry-run --replay-search search.json --output baseline.json

# 新设计
git checkout v0.4
uv run deepresearch "..." --dry-run --replay-search search.json --output new.json

# 比对
uv run deepresearch --compare baseline.json new.json
```

输出：

```text
A/B Comparison: baseline vs new

Claim extraction:
  baseline (v0.3.1): 12 cards from 15 sources (0.80 avg)
  new (v0.4):        24 cards from 15 sources (1.60 avg)
  delta: +100%

Per-source utilization:
  baseline: 12/15 sources contributed (80%)
  new:     15/15 sources contributed (100%)
  delta: +20%

Corroboration distribution:
  baseline: strongly=9, weakly=2, single=1
  new:      strongly=6, weakly=12, single=6
  delta: single_source rate 8% → 25%

Single-source cards:
  baseline: 1 cards
  new:     6 cards — review for false single_source
```

### 5.4 图结构变更

`build_research_graph` 新增 `replay_search: bool` 参数。当 True 时：

```python
if replay_search:
    graph.add_edge(START, "prepare_evidence")
    graph.add_edge("prepare_evidence", END)
```

## 6. 自动监测断言

`--dry-run` 结束时自动执行，不通过则打印 `[FAIL]`：

```python
# Assertion 1: 每个来源至少产出 1 条 claim
for source in extracted_sources:
    claim_count = len([c for c in claims if c.source_url == source.url])
    if claim_count == 0:
        print(f"[FAIL] Source {source.url} contributed 0 claims")

# Assertion 2: 交叉验证率 >= 60%
rate = (strongly + weakly) / total
if rate < 0.6:
    print(f"[FAIL] Corroboration rate {rate:.0%} below 60% threshold")

# Assertion 3: 子问题间 claim 数差值 <= 3x
if max_claims > min_claims * 3:
    print(f"[FAIL] Claims distribution skewed: {claims_per_sq}")
```

## 7. 文件变更

```
新增:
  src/deepresearch/prompts/extraction.py    — Phase 1 prompt
  tests/test_extraction_prompt.py

修改:
  src/deepresearch/state.py                 — ExtractedClaim 模型 + extracted_claims 字段
  src/deepresearch/prompts/evidence.py      — Phase 2 prompt (单子问题验证)
  src/deepresearch/nodes/prepare_evidence.py — 两阶段串联 + 断言
  src/deepresearch/graph.py                 — replay_search 参数
  src/deepresearch/cli.py                   — --save-search, --replay-search, --compare, --output
  tests/test_evidence_prompt.py             — 更新为 Phase 2 语义
  tests/test_prepare_evidence_node.py       — 两阶段测试
  tests/test_graph_structure.py             — replay_search 测试
  tests/test_cli.py                         — 新 CLI 选项测试
  tests/test_integration_offline.py         — 适配新管线
```

## 8. 验收标准

### 8.1 离线验收

- 所有测试通过
- `ExtractedClaim` 模型不含 corroboration 字段
- Phase 1 prompt 不含交叉验证指令
- Phase 2 prompt 范围限定为单子问题
- `--save-search` + `--replay-search` 可复现相同输入
- `--compare` 输出比对报告
- `--dry-run` 自动执行 3 个断言

### 8.2 在线 A/B 验收

使用对比型话题 "LangGraph 和 CrewAI 的适用场景"：

1. 冻结搜索结果
2. 用同一份搜索数据分别跑 v0.3.1 和 v0.4 管线
3. 比对：

| 指标 | v0.3.1 基线 | v0.4 目标 |
|---|---|---|
| claims_per_source | ~0.80 | ≥1.2 |
| source_utilization | ~80% | ≥90% |
| single_source_cards | ~1 (8%) | 合理增加（不追求数量，追求真实） |
| corroboration_rate | 91.7% | ≥60% |

验证完毕后跑一次标准全流程：review ≥ 85，citation validation 通过。
