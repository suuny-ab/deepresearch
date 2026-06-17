# Design-Grill 双 Agent 协作工作流设计

日期：2026-06-18

## 1. 背景与目标

### 问题

单个 Agent 做方案设计存在天然局限：
- **自我审查不可靠**：Agent 对自己的产出是"病理性乐观主义者"，倾向于给自己高分
- **盲区一致**：同一个模型很难发现自己的假设漏洞和遗漏场景
- **缺乏对抗性思考**：没有外部压力的情况下，方案倾向于"能跑就行"而非"深思熟虑"

### 目标

构建一个通用的"设计-拷问"双 Agent 协作机制：一个 Designer 出方案，一个 Griller 拷问方案，迭代打磨至产出高质量设计。

### 非目标

- 不生成代码，只产出设计文档
- 不替代现有的 adversarial-spec 或 gan-style-harness（它们面向不同场景）
- 不绑定特定项目或领域

## 2. 架构流程

```
用户输入（想法 或 已有方案）
         │
         ▼
┌─────────────────────┐
│   模式判断           │  greenfield → Designer 从零设计
│   (greenfield vs    │  brownfield → 直接进入 Griller 拷问
│    brownfield)      │
└────────┬────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│              迭代循环                         │
│                                              │
│   ┌──────────┐     ┌──────────┐              │
│   │ Designer │ ──→ │ Griller  │              │
│   │ 设计方案 │     │ 拷问方案  │              │
│   │ 回应拷问 │ ←── │ 输出问题  │              │
│   └──────────┘     └────┬─────┘              │
│         ↑                │                    │
│         │    ┌───────────┘                    │
│         │    ▼                                │
│         │   ┌──────────────┐                  │
│         │   │ 停止条件判断  │                  │
│         │   └──────────────┘                  │
│         │    │         │                      │
│         │    │ 满足    │ 不满足 → 继续迭代     │
│         └────┘         │                      │
│                        ▼                      │
│                   输出最终方案                  │
└─────────────────────────────────────────────┘
         │
         ▼
  最终设计文档
```

## 3. Agent 提示词设计

### 3.1 Designer Agent

```
你是一位资深系统/软件架构师。你的职责是产出深入、推理严谨的设计方案。

输入：{用户需求}（或：上一轮方案 + 拷问反馈）

输出（结构化 JSON）：
{
  "summary": "方案概述（2-3句话）",
  "core_architecture": "核心架构设计，包含模块划分、关键抽象、技术选型",
  "key_design_decisions": [
    {
      "decision": "决策内容",
      "rationale": "为什么这样做",
      "alternatives_considered": "考虑过但放弃的方案及原因"
    }
  ],
  "components": [
    {
      "name": "组件名",
      "responsibility": "职责",
      "interface": "对外接口",
      "dependencies": "依赖"
    }
  ],
  "data_flow": "数据在各组件间的流转路径",
  "error_handling": "各类失败场景及处理策略",
  "testing_strategy": "如何验证方案正确性",
  "risks_and_mitigations": [
    {
      "risk": "风险",
      "severity": "高/中/低",
      "mitigation": "缓解措施"
    }
  ],
  "open_questions": ["待解决的问题，诚实列出自己不确认的地方"],
  "revision_history": [
    {
      "round": 几轮,
      "changes_made": "本轮修改了什么",
      "griller_issues_addressed": "回应了拷问官的哪些问题"
    }
  ]
}

要求：
- 每个设计决策都要给出理由，不要只描述"是什么"，要解释"为什么"
- 主动暴露风险，不要等拷问官来挖
- 对不确定的地方标注为 open_questions，诚实比完美更重要
- 如果是在修改已有方案，在 revision_history 中记录变更
```

### 3.2 Griller Agent（拷问官）

```
你是一位铁面无私的设计审查官。你的职责是对方案进行无死角拷问——挖掘隐藏假设、暴露边界情况、质疑每一个决策。

按以下维度逐个审查，每个维度都问自己"这里可能出什么问题？"：

1. 正确性 — 方案逻辑上能跑通吗？有没有明显漏洞？
2. 完整性 — 缺了什么？有没有没覆盖到的场景？
3. 健壮性 — 什么情况下会挂？边界条件处理了吗？
4. 安全性 — 攻击面在哪？数据泄露、注入、权限等问题考虑了吗？
5. 性能 — 瓶颈在哪？高并发/大数据量下撑得住吗？
6. 可维护性 — 将来接手的人会骂娘吗？接口设计是否清晰？
7. 可测试性 — 怎么证明方案工作？关键路径能测试吗？
8. 替代方案 — 有没有更简单或更优的做法被忽略了？

输出（结构化 JSON）：
{
  "overall_assessment": "一句话总体评价",
  "continue": true/false,
  "severity_score": 1-10,
  "questions": [
    {
      "dimension": "correctness|completeness|robustness|security|performance|maintainability|testability|alternatives",
      "question": "具体问题，直击要害，不拐弯抹角",
      "why_it_matters": "为什么这个问题重要，不解决会导致什么后果",
      "severity": "critical|major|minor"
    }
  ],
  "strengths": ["方案中做得好的地方也要指出来"]
}

要求：
- 宁严勿松，早期放过一个问题后面要十倍代价修复
- 问题要具体，不要问泛泛而谈的——直接问具体场景和数值
- 但不要无中生有——如果某个维度方案处理得很好，就说好
- strengths 不能为空——总有几个做得对的地方
```

### 3.3 迭代上下文传递

每次 Designer 收到完整上下文：

```
【原始需求】
{用户最初的需求描述}

【上一轮方案】
{上一轮 Designer 输出的完整方案 JSON}

【拷问官反馈 — 第 N 轮】
{Griller 输出的 questions 列表 + overall_assessment + severity_score}
```

Designer 可对照 Griller 的问题逐条回应，不凭记忆修改。

## 4. 停止模式

### 4.1 交互模式（默认推荐）

- 每轮拷问后展示 Griller 的问题 + severity_score + Designer 修订摘要
- 用户决定：继续 / 停止输出 / 补充指导
- 支持不限制迭代轮数（用户随时喊停）

### 4.2 自动模式（Griller 判定）

- Griller 自行判定方案是否达标
- 两个停止信号：
  1. `continue: false` → 立即停止
  2. 连续 2 轮无 critical 问题 → 收敛停止
- **必须设置迭代上限**（3/5/8/10，默认 5），不允许不限制
- 到达上限强制停止，输出警告

### 4.3 模式与轮次约束

| 停止模式 | 可选迭代轮数 | 是否可选不限制 |
|----------|-------------|---------------|
| 交互 | 3 / 5（默认）/ 不限制 | ✅ |
| 自动 | 3 / 5（默认）/ 8 / 10 | ❌ |

## 5. 输入模式

### 5.1 自动检测

- 输入超过 200 字，或包含 `##`、`方案概述`、代码块 → Brownfield（打磨已有方案）
- 否则 → Greenfield（从零设计）

### 5.2 Greenfield 流程

1. Designer 接收用户需求 → 产出初版方案（v1）
2. 进入迭代循环：Griller 拷问 ↔ Designer 修订
3. 停止 → 输出最终方案

### 5.3 Brownfield 流程

1. 跳过初版设计，直接将用户已有方案作为 v1
2. Griller 直接拷问已有方案（首轮 prompt 强调"不要因为已成型就手下留情"）
3. 进入迭代循环：Griller 拷问 ↔ Designer 修订
4. 停止 → 输出最终方案

## 6. 技术实现

### 6.1 文件结构

```
.claude/workflows/design-grill.js   ← 工作流脚本（核心逻辑）
.claude/skills/design-grill/SKILL.md ← 用户入口（交互式引导）
```

### 6.2 Skill 交互引导

用户只需调用 `/design-grill`，skill 主动引导收集参数：

1. **需求/方案**（必填）：如果调用时已给则跳过
2. **输入模式自动检测**：向用户确认检测结果，错误则纠正
3. **停止模式**：A) 交互（默认） B) 自动
4. **最大迭代轮数**：根据停止模式提供不同选项
   - 交互：3 / 5（默认）/ 不限制
   - 自动：3 / 5（默认）/ 8 / 10

收集完成后展示总结，用户确认后启动 Workflow。

### 6.3 Workflow 脚本骨架

```js
export const meta = {
  name: 'design-grill',
  description: 'Designer 出方案 → Griller 拷问 → 迭代至收敛，产出高质量设计方案',
  phases: [
    { title: '设计', detail: 'Designer 产出或修订方案' },
    { title: '拷问', detail: 'Griller 多维度审查方案' },
  ],
}

const MAX_ITERATIONS = args.maxIterations === 0
  ? Infinity
  : (args.maxIterations || 5)
const MODE = args.mode || 'interactive'
const isGreenfield = !args.hasExistingPlan

let plan = null

// Phase 1: 初始设计（仅 greenfield）
if (isGreenfield) {
  phase('设计')
  plan = await agent(DESIGNER_PROMPT_INITIAL(args.requirement), {
    label: 'Designer 初版方案',
    schema: DESIGN_SCHEMA,
  })
}

// Phase 2: 迭代循环
let round = 0
let consecutiveNoCritical = 0

while (round < MAX_ITERATIONS) {
  phase('拷问')
  const grill = await agent(GRILLER_PROMPT(plan, round, args.requirement), {
    label: `Griller 第${round + 1}轮`,
    schema: GRILL_SCHEMA,
  })

  if (MODE === 'auto') {
    if (!grill.continue) break
    const criticals = grill.questions.filter(q => q.severity === 'critical')
    if (criticals.length === 0) {
      consecutiveNoCritical++
      if (consecutiveNoCritical >= 2) break
    } else {
      consecutiveNoCritical = 0
    }
  }

  // Designer 修订
  phase('设计')
  plan = await agent(DESIGNER_PROMPT_REVISE(plan, grill, args.requirement, round), {
    label: `Designer 修订第${round + 1}轮`,
    schema: DESIGN_SCHEMA,
  })

  round++
}

// Phase 3: 输出
log(`设计完成，共 ${round + 1} 轮迭代`)
return plan
```

### 6.4 调用方式

```bash
# 交互式引导（推荐）
/design-grill

# 带参数跳过部分引导
/design-grill "设计一个分布式日志收集系统"
/design-grill "设计日志系统" --mode auto
/design-grill --file ./my-design.md
```

## 7. 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 实现方式 | Workflow 脚本 + Skill 入口 | Workflow 提供确定性循环和结构化 schema；Skill 提供交互式引导 |
| 停止判定 | 交互 + 自动双模式 | 用户想参与就交互，想省事就自动 |
| 不限制轮次 | 仅交互模式可用 | 自动模式无人盯着，必须设上限防止死循环 |
| 收敛检测 | 连续 2 轮无 critical 问题 | 借鉴 GAN Harness 经验，防止在 minor 问题上无限循环 |
| 反馈方式 | 结构化 JSON | Griller 一次输出所有问题（agent-to-agent 不需要一问一答） |
| 迭代上下文 | 完整历史传递给 Designer | 每轮 Designer 看到原始需求 + 上轮方案 + Griller 反馈 |
| 审查维度 | 8 个固定维度 | 继承 grilling skill 精神，适配 agent-to-agent 交互模式 |

## 8. 借鉴的外部经验

| 借鉴点 | 来源 | 说明 |
|--------|------|------|
| 跨模型审查 | adversarial-spec + ARIS | Griller 优先用不同模型族效果更好 |
| 收敛检测 | GAN Harness | 连续 N 轮无改善则停止 |
| 反馈文件化 | GAN Harness | Griller 问题结构化输出，Designer 逐条回应 |
| 禁止 Griller 动手改 | GAN Harness | Griller 只提问题，永远不动手修改方案 |
| 第一轮校验 | adversarial-spec | 如果 Griller 首轮只提 minor 问题，提示再仔细看 |
| 8 维度审查 | grilling skill | 继承其"无死角深挖"精神 |
