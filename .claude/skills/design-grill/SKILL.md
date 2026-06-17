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

确认无误，现在启动...
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

### 第四步：输出最终方案

Workflow 返回结果后，执行以下操作：

1. 从返回结果中提取 `markdown`（方案文本）和 `filename`（建议文件名）
2. 将 `markdown` 内容写入文件，文件名使用返回的 `filename`
3. 向用户展示：

```
✅ 方案已生成并保存到: {filename}

📊 方案摘要:
{plan.summary}

你可以：
- 查看完整方案：打开 {filename}
- 继续拷问：告诉我你想针对哪个方面深入审查
- 基于方案开发：告诉我你想开始实现
```

## 参数速查

| 参数 | 说明 | 取值 |
|------|------|------|
| requirement | 需求描述 | 任意文本 |
| mode | 停止模式 | `interactive`（默认）/ `auto` |
| maxIterations | 最大轮数 | 0=不限制 / 3 / 5（默认）/ 8 / 10 |
| hasExistingPlan | 是否打磨已有方案 | `true` / `false` |
| existingPlan | 已有方案内容 | JSON 对象（hasExistingPlan=true 时必填） |
