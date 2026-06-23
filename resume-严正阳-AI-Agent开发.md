# 严正阳

**求职意向：AI Agent 开发工程师**

📧 zhengyang1013@126.com ｜ 📱 17393373476 ｜ 🔗 [github.com/suuny-ab](https://github.com/suuny-ab)

---

## 项目经历

### Deep Research Agent — 多架构 AI 深度研究系统

*独立开发 ｜ Python · LangGraph · DeepSeek · Tavily · Pydantic · FastAPI · LangSmith*

一个自动分解研究问题、检索网络信息、交叉验证证据并生成引用报告的多模式 AI Agent 系统。

**多架构 Agent 设计**：实现了三种差异化的执行模式——Pipeline（确定性 5 节点工作流）、Multi-Agent（子问题级并行 Agent + Coordinator 合并与跨 Agent 印证）、以及 ReAct V2（带反思循环和结构化记忆的自主 Agent）。三种模式共享同一套状态模型和提示词体系，可在不同场景按需切换。

**ReAct V2 — 反思增强的自主 Agent**：在基础 ReAct 循环之上设计了三阶段架构。阶段零生成多主题研究计划（ResearchPlan）；研究循环中每 N 轮触发一次反思步骤（Reflection），由 LLM 评估当前进展、识别信息缺口、动态调整计划主题状态；阶段二将结构化笔记（ResearchNote）转化为证据卡片并生成引用合规报告。反思机制将"盲目搜索直到饱和"升级为"有策略地填补知识缺口"。

**两阶段证据流水线**：将事实提取与交叉验证拆分为两个独立阶段，解决单次 LLM 调用同时承担"发散提取"和"收敛验证"导致的保守输出问题。阶段一从多来源一次性提取声明，阶段二按子问题并行交叉验证不同域名来源的独立印证。后验证阶段用代码层面的域名多样性和 URL 有效性检查覆盖 LLM 输出的不可靠性。

**引用合规系统**：针对 LLM 编造 URL 的幻觉问题，设计 7 维度 `[N]` 引用校验器（缺失来源章节 / 裸 URL / 重复编号 / 未定义引用 / 非法 URL / 未使用来源 / 重复来源），失败时自动构造诊断信息并触发一次重写。

**工程化实践**：218 个离线单元测试、Protocol 级依赖注入、Pydantic 模型守卫自动过滤不合法 JSON、按流水线阶段追踪 Token 成本。LLM 调用层内置指数退避重试（tenacity），搜索层集成 TTL 持久化缓存减少重复 API 消耗。

**生产级能力**：基于 FastAPI + SSE 实现了流式研究服务，Agent 的 Plan / Search / Reflect / Synthesize 各阶段以事件流实时推送。支持 `--consistency N` 多跑综合共识模式（Self-Consistency 论文思路）。跨运行持久化研究记忆（ResearchMemory），后续研究自动注入历史上下文。

---

## 工作经历

### AskTable（察言观数）· 后端开发

*2024.07 – 2025.01 ｜ Python · FastAPI · PostgreSQL · Redis · Qdrant*

AskTable 是一个企业级 AI 原生数据智能平台，用户通过自然语言与数据库交互，由 LLM 驱动的 Agent 完成 SQL 生成、数据分析与可视化。

- 在真实企业级 Agent 系统中理解了 LLM 应用的核心技术栈：多供应商 LLM SDK（DeepSeek / GPT / Claude / Qwen）、工具调用协议、NL2SQL 的 Schema Linking + RAG 增强、对话 Agent 的状态管理与 SSE 流式推送
- 接触了生产环境中的工程问题：Agent 取消机制、并发控制、错误追踪（Sentry + Langfuse）、API 密钥安全
- 熟悉了专业团队的工程规范：App Factory 模式下模块化架构设计、CI/CD 流水线、完整的测试与评估体系

---

## 技能清单

- **Agent 框架**：LangGraph（StateGraph 构建、多节点编排、条件路由、并行执行）
- **LLM 集成**：OpenAI SDK / DeepSeek API、Prompt Engineering、工具调用 / 函数调用
- **后端开发**：Python ≥3.11、FastAPI、PostgreSQL、Redis、Pydantic
- **搜索与检索**：Tavily API、向量检索基础（Qdrant）
- **工程化**：pytest（离线测试设计）、Git、Docker、LangSmith 链路追踪
- **语言**：中文（母语）、英文（技术文档阅读与写作）

---

## 教育背景

**东南大学** · 人工智能 · 本科 · 2025 年毕业
