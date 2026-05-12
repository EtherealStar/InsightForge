# 数据库业务规则补充说明

> **表结构文档**由 [tbls](https://github.com/k1LoW/tbls) 自动生成 → [dbdoc/](dbdoc/)
> 本文件仅保留 tbls 无法覆盖的业务规则说明。

---

## ArticleStatus 生命周期

```
stored → pending_summary → summarized → embedded
```

- `stored`：新入库，等待摘要（无摘要服务时直接跳到 `summarized`）
- `pending_summary`：已标记待摘要
- `summarized`：摘要完成，等待向量化
- `embedded`：向量化完成，可被检索

---

## 核心实体关系

```
Article (1) ──→ (N) ParentChunk (父分块, PostgreSQL)
Article (1) ──→ (N) Chunk (子分块, PostgreSQL/pgvector)
Chunk (N)   ──→ (1) ParentChunk (通过 parent_chunk_id)

AgentSession (1) ──→ (1) Plan Execute 深度研究会话
```

外键约束已配置 `ON DELETE CASCADE`：删除文章时自动级联删除关联的父子 chunks。

---

## 分块策略

| 参数 | 默认值 | 说明 |
|---|---|---|
| `chunk_max_child_tokens` | 512 | 子 chunk 最大 token 数 |
| `chunk_target_parent_tokens` | 1024 | 父 chunk 目标 token 数 |
| `chunk_overlap_tokens` | 100 | 父 chunk 间重叠 token 数 |
| `embedding_vector_size` | 1536 | pgvector 向量维度 |

**关键规则**：
- 子 chunk 按 Markdown 标题结构切分，≤512 token，存入 PostgreSQL `child_chunks` 用于 pgvector 检索
- 父 chunk ~1024 token，完整包含若干子 chunk，存入 PostgreSQL 用于 LLM 召回
- 父 chunk 之间通过共享尾部子 chunk 实现 ~100 token overlap
- 子 chunk 明确归属一个父 chunk（通过 `parent_chunk_id`）
- 短文档 (≤1024 token) 同时视为子 chunk 和父 chunk
- 全文索引：父 chunk 写入时自动使用 `jieba` 分词生成 `search_vector`
- `backfill_search_vectors()` 支持为已有数据回填全文索引

### 存储示意

```
文章 → ChunkingService
         ├── 子 chunks (≤512 tok) ──→ Embedding ──→ PostgreSQL child_chunks
         │                                          embedding + parent_chunk_id
         └── 父 chunks (~1024 tok) ──→ PostgreSQL (parent_chunks)
                                      含 search_vector (jieba tsvector)
```

---

## AgentSession Plan Execute 会话

`agent_sessions` 保存 Plan Execute 深度研究的完整会话状态：用户主题、AI 生成的 PLAN、用户确认后的 todo list、执行事件、最终报告正文和报告文件名。

### 状态流转

```
planned → approved → running → completed
                     └──────→ failed
planned ────────────→ cancelled
```

- `planned`：AI 已生成研究计划，等待用户审阅或编辑 todo
- `approved`：用户已确认计划和 todo，准备执行
- `running`：ReAct Agent 正在按确认后的计划执行
- `completed`：执行完成，`final_answer` 有最终报告正文，`report_filename` 指向 `output/research` 中的 Markdown 文件
- `failed`：执行失败，`error` 记录失败原因
- `cancelled`：用户取消执行

### 缓存与持久化

- 执行期 Redis 缓存键为 `logos:agent_session:{session_id}`，保存完整会话 JSON。
- 计划生成、用户保存计划、状态切换会立即 upsert PostgreSQL。
- 执行中 `events` 和 `todos` 优先更新 Redis；Redis 不可用时直接写 PostgreSQL。
- `completed/failed/cancelled` 终态会将 Redis 中的完整会话 flush 到 PostgreSQL。

### JSONB 字段语义

- `messages`：OpenAI message 格式数组，用于审计计划生成上下文。
- `plan`：结构化研究计划；如果模型返回非 JSON，则保存为 `{"raw": "..."}`。
- `todos`：用户最终确认的执行列表，元素包含 `id/title/status`。
- `events`：`AgentEvent.to_dict()` 序列化结果，包含 `thought/action_start/action_result/todo_update/answer/error` 等事件。

### 报告兼容关系

最终报告继续由 `DeepResearchService` 写入 `output/research/research_*.md`，以兼容现有报告列表、查看、导出、删除和 Webhook 推送接口。`agent_sessions.report_filename` 只保存文件名，`final_answer` 保存报告正文副本，便于会话详情直接展示。
