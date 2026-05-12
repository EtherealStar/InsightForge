# 三层记忆系统架构设计与执行计划

## 已确认决策

1. 记忆系统服务于 Agent 的两个功能：普通问答和深度研究。
2. 持久记忆采用“建议写入，用户确认”机制；自动提取只能生成 pending 候选。
3. MEMORY 索引以数据库为准，文档形式仅作为导出视图。
4. 会话记忆覆盖普通问答；原 Plan Execute `agent_sessions` 已扩展为通用 Agent session，不另建重复会话表。

## 三层记忆

| 层级 | 范围 | 持久性 | 权威存储 | 当前实现 |
|---|---|---|---|---|
| 会话记忆 | 当前普通问答或深度研究 session | Redis 热缓存，终态/降级写 PostgreSQL | `agent_sessions` | 已扩展 `summary/token_count/compact_failures` 等字段 |
| 持久记忆 | 跨对话 | 永久，允许用户删除 | `persistent_memories` | 已实现 pending/active/deleted 状态和 MEMORY 索引生成 |
| 核心记忆 | 全局 Agent 工作规则 | 永久，不物理删除，只能新建 revision | `core_memory_revisions` | 已实现 active revision 查询与新版本创建 |

## 当前代码落点

| 模块 | 文件 | 说明 |
|---|---|---|
| 数据模型 | `models/memory.py` | `CoreMemoryRevision`、`PersistentMemory`、`MemoryIndexItem` |
| 通用会话模型 | `models/agent_session.py` | `SessionStatus.ACTIVE`，新增会话摘要与 token 统计字段 |
| 存储实现 | `infrastructure/memory_store.py` | PostgreSQL 权威记忆存储 |
| 会话存储 | `infrastructure/agent_session_store.py` | 原深度研究 session 扩展为通用 Agent session |
| 服务层 | `services/memory_service.py` | 构建 memory context、触发会话摘要、创建持久记忆候选 |
| 普通问答接入 | `services/query_service.py`、`delivery/api/query_router.py` | 自动创建/续用通用 session，返回 `session_id` |
| 深度研究接入 | `agent/react/plan_execute_runner.py` | 执行 prompt 注入 memory context |
| API | `delivery/api/memory_router.py` | 核心记忆、MEMORY 索引、持久记忆管理 |

## 会话记忆策略

- 首次触发阈值：估算上下文达到 10k tokens。
- 后续更新阈值：上次成功摘要后每增长 5k tokens。
- 连续 3 次摘要失败后：改为每增长 10k tokens 再尝试。
- 摘要成功后：失败计数归零，恢复 5k tokens 更新。
- 当前实现使用轻量 token 估算，避免绑定具体 tokenizer。
- IndexedDB 后续只做前端草稿/离线缓存；后端事实来源是 Redis/PostgreSQL。

## 持久记忆策略

类型：

- `user`：用户身份、目标、知识背景。
- `feedback`：用户纠正、确认和工作方式偏好。
- `project`：用户长期追踪的主题和事件进展。

状态：

- `pending`：候选记忆，等待用户确认。
- `active`：已确认，进入 MEMORY 索引。
- `archived`：保留但默认不注入。
- `deleted`：逻辑删除。

MEMORY 索引格式由数据库 active 记忆生成：

```text
- [feedback-concise] - 回复保持简洁
```

## Agent 注入顺序

Agent system prompt 组合顺序：

1. 核心记忆
2. MEMORY 索引
3. 相关持久记忆
4. 会话记忆摘要
5. 原 ReAct/Plan Execute prompt 与工具说明

## 已完成

- [x] 扩展 `agent_sessions` 为通用 Agent session。
- [x] 新增三层记忆数据模型和 Protocol。
- [x] 新增 PostgreSQL `MemoryStore`。
- [x] 新增 `MemoryService`。
- [x] 普通问答自动创建/续用 session，API 返回 `session_id`。
- [x] 深度研究执行阶段注入 memory context。
- [x] 新增 Memory API。
- [x] 增加单元测试并通过相关测试。

## 后续工作

- [ ] 前端 Memory 管理页：pending 确认、active 列表、核心记忆 revision 查看。
- [ ] 自动提取持久记忆候选：会话结束后从用户反馈中生成 pending 记忆。
- [ ] 将 `session_memory_template.md` 和 `full_compact_template.md` 初始化进核心记忆表。
- [ ] 普通问答前端持久保存并复用 `session_id`。
- [ ] IndexedDB 草稿缓存与后端 session 同步。
- [ ] 使用真实 tokenizer 替换轻量估算，或在配置中按模型选择 tokenizer。
- [ ] 全量压缩：当上下文达到模型最大窗口 80% 时触发 `full_compact_template.md`。

## 验证

```bash
python -m pytest tests/test_query_service.py tests/test_query_router.py tests/test_plan_execute_runner.py tests/test_memory_service.py -q
python -m compileall models/agent_session.py models/memory.py infrastructure/agent_session_store.py infrastructure/memory_store.py services/memory_service.py services/query_service.py agent/react/plan_execute_runner.py delivery/api/query_router.py delivery/api/memory_router.py core/protocols.py core/factory.py core/config_manager.py
```

当前验证结果：相关测试 11 passed，编译检查通过。
