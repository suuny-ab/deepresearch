# Design-Grill 双 Agent 协作工作流实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现通用的"Designer 出方案 → Griller 拷问 → 迭代打磨"双 Agent 协作工作流。

**Architecture:** 两层结构——Skill（交互式引导 + 参数收集）→ Workflow 脚本（确定性循环 + agent 编排）。用户只需调用 `/design-grill`，skill 主动收集参数后启动 workflow。

**Tech Stack:** Claude Code Workflow 脚本（JavaScript）、Claude Code Skill（Markdown）

## Global Constraints

- Designer 和 Griller 提示词均为中文
- 结构化输出使用 JSON Schema，Griller 输出 `continue` 和 `questions[].severity` 供脚本做逻辑判断
- 交互模式支持不限制迭代轮数；自动模式必须设上限（3/5/8/10）
- Greenfield/Brownfield 自动检测：超过 200 字或含 `##`/`方案概述`/代码块 → Brownfield
- 收敛检测：连续 2 轮无 critical 问题 → 自动停止（自动模式）

---

### Task 1: Workflow 脚本 — Schema 定义与常量

**Files:**
- Create: `.claude/workflows/design-grill.js`

**Interfaces:**
- Produces: `DESIGN_SCHEMA` (object), `GRILL_SCHEMA` (object), `DESIGNER_PROMPT_INITIAL(requirement)` (function → string), `GRILLER_PROMPT(plan, round, requirement)` (function → string), `DESIGNER_PROMPT_REVISE(plan, grillResult, requirement, round)` (function → string)

- [ ] **Step 1: 创建 workflow 脚本骨架，包含 meta、Schema、Prompt**

```js
// .claude/workflows/design-grill.js
export const meta = {
  name: 'design-grill',
  description: 'Designer 出方案 → Griller 拷问 → 迭代至收敛，产出高质量设计方案',
  phases: [
    { title: '设计', detail: 'Designer 产出或修订方案' },
    { title: '拷问', detail: 'Griller 多维度审查方案' },
  ],
}

const DESIGN_SCHEMA = {
  type: 'object',
  properties: {
    summary: { type: 'string', description: '方案概述（2-3句话）' },
    core_architecture: { type: 'string', description: '核心架构设计，包含模块划分、关键抽象、技术选型' },
    key_design_decisions: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          decision: { type: 'string', description: '决策内容' },
          rationale: { type: 'string', description: '为什么这样做' },
          alternatives_considered: { type: 'string', description: '考虑过但放弃的方案及原因' }
        },
        required: ['decision', 'rationale', 'alternatives_considered']
      }
    },
    components: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string', description: '组件名' },
          responsibility: { type: 'string', description: '职责' },
          interface: { type: 'string', description: '对外接口' },
          dependencies: { type: 'string', description: '依赖' }
        },
        required: ['name', 'responsibility']
      }
    },
    data_flow: { type: 'string', description: '数据在各组件间的流转路径' },
    error_handling: { type: 'string', description: '各类失败场景及处理策略' },
    testing_strategy: { type: 'string', description: '如何验证方案正确性' },
    risks_and_mitigations: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          risk: { type: 'string' },
          severity: { type: 'string', enum: ['高', '中', '低'] },
          mitigation: { type: 'string' }
        },
        required: ['risk', 'severity', 'mitigation']
      }
    },
    open_questions: { type: 'array', items: { type: 'string' } },
    revision_history: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          round: { type: 'integer' },
          changes_made: { type: 'string' },
          griller_issues_addressed: { type: 'string' }
        },
        required: ['round', 'changes_made', 'griller_issues_addressed']
      }
    }
  },
  required: ['summary', 'core_architecture', 'key_design_decisions', 'components', 'risks_and_mitigations']
}

const GRILL_SCHEMA = {
  type: 'object',
  properties: {
    overall_assessment: { type: 'string', description: '一句话总体评价' },
    continue: { type: 'boolean', description: '是否还有值得提出的新问题（false=方案已足够完善）' },
    severity_score: { type: 'number', minimum: 1, maximum: 10, description: '方案当前质量分（10=无可挑剔）' },
    questions: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          dimension: {
            type: 'string',
            enum: ['correctness', 'completeness', 'robustness', 'security', 'performance', 'maintainability', 'testability', 'alternatives'],
            description: '审查维度'
          },
          question: { type: 'string', description: '具体问题，直击要害' },
          why_it_matters: { type: 'string', description: '为什么这个问题重要' },
          severity: { type: 'string', enum: ['critical', 'major', 'minor'], description: '严重程度' }
        },
        required: ['dimension', 'question', 'why_it_matters', 'severity']
      }
    },
    strengths: { type: 'array', items: { type: 'string' }, description: '方案中做得好的地方' }
  },
  required: ['overall_assessment', 'continue', 'severity_score', 'questions', 'strengths']
}

// Greenfield: Designer 从零设计方案
function DESIGNER_PROMPT_INITIAL(requirement) {
  return `你是一位资深系统/软件架构师。你的职责是产出深入、推理严谨的设计方案。

【用户需求】
${requirement}

请根据以上需求，产出一份完整的设计方案。每个设计决策都要给出理由。主动暴露风险。对不确定的地方标注为 open_questions。

输出要求：严格按指定的 JSON 结构返回。`
}

// Griller 拷问
function GRILLER_PROMPT(plan, round, requirement) {
  return `你是一位铁面无私的设计审查官。你的职责是对方案进行无死角拷问——挖掘隐藏假设、暴露边界情况、质疑每一个决策。

【原始需求】
${requirement}

【待审查方案 — 第 ${round + 1} 轮】
${JSON.stringify(plan, null, 2)}

按以下维度逐个审查，每个维度都问自己"这里可能出什么问题？"：

1. 正确性 — 方案逻辑上能跑通吗？有没有明显漏洞？
2. 完整性 — 缺了什么？有没有没覆盖到的场景？
3. 健壮性 — 什么情况下会挂？边界条件处理了吗？
4. 安全性 — 攻击面在哪？数据泄露、注入、权限等问题考虑了吗？
5. 性能 — 瓶颈在哪？高并发/大数据量下撑得住吗？
6. 可维护性 — 将来接手的人会骂娘吗？接口设计是否清晰？
7. 可测试性 — 怎么证明方案工作？关键路径能测试吗？
8. 替代方案 — 有没有更简单或更优的做法被忽略了？

要求：
- 宁严勿松，早期放过一个问题后面要十倍代价修复
- 问题要具体，不要问泛泛而谈的——直接问具体场景和数值
- 但不要无中生有——如果某个维度方案处理得很好，就说好
- strengths 不能为空——总有几个做得对的地方

输出要求：严格按指定的 JSON 结构返回。`
}

// Designer 修订已有方案
function DESIGNER_PROMPT_REVISE(plan, grillResult, requirement, round) {
  return `你是一位资深系统/软件架构师。你的方案经过了审查官的拷问，现在需要针对反馈进行修订。

【原始需求】
${requirement}

【上一轮方案】
${JSON.stringify(plan, null, 2)}

【拷问官反馈 — 第 ${round + 1} 轮】
总体评价: ${grillResult.overall_assessment}
质量评分: ${grillResult.severity_score}/10

具体问题：
${grillResult.questions.map((q, i) =>
  `${i + 1}. [${q.severity}] [${q.dimension}] ${q.question}\n   为什么重要: ${q.why_it_matters}`
).join('\n\n')}

请逐条回应拷问官的问题，修订方案。在 revision_history 中记录本轮变更。
如果拷问官提出的问题确实成立，修改方案；如果你认为某个问题不成立，解释原因。

输出要求：严格按指定的 JSON 结构返回。`
}
```

- [ ] **Step 2: 验证脚本语法**

```bash
# 检查 JS 语法（Node.js 环境）
node --check .claude/workflows/design-grill.js
```

---

### Task 2: Workflow 脚本 — 主循环逻辑

**Files:**
- Modify: `.claude/workflows/design-grill.js` — 追加主循环代码

**Interfaces:**
- Consumes: `DESIGN_SCHEMA`, `GRILL_SCHEMA`, `DESIGNER_PROMPT_INITIAL`, `GRILLER_PROMPT`, `DESIGNER_PROMPT_REVISE` (from Task 1)
- Produces: 主循环执行体（脚本入口）

- [ ] **Step 1: 追加主循环逻辑**

将以下代码追加到 `.claude/workflows/design-grill.js` 末尾：

```js
// ============================================================
// 主循环
// ============================================================

const MAX_ITERATIONS = args.maxIterations === 0
  ? Infinity
  : (args.maxIterations || 5)
const MODE = args.mode || 'interactive'
const isGreenfield = !args.hasExistingPlan
const requirement = args.requirement
const existingPlan = args.existingPlan

let plan = null

// Greenfield: Designer 先出初版方案
if (isGreenfield) {
  phase('设计')
  log('Designer 正在根据需求设计初版方案...')
  plan = await agent(DESIGNER_PROMPT_INITIAL(requirement), {
    label: 'Designer 初版方案',
    schema: DESIGN_SCHEMA,
  })
  if (!plan) {
    log('❌ Designer 初版方案生成失败，请重试。')
    return null
  }
  log(`初版方案完成。核心架构: ${plan.summary.slice(0, 80)}...`)
} else {
  // Brownfield: 直接使用用户提供的方案
  plan = existingPlan
  log('使用用户提供的已有方案作为起点。')
}

// 迭代循环
let round = 0
let consecutiveNoCritical = 0

while (round < MAX_ITERATIONS) {
  // Griller 拷问
  phase('拷问')
  log(`Griller 开始第 ${round + 1} 轮审查...`)
  const grill = await agent(GRILLER_PROMPT(plan, round, requirement), {
    label: `Griller 第${round + 1}轮`,
    schema: GRILL_SCHEMA,
  })

  if (!grill) {
    log('❌ Griller 调用失败，强制停止。')
    break
  }

  log(`第 ${round + 1} 轮审查完成 — 评分: ${grill.severity_score}/10, 问题数: ${grill.questions.length}`)
  if (grill.questions.length > 0) {
    log(`  其中 critical: ${grill.questions.filter(q => q.severity === 'critical').length}, major: ${grill.questions.filter(q => q.severity === 'major').length}, minor: ${grill.questions.filter(q => q.severity === 'minor').length}`)
  }

  // 自动模式下的停止判定
  if (MODE === 'auto') {
    if (!grill.continue) {
      log('✅ Griller 判定方案已完善，停止迭代。')
      break
    }

    const criticals = grill.questions.filter(q => q.severity === 'critical')
    if (criticals.length === 0) {
      consecutiveNoCritical++
      log(`连续 ${consecutiveNoCritical} 轮无 critical 问题。`)
      if (consecutiveNoCritical >= 2) {
        log('✅ 连续 2 轮无 critical 问题，收敛停止。')
        break
      }
    } else {
      consecutiveNoCritical = 0
    }
  }

  // 是否还有下一轮的机会
  round++
  if (round >= MAX_ITERATIONS) {
    log(`⚠️ 已达最大迭代轮数 (${MAX_ITERATIONS})，强制停止。`)
    break
  }

  // Designer 修订
  phase('设计')
  log(`Designer 正在根据拷问反馈修订方案（第 ${round + 1} 轮）...`)
  plan = await agent(DESIGNER_PROMPT_REVISE(plan, grill, requirement, round), {
    label: `Designer 修订第${round + 1}轮`,
    schema: DESIGN_SCHEMA,
  })

  if (!plan) {
    log('❌ Designer 修订失败，保留上一轮方案。')
    break
  }

  log(`修订完成。`)
}

log(`\n设计完成，共 ${round + 1} 轮迭代。最终评分: ${plan ? '见上' : 'N/A'}`)
return plan
```

- [ ] **Step 2: 验证完整脚本语法**

```bash
node --check .claude/workflows/design-grill.js
```

- [ ] **Step 3: Commit**

```bash
git add .claude/workflows/design-grill.js
git commit -m "feat: add design-grill workflow script — Designer+Griller adversarial loop"
```

---

### Task 3: Skill 入口文件

**Files:**
- Create: `.claude/skills/design-grill/SKILL.md`

**Interfaces:**
- Produces: `/design-grill` slash command（Claude Code 自动注册）

- [ ] **Step 1: 创建 SKILL.md**

```markdown
---
name: design-grill
description: 启动 Designer + Griller 双 Agent 协作，通过对抗性拷问迭代打磨设计方案。调用后主动引导用户，无需记忆任何参数。
---

# Design-Grill：设计-拷问 双 Agent 协作

启动一个 Designer（架构师）和一个 Griller（审查官）的对抗协作流程：
Designer 产出或修订方案 → Griller 多维度拷问 → Designer 回应 → 迭代至收敛。

## 流程

### 第一步：收集信息

按以下顺序引导用户。如果用户调用时已经给出了信息，跳过对应步骤。

#### 1. 需求/方案（必填）

如果用户在调用 `/design-grill` 时已经提供了需求描述或粘贴了已有方案，跳过此步。

否则问：
> 你想设计什么？给我一个简短的需求描述，或者直接粘贴已有方案让我帮你打磨。

#### 2. 输入模式检测

- 用户输入超过 200 字，或包含 `##`、`方案概述`、代码块（\`\`\`） → **Brownfield**（打磨已有方案）
- 否则 → **Greenfield**（从零设计）

向用户确认：
> 检测到这是一个{Greenfield 新需求/Brownfield 已有方案}，对吗？

如果用户说不对，让他指定正确的模式。

#### 3. 停止模式（如果没有通过 --mode 指定）

> 每轮拷问后，由谁来决定是否继续？
> - **A) 交互模式**（推荐）— 每轮展示拷问结果，你来决定继续还是停止
> - **B) 自动模式** — Griller 自行判定方案是否达标

#### 4. 最大迭代轮数

根据停止模式提供选项：

**交互模式：**
> 最多迭代几轮？
> - A) 3 轮 — 快速打磨
> - B) 5 轮 — 标准深度（推荐，直接回车即可）
> - C) 不限制 — 一直迭代到你喊停

**自动模式：**
> 最多迭代几轮？
> - A) 3 轮 — 快速打磨
> - B) 5 轮 — 标准深度（推荐，直接回车即可）
> - C) 8 轮 — 深度打磨
> - D) 10 轮 — 极致打磨

### 第二步：确认并启动

收集完成后，展示总结：

```
📋 确认信息：
- 需求/方案：{摘要}
- 流程类型：{Greenfield / Brownfield}
- 停止模式：{交互 / 自动}
- 最大轮数：{N 轮 / 不限制}

确认无误，开始启动...
```

然后调用 Workflow：

```
/workflow design-grill {requirement: "...", mode: "交互/自动", maxIterations: N, hasExistingPlan: true/false, existingPlan: ...}
```

mode 映射：交互 → `interactive`，自动 → `auto`
maxIterations 映射：不限制 → `0`

### 第三步：交互模式下的轮次把控

每轮拷问完成后：

1. 展示 Griller 的 `severity_score` 和问题摘要
2. 展示 Designer 修订摘要
3. 问用户：

> 第 {N} 轮拷问完成。Griller 评分 {X}/10，提出 {Y} 个问题（critical: {a}, major: {b}, minor: {c}）。
>
> Designer 已修订方案。是否继续下一轮？
> - **继续** — 进入下一轮拷问
> - **停止** — 输出当前方案
> - **补充指导** — 你在反馈中加入具体意见，Designer 据此修订后再拷问
```

- [ ] **Step 2: 验证 YAML frontmatter 格式**

```bash
# 确认 SKILL.md 的 YAML frontmatter 可解析（name 和 description 必填）
head -10 .claude/skills/design-grill/SKILL.md
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/design-grill/SKILL.md
git commit -m "feat: add design-grill skill — interactive entry point for design-grill workflow"
```

---

### Task 4: 端到端验证

**Files:**
- 无新建文件

- [ ] **Step 1: 确认文件结构完整**

```bash
ls -la .claude/workflows/design-grill.js
ls -la .claude/skills/design-grill/SKILL.md
```

- [ ] **Step 2: 验证 workflow 脚本语法**

```bash
node --check .claude/workflows/design-grill.js
```
Expected: 无错误输出，退出码 0

- [ ] **Step 3: 验证 SKILL.md frontmatter 格式**

```bash
head -6 .claude/skills/design-grill/SKILL.md
```
Expected: `---` 包裹的 YAML，包含 `name: design-grill` 和 `description:`

- [ ] **Step 4: 验证 Skill 可被发现**

```bash
ls .claude/skills/design-grill/
```
Expected: 目录存在且包含 `SKILL.md`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: finalize design-grill workflow — verification complete"
```
