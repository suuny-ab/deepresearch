// .claude/workflows/design-grill.js
// Design-Grill 双 Agent 协作工作流
// Designer 出方案 → Griller 拷问 → 迭代至收敛

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
    const criticalCount = grill.questions.filter(q => q.severity === 'critical').length
    const majorCount = grill.questions.filter(q => q.severity === 'major').length
    const minorCount = grill.questions.filter(q => q.severity === 'minor').length
    log(`  其中 critical: ${criticalCount}, major: ${majorCount}, minor: ${minorCount}`)
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

log(`\n设计完成，共 ${round + 1} 轮迭代。`)
return plan
