# ReAct Agent 详细设计

> **来源**：从 [ARCHITECTURE.md](../../ARCHITECTURE.md) §13 迁出的 Agent 智能体层完整设计文档。

---

Agent 层包含两个子模块：**ReAct 推理-行动循环**（`agent/react/`）和**工具系统**（`agent/tools/`）。

## 1. ReAct Agent 核心

| 组件 | 文件 | 职责 |
|---|---|---|
| **ReActAgent** | `agent/react/agent.py` | 推理-行动循环核心（run / run_stream）|
| **AgentEvent** | `agent/react/agent.py` | 流式事件数据类（thought/action/observation/answer）|
| **AgentResult** | `agent/react/agent.py` | 完整执行结果封装 |
| **ReActParser** | `agent/react/parser.py` | LLM 输出解析器（Thought/Action/Answer 格式）|
| **StreamingReActParser** | `agent/react/parser.py` | 流式逐 token 解析器 |
| **prompts** | `agent/react/prompts.py` | ReAct system prompt 模板（通用/深度研究/简报） |

### Agent 工作模式

| 模式 | Prompt 构建函数 | max_steps | 用途 |
|---|---|---|---|
| 通用模式 | `build_react_system_prompt` | 5 | 自动意图识别，快速问答 vs 深度研究切换 |
| 深度研究模式 | `build_deep_research_prompt` | 15 | 专用研究流程引导，多步信息收集 |
| Plan Execute 深度研究 | `build_research_plan_prompt` + `build_plan_execute_research_prompt` | 15 | 先生成可审阅 plan/todos，用户确认后执行 |
| 简报生成模式 | `build_briefing_agent_prompt` | — | 简报生成引导 |

### ReAct 循环流程

```
1. 构建 system prompt（含所有可用工具描述）
2. messages = [system_prompt, user_question]
3. while steps < max_steps:
   4. llm_output = LLM.generate_with_history(messages)
   5. parsed_steps = ReActParser.parse(llm_output)
   6. for step in parsed_steps:
      a. LLM token → yield AgentEvent("llm_delta")
      b. Thought   → yield AgentEvent("thought")
      c. Action    → yield AgentEvent("action_start") → 执行工具 → yield AgentEvent("action_result")
                     Observation 追加到 messages 历史
      d. Answer    → yield AgentEvent("answer_delta") + AgentEvent("answer") → 结束
7. 达到 max_steps → 强制要求 LLM 基于已有 Observation 给出回答
```

### SSE 事件格式

```json
data: {"event_type": "llm_delta", "content": "Thought:", "run_id": "...", "sequence": 1}
data: {"event_type": "thought", "content": "用户想了解AI新闻，需要搜索...", "step_index": 1}
data: {"event_type": "action_start", "tool_name": "search_evidence", "tool_input": {"query": "AI"}}
data: {"event_type": "action_result", "content": "找到 5 条相关文章...", "tool_result": {"success": true}}
data: {"event_type": "answer_delta", "content": "根据搜索结果，"}
data: {"event_type": "answer", "content": "根据搜索结果，最近的AI新闻..."}
data: [DONE]
```

每个事件会包含 `run_id`、`sequence`、`timestamp` 等审计字段；工具参数和结果会在日志中保留更完整版本，但会对 API Key、Token、Webhook URL 等敏感字段脱敏，并对超长文本截断。

### Plan Execute 深度研究流程

```
1. 用户提交研究主题
2. PlanExecuteRunner.generate_plan()
   → LLM 生成结构化 PLAN + todo list
   → agent_sessions 写入 planned 会话
3. 前端展示 PLAN 和可编辑 todo list
4. 用户确认后保存最终 PLAN/todos
5. PlanExecuteRunner.execute()
   → 状态切换 approved → running
   → 将 PLAN/todos 注入 ReAct system prompt
   → ReActAgent 按计划调用工具并流式返回事件
   → todo_update 事件同步 todo 进度
6. 最终 Answer 写入 output/research，并将完整会话 flush 到 PostgreSQL
```

执行期会话优先写入 Redis 键 `logos:agent_session:{session_id}`；终态或 Redis 不可用时写入 PostgreSQL `agent_sessions`。旧 `/api/research/stream` 保留兼容，前端默认使用 Plan Execute 两阶段接口。

---

## 2. 工具系统核心组件

| 组件 | 文件 | 职责 |
|---|---|---|
| **BaseTool** | `agent/tools/base.py` | 工具抽象基类（模板方法模式）|
| **ToolParameter** | `agent/tools/base.py` | 参数定义，生成 JSON Schema |
| **ToolResult** | `agent/tools/base.py` | 执行结果标准封装 |
| **ToolRegistry** | `agent/tools/registry.py` | 线程安全单例注册中心 |
| **@register_tool** | `agent/tools/registry.py` | 类装饰器，自动注册工具 |
| **ToolChain** | `agent/tools/chain.py` | 多工具有序编排 |
| **AsyncToolExecutor** | `agent/tools/executor.py` | 异步执行器（ThreadPool 包装）|

## 3. 内置工具

| 工具名 | 描述 | 依赖层 |
|---|---|---|
| `search_evidence` | 带过滤下推的原文 evidence RAG 检索 | EvidenceSearchService / HybridSearchService |
| `query_intel_facts` | 按竞品、产品、类型、维度、日期和状态查询结构化 facts | IntelService |
| `get_intel_fact` | 获取单条 fact 详情和 evidence refs | IntelService |
| `create_intel_fact` / `update_intel_fact` | 创建或修改 draft/rejected/archived fact | IntelService |
| `link_fact_to_competitor` / `link_fact_to_product` | 维护 fact 级竞品/产品归因 | IntelService |
| `create_insight_claim` / `query_insight_claims` | 创建 draft claim、查询 claims | InsightService |
| `web_search` | 多引擎并发搜索 (DuckDuckGo+Tavily+NewsAPI) | WebSearchService |
| `list_competitors` | 列出竞品 | CompetitorService |
| `get_competitor_profile` | 获取竞品档案、产品线和 fact 聚合 | CompetitorService |
| `compare_competitors` | 基于 facts/events 多竞品横向对比 | CompetitorService |
| `generate_analysis_report` | 基于 fact/evidence/claim 上下文生成报告 | ReportService |

内置工具通过 `ToolSpec` 定义注册表声明，由 `BuiltinToolFactory` 从 `ServiceRegistry` 解析 service 级依赖后创建。运行时 active 工具固定为上表 14 个；旧 news/article/brief 工具定义已删除，不再保留 removed placeholder，也不会进入 `ToolRegistry`。

> 上表描述当前工具。按 ADR-0002，后续工具契约必须移除 `dimension` 和三层业务 score，把搜索结果视为 Evidence Candidate，并让 claim 只通过 facts 间接溯源；具体迁移目标见 [structured-intelligence-model.md](structured-intelligence-model.md)。

## 4. 工具执行流程

```
ReActAgent 决策 → Action: tool_name
    → ToolRegistry.get(tool_name)
    → BaseTool.execute(**params)
        ├── validate_params()    参数校验
        ├── _run(**validated)    子类逻辑
        └── → ToolResult         结果封装
    → 结果文本追加到消息历史作为 Observation
```

## 5. 工具链编排

`ToolChain` 支持多步工具有序执行，`$prev` 占位符实现管道传参：

```python
chain = ToolChain("证据分析链")
chain.add_step("search_evidence", params={"query": "AI 新闻"})
chain.add_step("query_intel_facts", params={"competitor_ids": [1]})
result = chain.run()
```

## 6. 异步执行器

`AsyncToolExecutor` 基于 `asyncio` + `ThreadPoolExecutor`：

```python
executor = AsyncToolExecutor(max_workers=4, default_timeout=60)
result = await executor.execute("search_evidence", query="AI")
results = await executor.execute_batch([ToolCall(...), ...])
```
