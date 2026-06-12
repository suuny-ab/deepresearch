# Deep Research Agent A/B Benchmarking Framework 设计规格

日期：2026-06-12

## 1. 背景与目标

v0.1 到 v0.5.2 五个版本迭代中，每个版本都有一个明确的结构性改动目标。但这些改动是否真的达到了目标？之前依赖于在线单次运行 + 人工评估，缺少可量化、可复现、可对比的验证机制。

本规格定义一套 A/B Benchmarking 框架，达成三个目标：

1. **可复现**：同一次搜索结果冻结后，任意版本回放完全相同的输入
2. **可量化**：每个版本改动对应明确的度量指标和通过标准
3. **可演进**：后续所有以结果为导向的版本更新，必须通过框架的 A/B 测试才能 claim 成功

## 2. 回放架构

### 2.1 核心思路：冻结果，回放管线

搜索阶段有两个不可控变量——Tavily 每次返回不同结果，LLM 每次生成不同子问题。`--replay-search` 冻结搜索阶段的产物（question + subquestions + search_results），让后续管线的输入完全一致。

### 2.2 各版本回放方式

| 版本 | 回放方式 |
|---|---|
| v0.4, v0.5.1, v0.5.2 | 内置 `--replay-search` CLI flag + `replay_search=True` 图模式 |
| v0.3.1 | 无 `--replay-search`——通过小脚本直接调 graph.invoke() 手动注入 frozen state，跳过 plan + search |

所有版本使用 v0.5.2 的 `--save-search` 冻结搜索数据。**零 backport**，历史版本代码不动。

### 2.3 图结构

正常模式：
```
START → plan → search → evidence → write → review → save → END
```

`--replay-search` 模式：
```
START → evidence → write → review → save → END
        ↑ 用 frozen.json 的 subquestions + search_results
```

`--dry-run` 模式（用在 Test A/B 节省 LLM 调用）：
```
START → evidence → END
```

## 3. Benchmark 查询设计

5 个查询覆盖不同认知复杂度，每类验证不同的管线能力：

| ID | 类型 | 查询 | 验证管线能力 |
|---|---|---|---|
| q1 | 对比型 | "LangGraph 和 CrewAI 的适用场景" | 提取量、双方论点捕捉 |
| q2 | 事实型 | "固态电池 2026 年商业化进展" | 交叉验证强度 |
| q3 | 前瞻型 | "AI 搜索引擎 2027 年发展趋势" | single_source 比例合理性 |
| q4 | 中文技术 | "量子计算对现有密码体系的威胁" | 中文提取 + 技术深度 |
| q5 | 边界型 | "用 3 句话概括 2026 年 AI Agent 的关键进展" | 低分触发 rewrite |

Test A/B 使用 q1, q2, q3（3 个）。Test C 使用所有 5 个（q1-q4 正常 + q5 设计为低分诱因）。

每查询参数：`--max-subquestions 4 --results-per-query 4`

### Test C 低分诱因设计

为触发 review score < 70，q5 设计为故意制造低分：

| 诱因 | 设计方式 | 预期短板维度 |
|---|---|---|
| 不完整 | "用 3 句话回答" 限制长度 | 完整性 (20%) |
| 来源少 | `--results-per-query 1` | 交叉验证覆盖 (20%) |
| 中文 + 深度 | 技术深度要求 | 综合 |

## 4. A/B 测试矩阵

### Test A：v0.3.1 vs v0.4 —— 提取压制解除

| 项 | 内容 |
|---|---|
| 假设 | 提取+验证解耦后，claims/source 显著上升，source_utilization 达到 100%，corroboration_rate 从虚假的 100% 降到合理范围 |
| queries | q1 (对比型), q2 (事实型), q3 (前瞻型) |
| 运行 | 每 query × 1 run × 2 版本 = 6 次运行 |
| 模式 | `--dry-run`（停在 evidence，不写报告） |
| 数据点 | ~36 sources（3 queries × 4 subquestions × 3 sources） |
| 度量 | claims/source 均值、source_utilization%、corroboration_rate% |
| 通过标准 | claims/source v0.4 ≥ 1.5 (预期 2x baseline)；source_utilization ≥ 90%；corroboration_rate < 80%（不再虚假） |

### Test B：v0.4 vs v0.5.1 —— 评分一致性

| 项 | 内容 |
|---|---|
| 假设 | 5 维 rubric + 锚点 → 同 query 多次评分方差缩小 |
| queries | q1, q2, q3 |
| 运行 | 每 query × 6 runs × 2 版本 = 36 次运行 |
| 模式 | `--dry-run`（评分需要全流程，但可以用 --output 抓 review score...） |
| 修正模式 | 需要全流程以获取 review score |
| 数据点 | 每版本 18 个 score |
| 度量 | score 标准差、max-min 范围 |
| 通过标准 | v0.5.1 score 标准差 < v0.4 标准差；均值无明显下降 |
| 统计方法 | F-test for variance equality |

> **注意：** 评分需要 review_report 节点运行，review_report 在 write_report 之后，write_report 需要跑全流程（非 dry-run）。Test B 不能用 --dry-run。

### Test C：v0.5.1 vs v0.5.2 —— 反馈闭环有效性

| 项 | 内容 |
|---|---|
| 假设 | score < 70 触发 rewrite → rewrite 后 score 上升；提取数量期望 → claims/source 进一步提升 |
| queries | 5 个全部（q5 为核心低分测试） |
| 运行 | 每 query × 1 run × 2 版本 = 10 次运行 |
| 模式 | 全流程 |
| 数据点 | 5 个配对 (rewrite 前 score, rewrite 后 score) |
| 度量 | rewrite 前后 score 差值、rewrite 触发次数、claims/source v0.5.2 vs v0.5.1 |
| 通过标准 | rewrite 后 score ≥ rewrite 前（不倒退）；至少 1 次 rewrite 后 score 上升 ≥5 分；claims/source v0.5.2 ≥ v0.5.1 |

## 5. 执行流程和产出

### 5.1 目录结构

```
benchmark/
├── queries.json              # 5 个 benchmark 查询定义
├── frozen/                   # 冻结的搜索结果
│   ├── q1-langgraph-crewai.json
│   ├── q2-solid-state.json
│   ├── q3-ai-trends.json
│   ├── q4-quantum-crypto.json
│   └── q5-short-answer.json
├── results/                  # 各版本 × 各 query × 各 run 的输出
│   ├── v0.3.1-q1-run1.json
│   ├── ...
│   └── v0.5.2-q5-run1.json
├── compare.py                # 对比脚本
└── report.md                 # 最终 A/B 报告
```

### 5.2 执行步骤

```
# Step 1：冻结搜索（v0.5.2，1 次全流程）
git checkout v0.5.2
for q in q1 q2 q3 q4 q5:
  uv run deepresearch "<query>" --max-subquestions 4 --results-per-query 4 \
    --save-search benchmark/frozen/${q}.json

# Step 2：并行回放（3 个 git worktree 同时跑）
# Worktree 1: v0.4
git worktree add ../bench-v04 v0.4
cd ../bench-v04
# Test A: q1,q2,q3 × 1 run × dry-run = 3 runs
for q in q1 q2 q3; do
  uv run deepresearch --replay-search ../../deepsearch/benchmark/frozen/${q}.json \
    --dry-run --output ../../deepsearch/benchmark/results/v0.4-${q}-run1.json
done
# Test B: q1,q2,q3 × 6 runs × full = 18 runs
for q in q1 q2 q3; do
  for run in $(seq 1 6); do
    uv run deepresearch --replay-search ../../deepsearch/benchmark/frozen/${q}.json \
      --output ../../deepsearch/benchmark/results/v0.4-${q}-run${run}.json
  done
done

# Worktree 2: v0.5.1 — 同上配置
# Test B: q1,q2,q3 × 6 runs = 18 runs
# Test C: q1,q2,q3,q4,q5 × 1 run = 5 runs

# Worktree 3: v0.5.2 — 同上配置
# Test C: q1,q2,q3,q4,q5 × 1 run = 5 runs

# v0.3.1（串行，无 worktree 隔离）
git checkout v0.3.1
for q in q1 q2 q3; do
  python benchmark/scripts/replay_v031.py benchmark/frozen/${q}.json \
    --dry-run --output benchmark/results/v0.3.1-${q}-run1.json
done

# Step 3：对比分析
python benchmark/compare.py benchmark/results/ --matrix tests.json

# Step 4：清理 worktrees
git worktree remove ../bench-v04 ../bench-v051 ../bench-v052
```

### 5.3 对比报告输出示例

```
A/B Benchmark Report — 2026-06-12
──────────────────────────────────

Test A: v0.3.1 vs v0.4 — Extraction Suppression
  Metric                v0.3.1    v0.4      Delta     Pass?
  ─────────────────────────────────────────────────────
  claims/source         0.8       1.7       +113%     ✅
  source_utilization    80%       100%      +20%      ✅
  corroboration_rate    100%      62%       -38%      ✅

Test B: v0.4 vs v0.5.1 — Score Consistency
  Metric                v0.4      v0.5.1    Delta     Pass?
  ─────────────────────────────────────────────────────
  score_std             8.2       4.1       -50%      ✅
  score_range           84-96     82-88     -40%      ✅

Test C: v0.5.1 vs v0.5.2 — Review Feedback Loop
  Metric                v0.5.1    v0.5.2    Delta     Pass?
  ─────────────────────────────────────────────────────
  rewrites_triggered    0         2          +2        ✅
  avg_score_improvement N/A       +8 pts    —         ✅
  claims/source         1.6       1.9       +19%      ✅

Overall: 3/3 tests pass ✅
```

## 6. v0.6 决策机制

A/B 测试结果直接决定 v0.6 方向：

| 数据信号 | v0.6 方向 |
|---|---|
| claims/source < 1.5 | 继续优化提取 prompt 或 Phase 1 结构 |
| corroboration_rate > 80% | 交叉验证判断太宽松，收紧 Phase 2 标准 |
| score 方差仍 > 6 | rubric 需要更多锚点或维度权重调整 |
| rewrite 不触发或触发后不提升 | rethink 反馈闭环设计 |
| 对比型 query 仍显著弱于其他 | 重点攻克对比型话题 |
| 中文 query 系统性低于英文 | 多语言提取/搜索优化 |
| Test A/B/C 全部通过 | 管线已达局部最优，开始探索搜索策略或架构级改进 |

## 7. 非目标

- 不做 CI 自动化（本次手工触发，下一次迭代再做）
- 不做在线 smoke test（已有独立的在线验收流程）
- 不修改任何历史版本代码
- 不做 GPU/本地模型推理（保持 DeepSeek API）

## 8. 文件变更范围

```
新增:
  benchmark/queries.json          — 5 个 benchmark 查询定义
  benchmark/compare.py            — 对比分析脚本
  benchmark/scripts/replay_v031.py — v0.3.1 回放脚本
  benchmark/README.md             — 框架使用说明

不修改任何 src/ 或 tests/ 代码
```

## 9. 验收标准

- 5 个 frozen.json 成功生成
- v0.3.1 / v0.4 / v0.5.1 / v0.5.2 各版本成功回放
- compare.py 产生可读的对比报告
- 报告明确标注每个测试的 PASS/FAIL 及支撑数据
- 所有版本测试运行在 15 分钟内完成
