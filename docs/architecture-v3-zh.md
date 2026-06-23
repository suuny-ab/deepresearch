# React V3 架构设计

> **版本:** v1.0
> **状态:** 最终版 -- 已通过 1 轮设计审查（Griller 审查 v1，15 个问题全部解决）
> **日期:** 2026-06-18
> **设计者:** React V3 架构团队
> **受众:** 负责实现 V3 多智能体研究流水线的工程团队

---

## 执行摘要

React V3 是一个**多智能体研究架构**，用 8 个由线程安全、预算感知的 Supervisor 编排的专用 Agent，替换了 V2 固定的 LangGraph 流水线。

**相比 V2（graph_v2）的关键改进：**

| 维度 | V2 局限性 | V3 解决方案 |
|------|----------|-----------|
| 查询处理 | 原始问题字符串到处传递 | **ResearchBrief** 上下文压缩 + 业务规则校验 |
| 澄清机制 | 无 | **Triage + Clarifier Agent**，支持交互式和自动解决模式 |
| 并行安全 | 发射后不管的 ThreadPoolExecutor | **线程安全的 Supervisor**，带 `threading.Lock`、超时、预算执行 |
| 报告审查 | 被动 critic 日志，不触发重写 | **5 维度评分标准**（70% 阈值，最多 2 次重写） |
| 质量门 | 写入前无检查 | **写入前验证门**，关键矛盾阻断写入 |
| 成本控制 | 隐式（迭代次数限制） | **显式预算**：`total_llm_call_budget`、`per_subagent_timeout`、`pipeline_timeout` |
| API 兼容性 | 仅 CLI | **非交互式回退** 使 Clarifier 可在服务端模式下工作 |

**LLM 调用预算：** 每次运行 8~28 次调用（按深度模式分档：快速/标准/深度），通过流水线启动前成本预估和运行时预算监控执行。按 DeepSeek 定价估算成本：$0.003~$0.024/次。

**实现计划：** 6 个阶段，5 周，从 `runner.py` 的 `build_agent()` 重构为策略/插件注册模式开始。V2 和 V3 通过 `--architecture` CLI 标志共存。

**风险概况：** 全部 7 个风险均有缓解措施。两个关键风险（Supervisor 竞态条件、API 模式下 Clarifier 阻塞）已在本修订中修复。剩余最高风险是深度模式下的 LLM 调用成本，通过预算门和强制深度分档限制来应对。

---

## 目录

1. [架构概览](#1-架构概览)
2. [Agent 定义](#2-agent-定义)
3. [完整工作流](#3-完整工作流)
4. [关键设计决策与权衡](#4-关键设计决策与权衡)
5. [工具系统设计](#5-工具系统设计)
6. [状态管理](#6-状态管理)
7. [上下文工程策略](#7-上下文工程策略)
8. [结构化输出定义](#8-结构化输出定义)
9. [对比矩阵：V2 vs V3](#9-对比矩阵v2-vs-v3)
10. [实现路径](#10-实现路径)
11. [修订日志](#11-修订日志)

---

## 1. 架构概览

### 拓扑结构

```
                                User Query（用户查询）
                                     |
                                     v
               ┌─────────────────────────────────────────┐
               │           [1] Triage Agent               │
               │  判断：清晰度、范围、格式、              │
               │  紧急程度、路由决策                       │
               │  输出: TriageDecision(route, flags)      │
               └────────────────┬────────────────────────┘
                                |
                    ┌───────────┴───────────┐
                    v                       v
        ┌─────────────────────┐   ┌──────────────────────┐
        │ 需要澄清             │   │   足够清晰             │
        └─────────────────────┘   └──────────────────────┘
                    |                       |
                    v                       v
  ┌──────────────────────────────┐ ┌──────────────────────────────┐
  │  [2] Clarifier Agent         │ │  [3] Instruction Builder      │
  │  多轮对话 OR                  │ │  将澄清后的查询压缩为         │
  │  自动解决回退                 │ │  ResearchBrief                │
  │  最多 3 轮 / 自动默认值       │ │  + 业务规则校验               │
  └──────────────────────────────┘ └──────────────────────────────┘
                    |                       |
                    └───────────┬───────────┘
                                v
               ┌──────────────────────────────────────────────────┐
               │           ResearchBrief（已验证）                  │
               │  业务规则检查：非空问题、                          │
               │  有效 time_range、深度一致性、                     │
               │  预算一致性                                        │
               │  验证失败时重试（最多 1 次），                      │
               │  二次失败则回退到安全默认值                         │
               └──────────────────────────────────────────────────┘
                                |
                                v
               ┌──────────────────────────────────────────────────┐
               │      [4] Research Supervisor Agent               │
               │  解析 ResearchBrief，创建                          │
               │  SubQuestionRegistry（线程安全）                   │
               │  分配子问题、监控进度、                            │
               │  决定终止条件                                      │
               │  执行：per_subagent_timeout、                      │
               │  total_search_budget、LLM 调用预算                 │
               │  线程安全：registry 上的 threading.Lock            │
               └────────────────┬─────────────────────────────────┘
                                |
                    ┌───────────┼───────────┐
                    v           v           v
        ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
        │ [5] Sub-Research │ │ [5] Sub-Research │ │ [5] Sub-Research │
        │     Agent 1      │ │     Agent 2      │ │     Agent 3      │
        │ (子问题 q1)       │ │ (子问题 q2)       │ │ (子问题 q3)       │
        │                   │ │                   │ │                   │
        │ search_web()      │ │ search_web()      │ │ search_web()      │
        │ fetch()           │ │ fetch()           │ │ fetch()           │
        │ fact_check()      │ │ fact_check()      │ │ fact_check()      │
        │ extract()         │ │ extract()         │ │ extract()         │
        │                   │ │                   │ │                   │
        │ 输出:              │ │ 输出:              │ │ 输出:              │
        │ AgentResult        │ │ AgentResult        │ │ AgentResult        │
        │ (SearchResult[] +  │ │ (SearchResult[] +  │ │ (SearchResult[] +  │
        │ EvidenceCard[] +   │ │ EvidenceCard[] +   │ │ EvidenceCard[] +   │
        │ TokenUsage[] +     │ │ TokenUsage[] +     │ │ TokenUsage[] +     │
        │ contradictions[])  │ │ contradictions[])  │ │ contradictions[])  │
        └───────────────────┘ └───────────────────┘ └───────────────────┘
                    |                   |                   |
                    └───────────────────┼───────────────────┘
                                        v
               ┌──────────────────────────────────────────────────┐
               │     [6] Evidence Consolidator Agent              │
               │  输入: 所有子 Agent 的 AgentResult[]              │
               │  工作: 1) 证据卡片语义去重                        │
               │        2) 跨子问题交叉印证                        │
               │        3) 矛盾检测                                │
               │        4) 证据质量评分                            │
               │        5) 写入前验证门:                           │
               │           - 未解决矛盾 -> 警告                    │
               │           - 子问题 < 2 张卡片 -> 覆盖缺口         │
               │           - 关键矛盾 -> 阻断                      │
               │  输出: ConsolidatedEvidence                       │
               └──────────────────────────────────────────────────┘
                                        |
                                        v
               ┌──────────────────────────────────────────────────┐
               │      [7] Writing Agent                           │
               │  输入: ConsolidatedEvidence + ResearchBrief       │
               │  + pre_write_warnings                             │
               │  一次性报告生成，使用 [N] 引用格式                 │
               │  引用校验（第二次尝试时绕过）                       │
               │  输出: Report（markdown 字符串）                   │
               └──────────────────────────────────────────────────┘
                                        |
                                        v
               ┌──────────────────────────────────────────────────┐
               │    [8] Multi-Dimension Review Agent              │
               │  从 5 个维度评估报告（每项 0-100 分）:            │
               │  - 事实准确性 (FA)  权重 30%                     │
               │  - 覆盖完整性 (CO)  权重 25%                      │
               │  - 推理质量 (RQ)    权重 20%                      │
               │  - 引用质量 (CI)    权重 15%                      │
               │  - 清晰度/结构 (CS) 权重 10%                      │
               │  综合分 >= 70 通过；否则重写（最多 2 次）          │
               └────────────────┬─────────────────────────────────┘
                                |
                     ┌──────────┴──────────┐
                     v                     v
                 (通过)               (失败 + 重试次数 < 2)
                     |                     |
                     v                     v
          ┌─────────────────────┐ ┌─────────────────────┐
          │  最终报告             │ │  Writing Agent       │
          │  + 审查摘要           │<│  （附带审查反馈）     │
          │                     │ │                      │
          └─────────────────────┘ └─────────────────────┘
```

### 预算执行门

```
                    ┌──────────────────────────────────────┐
                    │   流水线预算检查                       │
                    │   在 Phase 2 之前: projected_cost      │
                    │   <= budget?                          │
                    │   是 -> 继续                           │
                    │   否 -> 中止并给出警告                  │
                    └──────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │   Supervisor 预算监控                  │
                    │   每次子 Agent 完成后:                  │
                    │   total_llm_calls <= budget?          │
                    │   否 -> 将剩余待处理项标记为已完成      │
                    └──────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │   每个 SubAgent 超时控制               │
                    │   concurrent.futures.timeout          │
                    │   on future.result(timeout)           │
                    │   超时 -> 标记为 saturated（饱和）      │
                    │   -> 释放槽位                          │
                    └──────────────────────────────────────┘
```

### 数据流总结

```
User -> [Triage] -> [Clarify | Build] -> ResearchBrief (validated)
  -> [Supervisor with budget watch]
  -> [SubAgent x N with TokenUsage tracking + timeout]
  -> AgentResult[] -> [Consolidator with pre-write gate]
  -> ConsolidatedEvidence -> [Writer] -> Report -> [Reviewer] -> FinalReport
```

---

## 2. Agent 定义

### 2.1 Triage Agent（分流 Agent）

```python
class TriageInput(BaseModel):
    query: str
    conversation_history: list[dict] = []
    user_context: dict = {}          # 来自 ResearchMemory
    interactive: bool = True         # 用户是否可以对澄清做出响应


class TriageDecision(BaseModel):
    route: Literal["clarify", "direct_to_research"]
    clarity_flags: list[str] = []
    # 标记哪些地方不清楚:
    #   "ambiguous_scope"（范围模糊）, "missing_constraints"（缺少约束）,
    #   "format_unclear"（格式不明确）, "multiple_interpretations"（多重解读）,
    #   "needs_time_range"（需要时间范围）, "needs_geo_focus"（需要地域聚焦）
    suggested_clarifications: list[str] = []
    confidence: float                # 0.0-1.0 路由置信度
    estimated_depth: Literal["quick", "standard", "deep"] = "standard"
```

**职责：** 检查原始用户查询，决定是需要澄清还是可以直接进入指令构建。这是一个轻量级的单次 LLM 调用关口。

**非交互式感知：** 当 `TriageInput.interactive == False`（API/服务端模式）时，Triage Agent 倾向于 `"direct_to_research"`，除非查询从根本上不明确（confidence < 0.3）。这防止 Clarifier 在非交互式上下文中阻塞。

### 2.2 Clarifier Agent（澄清 Agent）

```python
class ClarifierTurn(BaseModel):
    question: str                    # 向用户提出的问题
    options: list[str] = []          # 建议答案
    rationale: str                   # 为什么这个问题有助于澄清


class ClarifierResult(BaseModel):
    clarified_query: str             # 合并后的用户需求表达
    answered_questions: list[dict] = []  # [{question, answer}]
    auto_resolved: bool = False      # 是否使用了回退默认值
```

**职责：** 与用户进行最多 3 轮来回对话，收集缺失信息。每轮提出一个问题（附带 2-3 个建议答案）。所有 clarity_flags 解决后提前停止。

**非交互式回退：** 当 `interactive == False` 时，Clarifier 使用自动解决逻辑：
1. 对每个 clarity_flag，使用合理的默认值（如 `time_range="recent"`, `geo_focus="global"`, `format_preference="report"`）
2. 将所有默认值合并到 clarified_query 中，加上 `[Auto-resolved]` 前缀
3. 设置 `auto_resolved = True`
4. 澄清轮次不进行实际的 LLM 调用

这使得 V3 流水线无需修改即可在 API 服务端模式下工作。

### 2.3 Instruction Builder Agent（指令构建 Agent）

```python
class ResearchBrief(BaseModel):
    """精简后的研究任务书 -- 替代原始用户查询。
    在 LLM 生成后通过业务规则检查进行验证。
    """
    clarified_question: str           # 澄清后的问题
    time_range: str = "recent"        # "past_year"（过去一年）, "past_5_years"（过去五年）, "all_time"（所有时间）等
    geo_focus: str = "global"         # 地域聚焦
    format_preference: Literal["report", "comparison", "analysis", "summary"] = "report"
    constraints: list[str] = []       # 排除的来源、观点等
    depth_indicator: Literal["quick", "standard", "deep"] = "standard"
    seed_subquestions: list[str] = [] # 2-3 个 LLM 生成的起始角度
    target_audience: str = "general"  # "expert"（专家）, "general"（通用）, "executive"（高管）
    special_instructions: str = ""

    @model_validator(mode="after")
    def validate_seed_subquestions(self) -> "ResearchBrief":
        if not self.seed_subquestions:
            self.seed_subquestions = [self.clarified_question]
        return self

    @model_validator(mode="after")
    def validate_depth_consistency(self) -> "ResearchBrief":
        if self.depth_indicator == "quick" and len(self.seed_subquestions) > 3:
            self.seed_subquestions = self.seed_subquestions[:3]
        return self

    @model_validator(mode="after")
    def validate_time_range(self) -> "ResearchBrief":
        valid_ranges = {"recent", "past_year", "past_5_years", "all_time"}
        if self.time_range not in valid_ranges:
            self.time_range = "recent"  # 默认回退
        return self
```

**职责：** 将用户澄清后的查询（或直接查询，如果不需要澄清）压缩为结构化的、机器可读的研究简报。这是关键的上下文工程点：该简报替代下游 Agent 的所有先前对话历史。

**验证步骤：** LLM 生成原始 ResearchBrief 后，运行 Pydantic 验证和业务规则检查：
- `seed_subquestions` 必须非空（为空时用 `[clarified_question]` 填充）
- `depth_indicator` 必须与其他字段一致（quick 模式将子问题限制为 3 个）
- `time_range` 必须是已知值之一（无效时回退到 "recent"）
- 验证失败时尝试一次 LLM 重试（将验证错误传回）
- 第二次尝试也失败时，回退到默认值并标记警告

### 2.4 Research Supervisor Agent（研究监督 Agent）

```python
class SubQuestionRegistry(BaseModel):
    """由 Supervisor 管理 -- 跟踪所有子问题。"""
    entries: list[SubQuestionEntry] = []

    def get_entry(self, id: str) -> SubQuestionEntry | None:
        for e in self.entries:
            if e.id == id:
                return e
        return None

    def update_status(self, id: str, status: str) -> None:
        entry = self.get_entry(id)
        if entry:
            entry.status = status


class SubQuestionEntry(BaseModel):
    id: str
    question: str
    rationale: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    search_count: int = 0
    extracts_count: int = 0
    card_count: int = 0
    result: AgentResult | None = None


class SupervisorAction(BaseModel):
    action: Literal["start_agent", "check_progress", "reassign", "finalize"]
    subquestion_ids: list[str] = []
    rationale: str = ""
```

**职责：** 管理子研究 Agent 的生命周期。Supervisor 执行以下操作：
1. 接收 `ResearchBrief` 并创建 2-5 个 `SubQuestionEntry`
2. 管理并行执行槽位池（默认 3 个）
3. 决定何时启动新的子 Agent、何时等待正在运行的 Agent
4. 监控饱和状态（某个子问题在 3 次搜索后无新发现）
5. 检测死胡同并重新分配剩余范围
6. 当所有子问题完成/饱和时发出研究完成信号
7. 执行预算和超时限制
8. 使用线程安全的状态管理

**上下文隔离：** Supervisor 看不到搜索结果或证据卡片。它只能看到每个 SubQuestionEntry 的元数据（状态、计数）。

**线程安全的 Supervisor 实现：**

```python
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError


class ResearchSupervisor:
    def __init__(self, llm, tools, ctx: RunContext):
        self._llm = llm
        self._tools = tools
        self._ctx = ctx
        self._registry = SubQuestionRegistry()
        self._lock = threading.Lock()                 # 保护所有 registry 修改
        self._total_llm_calls = 0
        self._running_futures: dict[Future, str] = {}
        self._errors: list[str] = []

    def _safe_update(self, sq_id: str, **updates):
        """线程安全地更新 SubQuestionEntry。"""
        with self._lock:
            entry = self._registry.get_entry(sq_id)
            if entry:
                for k, v in updates.items():
                    setattr(entry, k, v)

    def _safe_acquire_slot(self) -> bool:
        """线程安全的槽位可用性检查。"""
        with self._lock:
            running = sum(1 for e in self._registry.entries if e.status == "running")
            return running < self._ctx.config.max_parallel_agents

    def run(self) -> list[AgentResult]:
        self._plan_subquestions()

        results: list[AgentResult] = []
        with ThreadPoolExecutor(
            max_workers=self._ctx.config.max_parallel_agents
        ) as executor:
            while self._has_pending():
                if not self._check_llm_budget():
                    self._finalize_remaining("budget_limit")
                    break

                pending = self._next_pending(
                    limit=self._ctx.config.max_parallel_agents
                )
                for sq in pending:
                    self._safe_update(sq.id, status="running")
                    future = executor.submit(
                        self._run_one_agent,
                        sq,
                    )
                    self._running_futures[future] = sq.id

                for future in as_completed(
                    self._running_futures,
                    timeout=self._ctx.config.pipeline_step_timeout,
                ):
                    sq_id = self._running_futures.pop(future)
                    try:
                        result = future.result(
                            timeout=self._ctx.config.per_subagent_timeout
                        )
                        results.append(result)
                        self._safe_update(sq_id, status="completed", result=result)
                        self._total_llm_calls += self._count_llm_calls(result)
                    except TimeoutError:
                        self._errors.append(f"Agent {sq_id} timed out")
                        self._safe_update(sq_id, status="skipped")
                    except Exception as exc:
                        self._errors.append(f"Agent {sq_id} failed: {exc}")
                        self._safe_update(sq_id, status="failed")

        return results

    def _check_llm_budget(self) -> bool:
        return self._total_llm_calls < self._ctx.config.total_llm_call_budget
```

### 2.5 Sub-Research Agent（子研究 Agent）

```python
class AgentResult(BaseModel):
    """单个 Sub-Research Agent 运行的输出。"""
    subquestion_id: str
    subquestion: str
    search_results: list[SearchResult] = []
    evidence_cards: list[EvidenceCard] = []
    visited_urls: list[str] = []
    errors: list[str] = []
    token_usage: list[TokenUsage] = []
    steps: list[AgentStep] = []
    saturated: bool = False
    contradictions_found: list[str] = []


class AgentStep(BaseModel):
    """子 Agent 研究循环中的单次操作。"""
    iteration: int
    action: str                               # "search"、"fetch"、"extract" 等
    query: str = ""
    result_summary: str = ""
    urls: list[str] = []
    contradictions_found: list[str] = []
```

**职责：** 为一个子问题执行完整的研究循环：
1. 基于子问题生成 2-3 个搜索查询
2. 对每个搜索结果，获取/提取完整内容
3. 从获取的内容中提取证据卡片
4. 在子问题的来源范围内交叉验证声明
5. 循环直到饱和或达到最大迭代次数

**每个子 Agent 是隔离的：** 它只知道自己的子问题，拥有自己的工具调用。它永远不会看到其他子问题的数据。

**从 V2 继承：** 每个子问题的研究循环模式（search -> extract -> validate）直接从 V2 的 `subquestion_agent.py` 继承。V3 新增：带饱和检测的迭代循环、TokenUsage 跟踪和矛盾保留。

**每次 LLM 调用的 TokenUsage 跟踪：**

```python
class SubResearchAgent:
    def _plan_queries(self) -> list[str]:
        prompt = build_search_plan_prompt(self._sq.question)
        text, llm_usage = self._llm.complete(prompt)
        self._usage.append(TokenUsage(
            node=f"subagent_{self._sq.id}_plan",
            prompt_tokens=llm_usage.prompt_tokens,
            completion_tokens=llm_usage.completion_tokens,
            estimated_cost=llm_usage.estimated_cost,
        ))
        return parse_queries(text)

    def _extract_cards(self) -> list[EvidenceCard]:
        prompt = build_extraction_prompt(self._sq.question, self._sources)
        text, llm_usage = self._llm.complete(prompt)
        self._usage.append(TokenUsage(
            node=f"subagent_{self._sq.id}_extract",
            prompt_tokens=llm_usage.prompt_tokens,
            completion_tokens=llm_usage.completion_tokens,
            estimated_cost=llm_usage.estimated_cost,
        ))
        return parse_cards(text)

    def run(self, max_iterations: int = 3) -> AgentResult:
        queries = self._plan_queries()
        for query in queries:
            result = self._tools.execute(...)
        cards = self._extract_cards()
        cards = self._cross_validate(cards)
        return AgentResult(
            subquestion_id=self._sq.id,
            evidence_cards=cards,
            token_usage=self._usage,
            contradictions_found=self._contradictions,
            visited_urls=list(self._visited_urls),
        )
```

### 2.6 Evidence Consolidator Agent（证据整合 Agent）

```python
class ConsolidatedEvidence(BaseModel):
    evidence_cards: list[EvidenceCard]
    contradictions: list[Contradiction] = []
    cross_agent_corroborations: int = 0
    quality_scores: dict[str, float] = {}
    coverage_gaps: list[str] = []
    pre_write_warnings: list[str] = []
    blocked: bool = False                    # True 时 Writer 不应继续


class Contradiction(BaseModel):
    topic: str
    claim_a: str
    agent_a: str
    source_a: str
    claim_b: str
    agent_b: str
    source_b: str
    explanation: str = ""
```

**职责：** 接收所有 `AgentResult` 对象，产生整合后的证据集：
1. **语义去重：** 合并关于同一事实的证据卡片
2. **跨子问题交叉印证：** 继承自 V2 的 `coordinator.py` 中的 `_detect_cross_agent_corroboration()`，当来自不同域的不同 Agent 确认同一声明时升级印证级别
3. **矛盾检测：** 继承自 V2 的混合 Jaccard+LLM 方法（coordinator.py 中的 `_detect_contradictions_llm()`）
4. **写入前验证门：** 在传递给 Writer 之前，检查：
   - 存在未解决的矛盾 -> 添加到 `pre_write_warnings`
   - 任何子问题的证据卡片少于 2 张 -> 添加到 `coverage_gaps`
   - 关键事实上的矛盾 -> 设置 `blocked = True`

```python
class EvidenceConsolidator:
    def _pre_write_gate(
        self, consolidated: ConsolidatedEvidence
    ) -> ConsolidatedEvidence:
        warnings = []

        if consolidated.contradictions:
            consolidated.pre_write_warnings.append(
                f"{len(consolidated.contradictions)} contradiction(s) detected: "
                + "; ".join(c.topic for c in consolidated.contradictions[:3])
            )

        for sq_id, score in consolidated.quality_scores.items():
            if score < 0.3:
                consolidated.coverage_gaps.append(
                    f"Subquestion {sq_id} has low evidence quality ({score:.2f})"
                )

        critical = [
            c for c in consolidated.contradictions
            if self._is_high_confidence_contradiction(c, consolidated.evidence_cards)
        ]
        if len(critical) > 1:
            consolidated.blocked = True
            consolidated.pre_write_warnings.append(
                f"BLOCKED: {len(critical)} critical contradiction(s) unresolved. "
                "Writer cannot produce a coherent report."
            )

        return consolidated
```

### 2.7 Writing Agent（写作 Agent）

```python
class WriteFeedback(BaseModel):
    review_issues: list[str] = []
    review_suggestions: list[str] = []
    allowed_urls: set[str] = set()
```

**职责：** 从整合证据中一次性生成报告。与 V2 的 `build_writing_prompt` + `validate_citations` 机制相同，直接复用。Writer 只能看到 `ConsolidatedEvidence.evidence_cards`——看不到原始搜索结果。

**写入前警告感知：** 如果 `ConsolidatedEvidence.blocked == True`，Writer 拒绝写入，并返回包含覆盖缺口和矛盾列表的错误诊断。如果存在警告但未阻断，则将其作为建议性说明注入写作提示词。

### 2.8 Multi-Dimension Review Agent（多维度审查 Agent）

```python
from pydantic import BaseModel, Field


class ReviewRubric(BaseModel):
    factual_accuracy: int = Field(ge=0, le=100)     # 事实准确性
    coverage_completeness: int = Field(ge=0, le=100) # 覆盖完整性
    reasoning_quality: int = Field(ge=0, le=100)     # 推理质量
    citation_quality: int = Field(ge=0, le=100)      # 引用质量
    clarity_structure: int = Field(ge=0, le=100)     # 清晰度/结构


class ReviewResult(BaseModel):
    rubric: ReviewRubric
    composite_score: int = Field(ge=0, le=100)
    passed: bool
    issues: list[str] = []
    suggestions: list[str] = []
    can_improve: bool = True
```

**职责：** 多维度报告评估（V3 中真正新增的功能——V2 的 critic 只记录问题而不触发重写）。
1. 为 5 个维度分别打分，附带具体理由
2. 综合分 = 加权平均（FA:30%, CO:25%, RQ:20%, CI:15%, CS:10%）
3. 如果 composite >= 70 或达到重写次数上限（总计最多 2 次）-> 通过
4. 否则 -> 将 review_feedback 返回给 Writing Agent 进行重写
5. 每次重写尝试都包含前一次审查作为反馈

---

## 3. 完整工作流

### Phase 0: Triage（分流，1 次 LLM 调用）

```
1. 用户提交查询
2. Triage Agent 接收 TriageInput(query, interactive=True/False)
3. LLM 分类：route, clarity_flags, confidence, estimated_depth
4. 如果 route == "clarify" 且 interactive == True：进入 Phase 1A
5. 如果 route == "clarify" 且 interactive == False：
   -> 设置 auto_resolve 模式，使用默认值跳过并进入 Phase 1B
6. 如果 route == "direct_to_research"：跳过进入 Phase 1B
```

### Phase 1A: Clarification（澄清，0-3 次 LLM 调用，用户交互或自动解决）

```
1. Clarifier Agent 获取 TriageDecision.clarity_flags
2. 交互模式:
   a. 对每个 flag（最多 3 个），生成一个问题
   b. 用户回应（文本或从选项中选择）
   c. 更新 ClarifierResult.answered_questions
3. 自动解决模式:
   a. 对每个 clarity_flag 使用默认值
   b. 设置 ClarifierResult.auto_resolved = True
4. 构建最终的 clarified_query
5. 传递给 Instruction Builder
```

### Phase 1B: Instruction Building（指令构建，1 次 LLM 调用 + 验证）

```
1. Instruction Builder 接收（clarified_query 或原始 query）
2. LLM 生成包含所有字段的 ResearchBrief
3. ResearchBrief 通过 Pydantic model_validate 验证
4. 应用业务规则检查:
   - 非空 seed_subquestions
   - 有效的 time_range
   - 深度约束一致性
5. 验证失败 -> 用 LLM 重试一次（传入错误反馈）
6. 重试也失败 -> 回退到安全默认值，标记警告
7. 发布 "research_brief" 事件
8. ResearchBrief 是唯一传递给下游 Agent 的上下文
```

### Phase 2: Research Supervision + Execution（研究监督 + 执行，变化：5-25 次 LLM 调用）

```
1. Supervisor 接收 ResearchBrief
2. LLM 生成 SubQuestionRegistry（2-5 个子问题）
3. 流水线预算检查: projected_cost <= budget?
   否 -> 中止并给出 "budget exceeded" 消息
4. Supervisor 建立并行槽位池（默认 3 个）
5. 研究循环（线程安全）:
   a. 获取锁，检查可用槽位
   b. 选择下一个待处理的子问题
   c. 通过 ThreadPoolExecutor 启动 Sub-Research Agent
      使用 concurrent.futures.timeout（默认每个 Agent 120s）
   d. Sub-Research Agent 运行自己的循环:
      - Phase 2a: 生成 2-3 个搜索查询（1 次 LLM 调用，记录 TokenUsage）
      - Phase 2b: 执行搜索（工具调用，0 次 LLM）
      - Phase 2c: 获取/提取搜索结果（工具调用，0 次 LLM）
      - Phase 2d: 提取证据卡片（1 次 LLM 调用，记录 TokenUsage）
      - Phase 2e: 子问题内交叉验证（1 次 LLM 调用，记录 TokenUsage）
      - Phase 2f: 检查饱和状态；保留迄今发现的矛盾
      - Phase 2g: 如果未饱和且在预算内，循环到 2a
   e. 超时: 将子问题标记为 "skipped"，释放槽位
   f. 完成: 加锁，更新 SubQuestionEntry，释放槽位
   g. Supervisor 预算检查: total_llm_calls < budget?
      否 -> 将剩余待处理项标记为 "skipped"
6. Supervisor 发出 "research_complete" 信号，附带 AgentResult[]
```

### Phase 3: Evidence Consolidation（证据整合，1 次 LLM 调用 + 写入前门）

```
1. Consolidator 接收 AgentResult[]
2. 合并所有证据卡片，语义去重
3. 检测跨子问题交叉印证（复用 V2 coordinator 逻辑）
4. 通过 LLM 检测矛盾（复用 V2 混合方法）
5. 为每个子问题分配质量评分
6. 识别覆盖缺口（证据卡片 < 2 张的子问题）
7. 写入前验证门:
   a. 检查关键的未解决矛盾
   b. 矛盾过多 -> 设置 blocked=True
   c. 如果 blocked -> 返回覆盖缺口 + 矛盾列表
   d. 未阻断但存在警告 -> 作为建议性说明附加
8. 输出 ConsolidatedEvidence
```

### Phase 4: Writing（写作，1-2 次 LLM 调用，流式）

```
1. 检查 ConsolidatedEvidence.blocked
   如果 blocked -> 跳过写入，返回错误诊断
2. Writer 接收 ConsolidatedEvidence + ResearchBrief
3. 将 pre_write_warnings 作为建议性说明注入提示词
4. 构建写作提示词（复用 V2 的 build_writing_prompt）
5. 生成报告（流式输出）
6. 验证引用（复用 V2 的 validate_citations）
7. 如果失败且尝试次数 < 2：附带失败反馈重写
8. 输出最终报告字符串
```

### Phase 5: Review（审查，1-2 次 LLM 调用）

```
1. Reviewer 接收 Report + ConsolidatedEvidence
2. 为 5 个维度打分并附理由
3. 计算综合评分
4. 如果 composite >= 70 或重写次数 >= 2:
   - 标记为通过
   - 输出最终报告 + 审查摘要
5. 否则（composite < 70 且重写次数 < 2）:
   - 输出 review_feedback
   - Writer 根据反馈重写（计入重写次数，总计最多 2 次）
```

### LLM 调用总估量（含预算执行）

| 阶段               | 最少 | 最多 | 说明                                              |
|--------------------|------|------|---------------------------------------------------|
| Triage             | 1    | 1    | 单次分类                                          |
| Clarify            | 0    | 3    | 直接或自动解决时 0，交互时 1-3                     |
| Instruction Build  | 1    | 2    | 1 + 验证失败时的可选重试                           |
| Supervisor (plan)  | 1    | 1    | 子问题生成                                        |
| Sub-Agents (each)  | 2    | 6    | 每个子问题。预算上限：默认总计 15                  |
| Consolidation      | 1    | 1    | 写入前门是基于规则的，不调用 LLM                   |
| Writing            | 1    | 2    | 1 次初始 + 1 次可选重写                            |
| Review             | 1    | 2    | 1 次审查 + 1 次可选跟进                           |
| **总计 (quick)**   | **8**| **--**| 1+1+1+2x2+1+1+1 = 8-9                            |
| **总计 (standard)**| **--**| **18**| +1 澄清 + 3x3 子问题 + 可选重写                    |
| **总计 (deep)**    | **--**| **28**| +3 澄清 + 4x4 子问题 + 重写                        |

**预算执行：** `RunConfig.total_llm_call_budget` 限制总计调用次数。Quick=10, Standard=18, Deep=28。流水线在进入 Phase 2 前和每次子 Agent 完成后进行检查。

---

## 4. 关键设计决策与权衡

### 决策 1：多 Agent 流水线 vs 单 Agent 循环

**状态：** 相比 V2 的增强架构。

**理由：** OpenAI Deep Research 的基础是上下文隔离——每个 Agent 只看到它需要的上下文。V2 的单 Agent 循环（react_v2.py）将整个 workspace 带入每次 action prompt，导致 token 用量随迭代线性增长。

**V3 从 V2 继承了什么：** V2 的 `graph_v2.py` 已经实现了带并行子问题 Agent、coordinator 节点和独立 writer 节点的多 Agent 流水线。V3 将其形式化为显式的 Agent 角色。

**权衡：** 增加了 LLM 总调用次数（8-28 vs V2 的 ~10-15），但每次调用的提示词更小、更聚焦。由于并行化，实际端到端耗时反而**更低**。

**成本考量：** 8-28 次 LLM 调用，每次约 3K tokens = 每运行约 24K-84K tokens。按 DeepSeek 定价（$0.14/M 输入，$0.28/M 输出）：约 $0.003-$0.024/次。快速模式（8 次调用，约 24K tokens）：约 $0.003。深度模式（28 次调用，约 84K tokens）：约 $0.024。

### 决策 2：ResearchBrief 作为上下文压缩点

**状态：** V3 新增（V2 中没有等价物——原始问题字符串到处传递）。

**理由：** V2 中，原始 `question` 字符串被到处传递。如果用户进行了来回澄清，该历史会丢失或被不一致地整合。`ResearchBrief` Pydantic 模型将**所有**先前上下文（原始查询 + 澄清答案 + 推断的约束）压缩到单个结构化对象中。

**权衡：** 增加了 1-2 次 LLM 调用（Clarifier + Instruction Builder）。但下游 Agent 的提示词大小节省了 3-10 倍，因为它们不需要对话历史。

### 决策 3：带 Supervisor 的并行子研究 Agent

**状态：** 相比 V2 增强（graph_v2.py 中已存在）。

**V2 已有的：** `graph_v2.py` 使用 `ThreadPoolExecutor` 并行化子问题 Agent（第 90-101 行），每个运行独立的 search-extract-validate 流水线。

**V3 新增：** 显式的 Supervisor 角色，具有生命周期管理、饱和检测、预算执行、超时控制和线程安全状态管理。V2 的 Agent 执行是发射后不管（收集结果，无执行中监控）。

**权衡：** 并行的子 Agent 增加了 LLM 总调用次数，但减少了端到端耗时。V3 增加了 V2 缺乏的预算门和超时处理。

### 决策 4：LLM 驱动的证据整合

**状态：** 相比 V2 增强。

**V2 已有的：** `coordinator.py` 实现了跨 Agent 印证检测（第 78-147 行）、混合 Jaccard+LLM 矛盾检测（第 295-414 行）和全面的证据合并。

**V3 新增：** 覆盖缺口分析（标记证据不足的子问题）、每个子问题的质量评分、可在关键矛盾未解决时阻断 Writer 的写入前验证门。

**权衡：** 相比 V2 增加了 1 次 LLM 调用。写入前门避免了在有矛盾证据上浪费 Writer 调用，在失败场景中节省了 2+ 次 LLM 调用。

### 决策 5：带重写循环的多维度审查

**状态：** V3 中真正新增的功能。

**理由：** V2 的 critic（react_v2.py 第 853-888 行的 `_critique_report()`）是单次 LLM 调用，将问题记录到 `errors[]` 但从未触发重写。V3 的 Review Agent 使用结构化的 5 维度评分标准，具有明确的通过/失败阈值（70/100）和最多 2 次重写循环。

**权衡：** 增加了 1-2 次 LLM 调用。但结构化审查能够捕获更多问题，重写循环确保输出前的最低质量。

### 决策 6：工具系统——扩展现有 Registry，推迟 MCP

**状态：** 复用 V2 的 `ToolRegistry`，推迟 MCPToolAdapter。

**理由：** V2 的 `ToolRegistry` 是一个简单、经过充分测试的容器，具有 `register()` 和 `execute()` 方法。创建并行的 `MCPToolRegistry` 需要维护两个独立的注册系统。由于尚未使用 MCP 服务器，MCP 适配器增加了复杂性而没有直接收益。

**V3 方案：** 扩展 `ToolRegistry`，增加可选的 `mcp_servers` 字典。未配置 MCP 服务器时，其行为与 V2 的 registry 完全相同。当 MCP 服务器可用时，工具查找先检查本地工具，再检查 MCP 服务器。

**推迟：** `MCPToolAdapter` 和完整的 MCP 集成推迟到 Phase 5（生产就绪）。

### 决策 7：Clarifier 的非交互式回退

**状态：** V3 新增（修复了原始设计中的关键缺陷）。

**理由：** 原始 V3 设计假定仅 CLI 交互。现有代码库已有 `server.py`（API 服务器），Clarifier Agent 会在非交互模式下阻塞。添加 `ClarifierMode` 和 `auto_resolve` 回退使流水线在 CLI 和 API 上下文中都能工作。

**权衡：** 自动解决可能错过交互式澄清能够捕获的细微之处。

### 决策 8：线程安全的 Supervisor 状态

**状态：** V3 新增（修复了原始设计中的关键正确性缺陷）。

**理由：** 原始设计使用 `ThreadPoolExecutor` 并发写入 `SupervisorState.running_agents` 字典——典型的竞态条件。修订后的设计使用 `threading.Lock` 保护所有状态修改。

**与 V2 的对比：** V2 的 `graph_v2.py` 使用发射后不管模式的 `ThreadPoolExecutor`——提交所有 Agent，然后收集结果。不存在并发状态更新，因为每个 Agent 返回独立的 `AgentResult`，coordinator 顺序处理它们。V3 的 Supervisor 需要线程安全，因为它在执行过程中监控和修改 registry 状态。

### 决策 9：剪枝保留矛盾历史

**状态：** V3 原始设计中的 bug 修复。

**理由：** 原始的 `prune_subagent_history()` 丢弃了中间矛盾，丢失了有价值的信息。修订版本保留每次迭代中的 `contradictions_found`，并将其包含在最终的 `AgentResult` 中。

### 决策 10：上下文隔离 vs 交叉印证之间的张力

**状态：** 已确认的设计张力，通过可配置隔离来应对。

**理由：** 上下文隔离防止子 Agent 之间的交叉污染，但跨子问题交叉印证需要比较不同子问题的声明。这些目标存在内在张力：完美隔离使交叉印证成为不可能。

**解决方案：**
- 子 Agent 在研究时真正隔离运行（不知道其他子问题的存在）
- Consolidator 在合并时使用 LLM 语义相似度显式地重新关联
- 隔离级别可通过 `RunConfig.isolation_level` 配置：从严格（无跨子问题上下文）到宽松（子 Agent 接收兄弟子问题的简短摘要）

**默认设置：** 研究时严格隔离，整合时完全可见。

---

## 5. 工具系统设计

### 架构（简化——复用现有 V2 系统）

```
Tool (Protocol, 与 V2 相同)
+-- TavilySearchTool          (复用 V2)
+-- WebFetchTool              (复用 V2)
+-- TavilyExtractTool         (复用 V2)
+-- CompareSourcesTool        (复用 V2)
+-- FactCheckTool             (复用 V2)
+-- MCPToolAdapter            (推迟到 Phase 5)
```

### Tool Registry（扩展，而非替换）

```python
# tools/registry.py -- 现有 V2 类，扩展了 MCP 支持

class ToolRegistry:
    """兼容 V2 的工具注册表，扩展了可选的 MCP 服务器支持。"""

    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        self._mcp_servers: dict[str, MCPServer] = {}   # 可选，Phase 5
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: Tool) -> None:
        """添加本地工具（与 V2 相同）。"""
        self._tools[tool.name] = tool

    def register_mcp_server(self, name: str, server: MCPServer) -> None:
        """注册 MCP 服务器（推迟，Phase 5 前不执行任何操作）。"""
        self._mcp_servers[name] = server

    def execute(self, name: str, **kwargs) -> ToolResult:
        tool = self._tools.get(name)
        if tool:
            return tool.execute(**kwargs)
        # 回退到 MCP 服务器（Phase 5）
        for srv in self._mcp_servers.values():
            if srv.has_tool(name):
                return srv.call_tool(name, **kwargs).to_tool_result()
        return ToolResult(
            error=f"Unknown tool: {name}. Available: {sorted(self._tools.keys())}"
        )

    def describe_tools(self) -> str:
        lines = ["Available tools:"]
        for name in sorted(self._tools):
            tool = self._tools[name]
            lines.append(f"\n## {name}")
            lines.append(f"Description: {tool.description}")
            lines.append(f"Parameters: {tool.parameters}")
        return "\n".join(lines)
```

**关键简化：** 没有 `MCPToolRegistry` 类。没有双 registry 维护负担。一个 `ToolRegistry` 处理本地和 MCP 工具，未配置 MCP 时行为零变化。

### Sub-Research Agent 中的工具执行

每个子 Agent 接收一个共享的（只读）`ToolRegistry` 引用。维护内部可变状态的工具实例（缓存、计数器）被识别出来，其共享状态路径被文档化，而非假装存在完美隔离。

**工具中已知的共享状态：**
1. `TavilyKeyPool`——应用级单例，在所有 Agent 间共享。通过连接池而非隔离来缓解。不影响数据完整性（仅影响限流）。
2. `ResearchMemory` 单例——由 Supervisor 进行共享写入（用于元学习），不由子 Agent 写入。子 Agent 不写入 ResearchMemory。
3. 工具缓存——如果任何工具维护内部缓存，它是共享的。这通常是有益的（去重）且不是数据完整性问题。

**上下文隔离声明：** "每个子 Agent 在提示词中只看到自己子问题的数据。工具执行在工具对研究内容无状态的意义上是隔离的。共享基础设施（KeyPool、缓存）影响性能，不影响数据机密性或研究完整性。"

---

## 6. 状态管理

### 状态模型

```python
# -- 在所有 Agent 间共享 --

class RunContext(BaseModel):
    session_id: str
    created_at: datetime
    research_brief: ResearchBrief
    config: "RunConfig"


class RunConfig(BaseModel):
    max_parallel_agents: int = 3
    max_iterations_per_subagent: int = 3       # 为控制预算从 5 减少
    total_search_budget: int = 30
    total_llm_call_budget: int = 18            # 防止 LLM 调用爆炸
    per_subagent_timeout: int = 120            # 秒，防止挂起
    pipeline_timeout: int = 600                # 秒，流水线总超时
    pipeline_step_timeout: int = 60            # 秒，Supervisor 内每步超时
    max_rewrite_attempts: int = 2
    review_pass_threshold: int = 70
    tavily_results_per_query: int = 5
    evidence_card_min_count: int = 3
    clarifier_mode: Literal["interactive", "auto_resolve"] = "auto_resolve"
    isolation_level: Literal["strict", "relaxed"] = "strict"
    cost_per_call_estimate: float = 0.001       # 用于运行前预算预估


# -- 阶段状态 --

class TriageState(BaseModel):
    input: TriageInput
    decision: TriageDecision | None = None


class ClarifierState(BaseModel):
    result: ClarifierResult
    turns_remaining: int = 3
    mode: Literal["interactive", "auto_resolve"] = "auto_resolve"


class SupervisorState(BaseModel):
    registry: SubQuestionRegistry
    running_agents: dict[str, AgentResult] = {}
    slot_count: int
    phase: Literal["planning", "executing", "finalizing"] = "planning"
    total_llm_calls: int = 0
    # 非直接线程安全——修改方法需要外部 Lock
```

### 上下文隔离策略

| Agent               | 可看到的内容                                  | 看不到的内容                                   |
|---------------------|----------------------------------------------|-----------------------------------------------|
| Triage              | 原始查询                                     | 无（第一个）                                    |
| Clarifier           | 原始查询、flags                              | ResearchBrief、证据                            |
| Instruction Builder | 澄清后的查询或原始查询                         | 证据、报告                                     |
| Supervisor          | 仅 ResearchBrief                             | 搜索结果、证据卡片                               |
| Sub-Research Agent  | 一个 SubQuestionEntry、工具                   | 其他子问题、完整报告                             |
| Consolidator        | AgentResult[]                                | 原始用户查询、报告                               |
| Writer              | ConsolidatedEvidence + ResearchBrief         | 原始搜索结果、完整提取文本                        |
| Reviewer            | Report + ConsolidatedEvidence                | 原始搜索结果、用户查询                            |

**关于工具级别隔离的说明：** 子 Agent 共享同一个 `ToolRegistry` 实例。工具执行不是数据隔离的（所有 Agent 使用相同的 API key pool 和连接池）。然而，这只影响性能特征，不影响研究数据完整性。真正的隔离在提示词/上下文级别实现——没有子 Agent 在其 LLM 提示词中看到其他子问题的数据。

### 上下文传递方式

```python
class V3Pipeline:
    def __init__(self, llm: LLMClient, tools: ToolRegistry, config: RunConfig):
        self._llm = llm
        self._tools = tools
        self._config = config

    async def run(self, query: str) -> PipelineResult:
        # Stage 1: Triage
        triage = TriageAgent(self._llm)
        decision = triage.run(TriageInput(
            query=query,
            interactive=self._config.clarifier_mode == "interactive",
        ))

        # Stage 2: Clarify or Build
        brief = self._build_brief(decision, query)

        # 在昂贵的阶段之前进行预算检查
        projected_cost = self._project_cost(brief)
        if projected_cost > self._config.total_llm_call_budget:
            return PipelineResult(errors=[
                f"Projected cost ({projected_cost} calls) exceeds "
                f"budget ({self._config.total_llm_call_budget})"
            ])

        ctx = RunContext(
            session_id=uuid4().hex[:12],
            research_brief=brief,
            config=self._config,
        )

        # Stage 3: Supervisor + Sub-Agents
        supervisor = ResearchSupervisor(self._llm, self._tools, ctx)
        agent_results = await supervisor.run()

        # Stage 4: Consolidation + Pre-write gate
        consolidator = EvidenceConsolidator(self._llm)
        consolidated = consolidator.run(agent_results)
        if consolidated.blocked:
            return PipelineResult(errors=[
                f"Evidence consolidation blocked: "
                f"{consolidated.pre_write_warnings}"
            ])

        # Stage 5: Write + Review
        writer = WritingAgent(self._llm)
        report = writer.run(consolidated, brief)

        reviewer = MultiDimensionReviewer(self._llm)
        review = reviewer.run(report, consolidated)

        rewrite_count = 0
        while (
            not review.passed
            and rewrite_count < self._config.max_rewrite_attempts
        ):
            rewrite_count += 1
            report = writer.rewrite(consolidated, brief, review)
            review = reviewer.run(report, consolidated)

        return PipelineResult(
            report=report,
            review=review,
            evidence=consolidated,
            brief=brief,
        )
```

### 成本预估

```python
def _project_cost(self, brief: ResearchBrief) -> int:
    """在启动昂贵阶段之前预估总 LLM 调用次数。"""
    depth_map = {"quick": 8, "standard": 15, "deep": 25}
    base = depth_map.get(brief.depth_indicator, 15)
    num_sq = len(brief.seed_subquestions)
    per_sq_estimate = 3  # 每个子问题的 plan + extract + validate
    estimated = base + (num_sq * per_sq_estimate)
    return min(estimated, self._config.total_llm_call_budget)
```

---

## 7. 上下文工程策略

上下文工程是最关键的设计原则。V3 在四个层面实现它：

### 第 1 层：查询压缩（Clarifier -> ResearchBrief）

将所有对话上下文压缩到单个结构化字段中。

### 第 2 层：简报隔离（Supervisor）

Supervisor 只能看到 ResearchBrief。

### 第 3 层：子问题隔离（Sub-Research Agent）

每个子 Agent 在提示词中只能看到自己的子问题。它与其他 Agent 共享工具基础设施（KeyPool、连接池），这只影响限流而不影响数据完整性。

**可配置隔离：** 当 `isolation_level = "relaxed"` 时，子 Agent 会收到兄弟子问题的一行摘要（"其他研究人员正在覆盖：X, Y, Z"），以避免冗余搜索而不引入偏见。

### 第 4 层：证据隔离（Writer）

Writer 只能看到 ConsolidatedEvidence。

### 第 5 层：带矛盾保留的剪枝

```python
def prune_subagent_history(
    iterations: list[AgentStep],
    contradictions_accumulated: list[str],  # 跨迭代累积
) -> tuple[list[AgentStep], list[str]]:
    """仅保留最后一次迭代的完整步骤；总结更早的迭代。
    保留所有迭代中发现的矛盾。
    """
    if len(iterations) <= 1:
        return iterations, contradictions_accumulated

    last = iterations[-1]
    prior = iterations[:-1]

    for step in prior:
        contradictions_accumulated.extend(step.contradictions_found)

    summary = (
        f"(Previous {len(prior)} iterations explored "
        f"{len(set(s.query for s in prior if s.query))} queries, "
        f"visited {len(set(u for s in prior for u in s.urls))} URLs"
    )
    if contradictions_accumulated:
        summary += (
            f", found {len(contradictions_accumulated)} contradiction(s) "
            f"during earlier iterations"
        )
        for c in contradictions_accumulated[-5:]:  # 保留最后 5 个
            summary += f"\n  - {c}"

    return [
        AgentStep(iteration=0, action="summary", result_summary=summary),
        last,
    ], contradictions_accumulated
```

### 上下文隔离 vs 交叉印证张力（分析）

**张力所在：**
- 上下文隔离防止子 Agent 看到其他子问题的发现（避免偏见/交叉污染）
- 跨子问题交叉印证需要比较不同子问题的声明（需要共享语义空间）
- 这些目标存在内在张力：完美隔离使交叉印证更困难

**V3 的解决方案：**
1. **研究时：** 子 Agent 严格隔离（默认）。每个 Agent 只知道自己的子问题。
2. **整合时：** Consolidator 使用 LLM 语义相似度显式重新关联所有证据卡片，无论它们由哪个 Agent 产生。
3. **可配置隔离：** 对于交叉授粉有价值的研究（如广泛调查），设置 `isolation_level = "relaxed"` 为子 Agent 提供兄弟子问题的上下文。
4. **覆盖缺口：** Consolidator 明确识别证据不足的子问题。

**量化的权衡：** 严格隔离意味着 Consolidator 完成关联工作。这只消耗 1 次额外的 LLM 调用（整合阶段）。在 V2 的方法中（无隔离，一切在一个上下文中），关联隐式发生但上下文大得多。该权衡对 V3 有利：一次约 2K tokens 的 LLM 调用，相比于 V2 在每次 action prompt 中携带所有子问题（累积 8K+ tokens）。

---

## 8. 结构化输出定义

V3 流水线的关键 Pydantic 模型。

### 8.1 核心数据模型（从 V2 复用，未更改）

```python
# 来自 state.py -- 复用:
# - SubQuestion
# - SearchResult
# - EvidenceCard（含 corroboration_level、corroborating_sources）
# - TokenUsage、UsageInfo、ExtractedClaim、ExtractedSource
```

### 8.2 流水线模型（V3 新增或修改）

所有模型位于 `src/deepresearch/agents/react_v3/models.py`。

```python
from datetime import datetime
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator
from typing import Literal


class RunConfig(BaseModel):
    """单次 V3 流水线运行的配置。"""
    max_parallel_agents: int = 3
    max_iterations_per_subagent: int = 3
    total_search_budget: int = 30
    total_llm_call_budget: int = 18
    per_subagent_timeout: int = 120                # 秒
    pipeline_timeout: int = 600                    # 秒，10 分钟
    pipeline_step_timeout: int = 60                # 秒，Supervisor 内
    max_rewrite_attempts: int = 2
    review_pass_threshold: int = 70
    tavily_results_per_query: int = 5
    evidence_card_min_count: int = 3
    clarifier_mode: Literal["interactive", "auto_resolve"] = "auto_resolve"
    isolation_level: Literal["strict", "relaxed"] = "strict"
    cost_per_call_estimate: float = 0.001          # 美元


class RunContext(BaseModel):
    """在所有 Agent 间共享的不可变上下文。"""
    session_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=datetime.utcnow)
    research_brief: "ResearchBrief | None" = None
    config: RunConfig = Field(default_factory=RunConfig)


# -- Triage --

class TriageInput(BaseModel):
    query: str
    conversation_history: list[dict] = []
    interactive: bool = True


class TriageDecision(BaseModel):
    route: Literal["clarify", "direct_to_research"]
    clarity_flags: list[str] = []
    suggested_clarifications: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_depth: Literal["quick", "standard", "deep"] = "standard"


# -- Clarifier --

class ClarifierTurn(BaseModel):
    question: str
    options: list[str] = []
    rationale: str = ""


class ClarifierResult(BaseModel):
    clarified_query: str
    answered_questions: list[dict] = []
    auto_resolved: bool = False


# -- Instruction Builder --

class ResearchBrief(BaseModel):
    """精简后的研究任务书 -- 替代原始用户查询。
    在 LLM 生成后通过业务规则检查进行验证。
    """
    clarified_question: str
    time_range: str = "recent"
    geo_focus: str = "global"
    format_preference: Literal["report", "comparison", "analysis", "summary"] = "report"
    constraints: list[str] = []
    depth_indicator: Literal["quick", "standard", "deep"] = "standard"
    seed_subquestions: list[str] = []
    target_audience: str = "general"
    special_instructions: str = ""

    @model_validator(mode="after")
    def validate_seed_subquestions(self) -> "ResearchBrief":
        if not self.seed_subquestions:
            self.seed_subquestions = [self.clarified_question]
        return self

    @model_validator(mode="after")
    def validate_depth_consistency(self) -> "ResearchBrief":
        if self.depth_indicator == "quick" and len(self.seed_subquestions) > 3:
            self.seed_subquestions = self.seed_subquestions[:3]
        return self


# -- Supervisor --

class SubQuestionEntry(BaseModel):
    id: str
    question: str
    rationale: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    search_count: int = 0
    extracts_count: int = 0
    card_count: int = 0
    result: "AgentResult | None" = None


class SubQuestionRegistry(BaseModel):
    entries: list[SubQuestionEntry] = []

    def get_entry(self, id: str) -> SubQuestionEntry | None:
        for e in self.entries:
            if e.id == id:
                return e
        return None


class SupervisorAction(BaseModel):
    action: Literal["start_agent", "check_progress", "reassign", "finalize"]
    subquestion_ids: list[str] = []
    rationale: str = ""


# -- Sub-Research Agent --

class AgentStep(BaseModel):
    iteration: int
    action: str
    query: str = ""
    result_summary: str = ""
    urls: list[str] = []
    contradictions_found: list[str] = []


class AgentResult(BaseModel):
    subquestion_id: str
    subquestion: str
    search_results: list["SearchResult"] = []
    evidence_cards: list["EvidenceCard"] = []
    visited_urls: list[str] = []
    errors: list[str] = []
    token_usage: list["TokenUsage"] = []
    steps: list[AgentStep] = []
    saturated: bool = False
    contradictions_found: list[str] = []


# -- Evidence Consolidator --

class Contradiction(BaseModel):
    topic: str
    claim_a: str
    agent_a: str
    source_a: str
    claim_b: str
    agent_b: str
    source_b: str
    explanation: str = ""


class ConsolidatedEvidence(BaseModel):
    evidence_cards: list["EvidenceCard"] = []
    contradictions: list[Contradiction] = []
    cross_agent_corroborations: int = 0
    quality_scores: dict[str, float] = {}
    coverage_gaps: list[str] = []
    pre_write_warnings: list[str] = []
    blocked: bool = False


# -- Review --

class ReviewRubric(BaseModel):
    factual_accuracy: int = Field(ge=0, le=100)     # 事实准确性
    coverage_completeness: int = Field(ge=0, le=100) # 覆盖完整性
    reasoning_quality: int = Field(ge=0, le=100)     # 推理质量
    citation_quality: int = Field(ge=0, le=100)      # 引用质量
    clarity_structure: int = Field(ge=0, le=100)     # 清晰度/结构


class ReviewResult(BaseModel):
    rubric: ReviewRubric
    composite_score: int = Field(ge=0, le=100)
    passed: bool = False
    issues: list[str] = []
    suggestions: list[str] = []
    can_improve: bool = True


# -- Pipeline Output --

class PipelineResult(BaseModel):
    report: str = ""
    review: ReviewResult | None = None
    evidence: ConsolidatedEvidence | None = None
    brief: ResearchBrief | None = None
    session_id: str = ""
    iterations: int = 0
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    errors: list[str] = []
```

---

## 9. 对比矩阵：V2 vs V3

此矩阵已从原始草稿中修正。之前标记为 "V3 新增" 的几个功能在 V2/graph_v2 中已存在。修正后的矩阵准确反映了每个版本提供的功能。

| 维度 | V2（graph_v2 + coordinator） | V3（多 Agent 流水线） | 说明 |
|------|------------------------------|----------------------|------|
| **架构** | LangGraph StateGraph，5 个节点（plan、run_agents、coordinator、write、save） | 8 个显式 Agent（Triage、Clarifier、Builder、Supervisor、Sub-Agent×N、Consolidator、Writer、Reviewer） | 角色更明确，但核心研究流程与 graph_v2 相似 |
| **Triage / 澄清** | 无——原始查询直接进入 planner | Triage Agent + Clarifier Agent（0-3 轮或自动解决） | **真正新增**：V2 无查询分流 |
| **研究简报** | 无——原始 `question` 字符串到处传递 | ResearchBrief Pydantic 模型 + 业务规则校验 | **真正新增**：V2 无上下文压缩层 |
| **上下文工程** | 无——完整 workspace 每次迭代传递（react_v2）或子问题传递给 Agent（graph_v2） | ResearchBrief 压缩、逐 Agent 上下文隔离、子 Agent 剪枝 | V3 形式化，graph_v2 中部分存在（子问题隔离） |
| **并行研究** | graph_v2: ThreadPoolExecutor 并行子问题 Agent | 并行子 Agent + Supervisor 生命周期、预算控制、线程安全 | V2 有基础；V3 增加显式管理 |
| **交叉验证** | 每个子问题 + 通过 coordinator.py 跨子问题 | 相同逻辑，复用 V2，增加覆盖缺口分析 | V2 已有，V3 增强 |
| **矛盾检测** | 混合：Jaccard 快速过滤 + LLM 语义分类（coordinator.py） | 相同混合方法，继承自 V2 | V2 已有，V3 原样复用 |
| **报告生成** | build_writing_prompt + validate_citations + 1 次重写 | 相同代码，相同复用 | 与 V2 **无变化** |
| **报告审查** | `_critique_report()`——单次 LLM 调用，记录到 errors，不重写（react_v2.py） | 多维度评分标准（5 轴），70% 阈值，最多 2 次重写 | **真正新增**：V2 的 critic 是被动的，V3 的是可执行的 |
| **写入前验证** | 无——证据直接进入 Writer | Consolidator 中的写入前门：关键矛盾时阻断 | **真正新增**：防止浪费 Writer 调用 |
| **工具系统** | ToolRegistry 带 register/execute/describe | 相同 ToolRegistry，扩展了可选的 MCP 服务器支持 | **渐进式**：向后兼容扩展 |
| **Token 用量跟踪** | react_v2.py、graph_v2.py、subquestion_agent.py 中完整跟踪 | 相同模式，每次 LLM 调用强制执行 | V2 已有，V3 修复了原始遗漏 |
| **预算控制** | max_iterations=15 + dry_rounds=3（react_v2.py）或基于搜索（graph_v2） | total_llm_call_budget + per_subagent_timeout + pipeline_timeout + 深度分档 | **真正新增**：显式预算执行 |
| **线程安全** | 发射后不管的并行（graph_v2），无并发状态 | Supervisor registry 上的 threading.Lock，futures 超时 | V3 解决了 V2 通过设计避免的问题 |
| **Clarifier 非交互式** | 不适用（无 Clarifier） | clarifier_mode: auto_resolve 带默认值 | **真正新增**：API 兼容性必需 |
| **状态模型** | ResearchState TypedDict | RunContext + 每个阶段的模型 | V3 的类型化接口更易维护 |
| **决策日志** | DecisionLogger（JSONL） | 相同 DecisionLogger，扩展了 `agent` 字段 | 向后兼容 |
| **研究记忆** | ResearchMemory 单例 | 相同单例 | **无变化**，V2 和 V3 共享 |
| **配置** | AppConfig（dataclass） | RunConfig（Pydantic）+ 基于环境变量的 AppConfig | Schema 验证 |
| **错误处理** | 内联 try/except，dry-round 检测 | 每个 Agent 的错误边界，Supervisor 级别终止，流水线启动前预算检查 | V3 中更分层 |
| **流式输出** | 每个阶段的 Generator | 每个阶段的 Generator（相同 SSE 模式） | 相同机制 |
| **配置文件** | pyproject.toml | pyproject.toml（相同） | 无变化 |

### V3 从 V2 保留的内容（未更改）

| 组件                  | 文件                        | 状态       |
|-----------------------|-----------------------------|----------|
| LLMClient 协议         | `clients/llm.py`            | 未更改    |
| DeepSeekLLMClient     | `clients/llm.py`            | 未更改    |
| TavilySearchClient    | `clients/tavily.py`         | 未更改    |
| SubQuestion           | `state.py`                  | 复用      |
| SearchResult          | `state.py`                  | 复用      |
| EvidenceCard          | `state.py`                  | 复用      |
| ExtractedClaim        | `state.py`                  | 复用      |
| ExtractedSource       | `state.py`                  | 复用      |
| TokenUsage, UsageInfo | `state.py`                  | 复用      |
| Tool 协议              | `tools/base.py`             | 未更改    |
| ToolResult            | `tools/base.py`             | 未更改    |
| TavilySearchTool      | `tools/tavily_search.py`    | 复用      |
| WebFetchTool          | `tools/web_fetch.py`        | 复用      |
| TavilyExtractTool     | `tools/tavily_extract.py`   | 复用      |
| CompareSourcesTool    | `tools/compare_sources.py`  | 复用      |
| FactCheckTool         | `tools/fact_check.py`       | 复用      |
| build_writing_prompt  | `prompts/writing.py`        | 复用      |
| validate_citations    | `citations.py`              | 复用      |
| build_extraction_prompt| `prompts/extraction.py`    | 复用      |
| build_validation_prompt| `prompts/evidence.py`       | 复用      |
| CoordinatorResult     | `agents/coordinator.py`     | Consolidator 复用此逻辑 |
| Contradiction         | `agents/coordinator.py`     | 复用      |
| coordinate()          | `agents/coordinator.py`     | Consolidator 调用此函数 |
| DecisionLogger        | `utils/decision_log.py`     | 复用（扩展了 agent 字段） |
| ResearchMemory        | `utils/research_memory.py`  | 复用      |
| SearchCache           | `utils/search_cache.py`     | 复用      |

### V3 相比 V2 的变更

| 组件                   | V2 行为                                           | V3 行为                                                          |
|------------------------|--------------------------------------------------|------------------------------------------------------------------|
| Agent 入口点            | `ReActV2Agent.run(question)` 或 LangGraph app     | `V3Pipeline.run(query)`——编排所有 Agent                         |
| Triage                 | 无                                                | TriageAgent + ClarifierAgent（交互式或自动解决）                   |
| 指令构建                | 无（原始问题）                                     | InstructionBuilder -> ResearchBrief 带验证                        |
| Supervisor             | graph_v2: 发射后不管的 ThreadPoolExecutor          | 显式生命周期、预算监控、线程安全、超时                               |
| 写入前验证              | 无                                                | Consolidator 带写入前门                                          |
| 报告审查                | _critique_report() 记录到 errors，不重写           | MultiDimensionReviewer 带重写循环                                 |
| 预算控制                | 隐式（max_iterations / dry_rounds）               | 显式（total_llm_call_budget + 超时）                              |
| 工具系统                | 仅 ToolRegistry                                   | 扩展的 ToolRegistry + 可选 MCP 支持                               |
| Runner 集成             | build_agent() 有 6 个分支                         | 通过架构 registry 增加 +1 分支（Phase 0 前置条件）                  |

### V3 移除的内容（V2 中有）

| 功能                                        | 移除原因                                                    |
|---------------------------------------------|-------------------------------------------------------------|
| `TopicState.open_questions` / `resolved_questions` | 被 Supervisor 的子问题状态跟踪替代                           |
| `ResearchNote` dataclass                    | 被 EvidenceCard（更结构化、类型化）替代                       |
| `_auto_manage_workspace()`                  | Supervisor 用 LLM 感知处理饱和检测                           |
| `_update_question_pool()`                   | 问题池概念被 SubQuestionRegistry 替代                        |
| Agent 编排的 LangGraph 依赖                  | V3 使用内置异步编排（无 LangGraph StateGraph）               |
| 发射后不管的并行                             | V3 使用带超时和状态跟踪的托管 futures                         |

---

## 10. 实现路径

### 包结构

```
src/deepresearch/agents/react_v3/
+-- __init__.py
+-- models.py              # 所有 V3 Agent 的 Pydantic 模型
+-- triage.py              # TriageAgent
+-- clarifier.py           # ClarifierAgent（交互式 + auto_resolve）
+-- instruction_builder.py # InstructionBuilderAgent（带验证）
+-- supervisor.py          # ResearchSupervisor（线程安全、预算感知）
+-- sub_agent.py           # SubResearchAgent（带 TokenUsage 跟踪）
+-- consolidator.py        # EvidenceConsolidator（带写入前门）
+-- writer.py              # WritingAgent（封装 V2 的 build_writing_prompt）
+-- reviewer.py            # MultiDimensionReviewer
+-- pipeline.py            # V3Pipeline 编排器
+-- mcp_tool.py            # MCPToolAdapter（Phase 5，可选）
```

### 阶段计划

#### Phase 0: 前置条件——重构 build_agent()（第 0 周）

- [ ] 将 `runner.py` 的 `build_agent()` 从 243 行的单函数分支重构为策略/插件模式
- [ ] 每个架构实现 `ResearchArchitecture` 协议，具有 `build(config) -> Callable`
- [ ] 通过 `ARCHITECTURE_REGISTRY: dict[str, type[ResearchArchitecture]]` 注册架构
- [ ] V2 和 V3 使用相同的 registry——无特殊分支
- [ ] 编写 registry 测试（test_architecture_registry.py）
- [ ] **关键依赖**：无此重构则不能合并任何 V3 代码

```python
# runner.py 的新模式

class ResearchArchitecture(Protocol):
    """每个架构实现此协议。"""
    name: str

    def build(self, llm, search, config, **kwargs) -> Callable[[str], ResearchState]:
        ...

# Registry
ARCHITECTURE_REGISTRY: dict[str, type[ResearchArchitecture]] = {}

def register(cls):
    ARCHITECTURE_REGISTRY[cls.name] = cls
    return cls

@register
class PipelineArchitecture(ResearchArchitecture):
    name = "pipeline"
    def build(self, llm, search, config, **kwargs) -> Callable:
        ...

@register
class ReactV2Architecture(ResearchArchitecture):
    name = "react-v2"
    def build(self, llm, search, config, **kwargs) -> Callable:
        ...

@register
class ReactV3Architecture(ResearchArchitecture):
    name = "react-v3"
    def build(self, llm, search, config, **kwargs) -> Callable:
        ...

def build_agent(*, architecture="pipeline", **kwargs):
    cls = ARCHITECTURE_REGISTRY.get(architecture)
    if cls is None:
        raise ValueError(
            f"Unknown architecture: {architecture}. "
            f"Available: {list(ARCHITECTURE_REGISTRY)}"
        )
    return cls().build(**kwargs)
```

#### Phase 1: 基础设施（第 1 周）

- [ ] 创建 `agents/react_v3/` 包，包含 `models.py`
- [ ] 实现 `RunConfig`、`RunContext`、所有 Pydantic 模型（包含 ResearchBrief 验证）
- [ ] 在 `tools/registry.py` 中为 `ToolRegistry` 添加 MCP 支持（向后兼容）
- [ ] 实现成本预估：`_project_cost()` 用于流水线启动前预算检查
- [ ] 在架构 registry 中注册 `"react-v3"`（Phase 0 前置条件）
- [ ] 编写所有模型的单元测试（test_react_v3_models.py）

#### Phase 2: 核心 Agent（第 2 周）

- [ ] 实现 `TriageAgent`（带 interactive 标志）+ 测试
- [ ] 实现 `InstructionBuilderAgent`（带 ResearchBrief 验证 + 重试）+ 测试
- [ ] 实现 `SubResearchAgent`（继承 V2 的 search-extract-validate，增加迭代循环、饱和检测、TokenUsage 跟踪、矛盾保留）+ 测试

#### Phase 3: 协调（第 3 周）

- [ ] 实现 `ResearchSupervisor`（线程安全、预算感知、超时感知）+ 测试
- [ ] 实现 `EvidenceConsolidator`（复用 V2 的 coordinator.py 逻辑，增加写入前门）+ 测试
- [ ] 实现 `WritingAgent`（封装 `build_writing_prompt` + `validate_citations`，增加写入前警告感知）+ 测试
- [ ] 实现 `MultiDimensionReviewer`（带重写循环、综合评分）+ 测试

#### Phase 4: 流水线 + 集成（第 4 周）

- [ ] 实现 `V3Pipeline` 编排器（带预算预估、写入前门、错误边界）
- [ ] 实现 `ClarifierAgent`（交互式 CLI + auto-resolve 模式）
- [ ] 为流水线添加流式 SSE 事件
- [ ] 使用 Fake LLM/Search 客户端编写集成测试
- [ ] 通过架构 registry 集成 CLI

#### Phase 5: 生产就绪（第 5 周）

- [ ] 使用真实 DeepSeek + Tavily 进行在线测试
- [ ] 在相同查询上与 V2 进行基准测试（质量 + 成本 + 端到端耗时）
- [ ] DecisionLogger 集成（添加 `agent` 字段）
- [ ] ResearchMemory 集成（Supervisor 读取，不写入）
- [ ] 文档更新
- [ ] MCPToolAdapter（如果有可用 MCP 服务器——可选，从 Phase 1 推迟）

### 迁移策略

1. **共存：** V2 和 V3 作为策略 registry 中的两个架构并行运行。用户通过 `--architecture react-v2`（默认）或 `--architecture react-v3` 选择。

2. **共享核心：** 两种模式共享相同的工具、客户端、状态类型、提示词、验证代码、coordinator 逻辑和子问题 Agent 代码。V3 只增加代码，从不修改 V2 的代码。

3. **逐步默认切换：** Phase 5 基准测试确认 V3 质量 >= V2 且成本相当或更优后，CLI 默认切换为 `react-v3`。

4. **V2 废弃：** V3 稳定生产使用 2 个月后，标记 V2 为已废弃。保留代码 6 个月以备回滚。

### 风险缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 并行子 Agent 超出 API 速率限制 | 高 | 使用 TavilyKeyPool（已存在）；可配置的 `max_parallel_agents`；带头退重试 |
| LLM 调用成本高于 V2 | 中高 | 流水线启动前预算门；带强制调用限制的分档深度模式；监控每次调用 token 数；预估成本超过预算时中止 |
| 上下文隔离丢失跨子问题的意外发现 | 中 | Consolidator 显式重新关联；`isolation_level = "relaxed"` 选项；coverage_gaps 标记 |
| Clarifier Agent 在 API 模式下阻塞 | 严重（已修复） | `clarifier_mode: "auto_resolve"` 提供非交互式回退和合理默认值 |
| Supervisor 竞态条件 | 严重（已修复） | 所有 registry 修改使用 `threading.Lock`；futures 超时 |
| 子 Agent 挂起/停滞 | 中 | `per_subagent_timeout`（120s）；`pipeline_step_timeout`（60s）；超时时释放槽位 |
| build_agent() 可维护性 | 中 | **Phase 0 前置条件**：在添加 V3 代码前重构为策略/插件模式 |
| ResearchBrief 验证失败 | 中 | 1 次 LLM 重试 + 错误反馈；第二次也失败时回退到安全默认值 |
| MCP 工具适配器未使用的复杂性 | 低 | **推迟到 Phase 5**：Phase 1-4 中无 MCP 代码；现有 ToolRegistry 处理一切 |
| 写入前门阻断有效研究 | 低 | 仅在关键矛盾时阻断；警告会透传；Writer 仍可生成附有注意事项的输出 |

---

## 附录 A：关键提示词设计原则

```
+-----------------------------------------------------------+
|                提示词设计原则                                |
+-----------------------------------------------------------+
| 1. 每个 Agent 提示词仅包含其需要的上下文                     |
| 2. 每个提示词以 "Return JSON ONLY:" 结尾                   |
| 3. JSON Schema 包含在提示词中                               |
| 4. 示例内联展示复杂结构                                     |
| 5. 指令使用要点式祈使句格式                                  |
| 6. 无对话历史——所有上下文是结构化的                           |
| 7. 输出格式用 Pydantic 验证                                  |
| 8. 解析失败时强制重试（最多 2 次），附带错误信息               |
| 9. ResearchBrief 验证错误在重试时传回 LLM 以供自我修正        |
+-----------------------------------------------------------+
```

## 附录 B：流式事件协议

```
V3Pipeline SSE 事件:

{"type": "phase",     "data": {"phase": "triage",         "message": "Analyzing query..."}}
{"type": "phase",     "data": {"phase": "clarify",        "message": "Need more details..."}}
{"type": "clarify",   "data": {"question": "...", "options": ["...", "..."], "round": 1, "mode": "interactive|auto_resolve"}}
{"type": "phase",     "data": {"phase": "build",          "message": "Building research brief..."}}
{"type": "budget",    "data": {"projected_calls": 12, "budget": 18, "proceed": true}}
{"type": "phase",     "data": {"phase": "research",       "message": "Researching 3 topics..."}}
{"type": "sub_start", "data": {"subquestion_id": "q1", "question": "..."}}
{"type": "sub_search","data": {"subquestion_id": "q1", "query": "..."}}
{"type": "sub_card",  "data": {"subquestion_id": "q1", "count": 5}}
{"type": "sub_done",  "data": {"subquestion_id": "q1", "cards": 7, "urls": 12, "calls": 4}}
{"type": "sub_timeout","data": {"subquestion_id": "q4", "timeout": 120}}
{"type": "phase",     "data": {"phase": "consolidate",    "message": "Cross-validating evidence..."}}
{"type": "gate",      "data": {"blocked": false, "warnings": ["1 contradiction detected"], "gaps": []}}
{"type": "phase",     "data": {"phase": "writing",        "message": "Writing report..."}}
{"type": "token",     "data": {"text": "..."}}              # 流式报告 token
{"type": "phase",     "data": {"phase": "review",         "message": "Reviewing report..."}}
{"type": "review",    "data": {"rubric": {...}, "composite": 85, "passed": true}}
{"type": "done",      "data": {"iterations": 15, "total_llm_calls": 14, "total_tokens": 45000, "total_cost": 0.18}}
```

## 附录 C：与 LangChain OpenDeepResearch 的对比

| 维度 | LangChain OpenDeepResearch | React V3 |
|------|---------------------------|-----------|
| **架构** | 并行 Supervisor + 子研究 Agent | 8 个显式 Agent，带类型化接口 |
| **子问题分解** | LLM 生成子问题，Supervisor 分配 | ResearchBrief 提供 seed_subquestions，LLM 扩展 |
| **并行执行** | 基于 asyncio 的事件循环 | ThreadPoolExecutor + 线程安全 Supervisor |
| **证据整合** | 未明确记录为单独阶段 | 正式的 Consolidator，带覆盖缺口、质量评分、写入前门 |
| **报告审查** | 未公开记录 | 5 维度评分标准 + 重写循环 + 综合评分 |
| **Triage/澄清** | 无（假定查询清晰） | TriageAgent + ClarifierAgent，带非交互式回退 |
| **上下文工程** | 研究时的子问题隔离 | 四层隔离（查询压缩、简报隔离、子问题隔离、证据隔离） |
| **剪枝** | 未记录 | 子 Agent 历史剪枝，保留矛盾 |
| **预算控制** | 公开材料中未记录 | total_llm_call_budget、per_subagent_timeout、pipeline_timeout、运行前成本预估 |
| **线程安全** | asyncio 避免共享状态问题 | threading.Lock 处理并发状态修改 |
| **MCP 集成** | 原生 LangChain 工具系统 | 扩展的 ToolRegistry + 推迟的 MCP 适配器 |
| **非交互式模式** | 设计上兼容 API | 显式的 clarifier_mode: auto_resolve |
| **写入前验证** | 未记录 | 写入前门：关键矛盾时阻断 |

**V3 相比 OpenDeepResearch 的差异化优势：**
1. 带重写循环的多维度审查（OpenDeepResearch 未公开记录报告质量门）
2. 写入前验证门，防止在矛盾证据上浪费生成
3. 面向 API/无头操作的非交互式回退
4. 带运行前预估的显式成本预算
5. 作为上下文压缩层的业务规则验证 ResearchBrief

---

## 11. 修订日志

| 日期       | 作者              | 变更                          | 参考              |
|------------|-------------------|------------------------------|-------------------|
| 2026-06-18 | V3 设计团队        | 初始草稿                      | --                |
| 2026-06-18 | V3 设计团队        | 修订版 1（Griller 审查）      | 解决了 15 个问题   |

### 问题回应（Griller 审查 v1）

| #  | 问题                                                       | 严重性  | 裁决             | 变更摘要                                                        |
|----|------------------------------------------------------------|--------|-----------------|----------------------------------------------------------------|
| 1  | SubResearchAgent 缺少 TokenUsage 跟踪                       | 严重   | 接受并修改        | 在子 Agent 的每次 LLM 调用中添加 TokenUsage 跟踪               |
| 2  | Clarifier 无非交互式回退                                    | 严重   | 接受并修改        | 在 RunConfig 中添加 `clarifier_mode`；带默认值的自动解决       |
| 3  | 缺少 LLM 调用预算和流水线超时                                 | 重要   | 接受并修改        | 在 RunConfig 中添加 `total_llm_call_budget` 和超时             |
| 4  | Supervisor 并发状态更新竞态条件                               | 严重   | 接受并修改        | 在 Supervisor 中添加 `threading.Lock`                          |
| 5  | 跨 Agent 工具共享破坏上下文隔离                                | 严重   | 接受并修改        | 记录共享状态路径；添加 `isolation_level` 配置                  |
| 6  | 子 Agent 历史剪枝丢失矛盾                                     | 重要   | 接受并修改        | `prune_subagent_history()` 现在保留矛盾                        |
| 7  | build_agent() 函数膨胀                                       | 严重   | 接受并修改        | 添加 Phase 0 前置条件：策略/插件重构                            |
| 8  | 12-40 次 LLM 调用经济上不可持续                               | 严重   | 接受并修改        | 修订预估为 8-28；添加预算执行；成本计算                         |
| 9  | MCPToolRegistry 与现有 ToolRegistry 不兼容                    | 重要   | 接受并推迟        | 扩展现有 ToolRegistry；MCP 推迟到 Phase 5                      |
| 10 | 多个 "V3 新增" 功能在 V2 中已存在                              | 严重   | 接受并修改        | 修正对比矩阵（第 9 节）中的所有声明                             |
| 11 | 上下文隔离 vs Consolidator 意外发现的张力                     | 重要   | 接受并修改        | 添加张力分析（第 7 节）；可配置隔离                             |
| 12 | 无 OpenDeepResearch 对比                                     | 轻微   | 接受并添加        | 添加附录 C                                                     |
| 13 | ResearchBrief 验证缺失                                       | 严重   | 接受并修改        | 添加业务规则校验器，失败时重试                                  |
| 14 | 子 Agent 无死锁/超时检测                                     | 重要   | 接受并修改        | 添加 `concurrent.futures.timeout`；超时时释放槽位              |
| 15 | Writer 写入前无事实检查                                      | 重要   | 接受并修改        | 在 Consolidator 中添加写入前验证门                             |

**总结：** 15 个问题中，13 个接受并修改，1 个推迟（MCPToolAdapter 到 Phase 5），1 个接受并添加（OpenDeepResearch 对比）。无拒绝的问题。

---

## 文档元数据

| 属性       | 值                                           |
|------------|----------------------------------------------|
| 版本       | v1.0                                         |
| 状态       | 最终版——通过 1 轮设计审查                        |
| 文件名     | `docs/architecture-v3.md`                    |
| 作者       | React V3 架构团队                             |
| 审查方     | Griller review v1（15 个问题，全部解决）       |
| 最后更新   | 2026-06-18                                   |
| 取代       | 初始草稿（pre-griller）                       |
| 下次审查   | Phase 2 实现后（第 2 周）                      |
