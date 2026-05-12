# Protocol 接口契约详细设计

> **来源**：从 [ARCHITECTURE.md](../../ARCHITECTURE.md) §5 迁出的 Protocol 完整设计文档。

---

系统通过 `typing.Protocol` 定义接口契约，是**架构可替换性的基石**。所有 Protocol 均标记为 `@runtime_checkable`，定义在 `core/protocols.py`。

---

## 1. ArticleStoreProtocol

```python
class ArticleStoreProtocol(Protocol):
    def save_articles(self, articles: list[Article]) -> int: ...
    def get_unembedded(self, limit: int = 100) -> list[Article]: ...
    def mark_embedded(self, article_ids: list[int]) -> None: ...
    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Article]: ...
    def get_recent(self, hours: int = 24, limit: int = 50) -> list[Article]: ...
    def get_stats(self) -> dict: ...
    def cleanup_old_articles(self, retention_days: int = 90) -> int: ...
```

### 当前实现：`PostgresArticleStore`

- **去重策略**：SHA256(url) → url_hash UNIQUE 约束
- **并发安全**：`INSERT ... ON CONFLICT DO NOTHING`
- **标签存储**：Postgres 原生 `JSONB` 格式

### 超出 Protocol 的额外方法

以下方法在 `PostgresArticleStore` 中实现但不在 Protocol 定义内，调用方直接依赖 concrete 类型：

| 方法 | 用途 | 调用方 |
|---|---|---|
| `delete_articles()` | 批量删除文章 | news_router |
| `get_article_by_id()` | 按 ID 获取单篇文章 | ReadArticleTool, news_router |
| `get_articles()` | 分页查询文章列表 | news_router |
| `count_articles()` | 文章总数统计 | news_router |
| `get_pending_summary()` | 获取待摘要文章 | SummaryService |
| `mark_pending_summary()` | 标记文章待摘要 | PipelineService |
| `mark_summarized()` | 标记文章已摘要 | SummaryService |
| `update_summary()` | 更新摘要和标签 | SummaryService |

### 父 chunk 存储方法（PostgreSQL 特有）

| 方法 | 用途 |
|---|---|
| `save_parent_chunks()` | 批量写入父 chunk 到 `parent_chunks` 表 |
| `get_parent_chunks_by_ids()` | 按 ID 列表获取父 chunks |
| `delete_parent_chunks_by_article_ids()` | 按文章 ID 删除关联父 chunks |

### 全文搜索方法（PostgreSQL FTS 特有）

| 方法 | 用途 |
|---|---|
| `search_parent_chunks_by_keyword()` | 使用 tsvector 全文搜索父 chunks |
| `backfill_search_vectors()` | 回填已有数据的 search_vector 索引 |
| `_segment_text()` | jieba 分词工具方法，供 FTS 索引和查询使用 |

---

## 2. VectorStoreProtocol

```python
class VectorStoreProtocol(Protocol):
    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int: ...
    def search_chunks(self, query_embedding: list[float], top_k: int = 10,
                      filters: dict | None = None) -> list[ChunkSearchResult]: ...
    def delete_by_article_ids(self, article_ids: list[int]) -> None: ...
```

### 当前实现：`PgVectorStore` (chunk 级别)

| 配置项 | 值 |
|---|---|
| 表名 | `child_chunks` |
| 距离度量 | cosine |
| 批量写入大小 | 50 条 |
| 主键 | `chunk_id` |

**统一存储设计**：
- 子 chunk 文本 + embedding → PostgreSQL `child_chunks` 表
- 父 chunk 文本 + 全文索引 → PostgreSQL `parent_chunks` 表
- 删除通过 `article_id` SQL 过滤

---

## 3. LLMClientProtocol

```python
class LLMClientProtocol(Protocol):
    def generate(self, system_prompt: str, user_message: str) -> str: ...
    def generate_stream(self, system_prompt: str, user_message: str) -> Iterator[str]: ...
    def generate_with_history(self, messages: list[dict]) -> str: ...
    def generate_with_history_stream(self, messages: list[dict]) -> Iterator[str]: ...
```

`generate_with_history` 系列方法接受 OpenAI 格式的消息列表 `[{"role": "system"|"user"|"assistant", "content": "..."}]`，支持 ReAct Agent 的多轮推理对话。

### 各客户端消息格式转换

| 客户端 | SDK 调用方式 | system 处理 |
|---|---|---|
| **OpenAI Compatible / OpenAI** | 直接传 `messages` 到 `chat.completions.create()` | `role: "system"` 原样传递 |
| **Gemini** | 提取 `system` 为 `system_instruction` | `user`/`assistant` 转为 `contents` 列表 |
| **Anthropic** | 提取 `system` 为独立参数 | 其余为 `messages` 列表 |

### 当前实现（4 个客户端）

| 客户端 | Provider 标识 | 默认模型 |
|---|---|---|
| `OpenAICompatibleClient` | `openai_compatible` | 用户自定义 |
| `OpenAIClient` | `openai` | `gpt-4o-mini` |
| `GeminiClient` | `gemini` | `gemini-2.0-flash` |
| `AnthropicClient` | `anthropic` | `claude-sonnet-4-20250514` |

---

## 4. EmbeddingClientProtocol

```python
class EmbeddingClientProtocol(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

**当前实现**：`OpenAICompatibleEmbeddingClient`
- 批量 50 条，自动分批
- 兼容任何 OpenAI 格式 Embedding API

---

## 5. RerankClientProtocol

```python
class RerankClientProtocol(Protocol):
    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[dict]:
        """对文档列表按与 query 的相关性重新排序。
        Returns: [{"index": int, "relevance_score": float}, ...] 按 relevance_score 降序。
        """
        ...
```

### 当前实现：`OpenAICompatibleRerankClient`

| 配置项 | 说明 |
|---|---|
| 兼容 API | Jina Reranker / SiliconFlow / Cohere 等 Cross-Encoder |
| 请求格式 | `POST {base_url}/rerank` |
| 启用方式 | `RERANK_ENABLED=true` 环境变量 |
| 功能定位 | 可选功能，混合检索后的精排步骤 |

---

## Protocol 与实际使用的差异

> **已知问题**：`ArticleStoreProtocol` 仅定义了 7 个基础方法，但实际代码依赖了超过 15 个额外方法。这意味着 Protocol 的"可替换性"承诺在当前阶段无法完全兑现。详见 [技术债务追踪器](../exec-plans/tech-debt-tracker.md) §2.1。

---

## 6. AgentSessionStoreProtocol

通用 Agent 会话存储，当前实现为 `AgentSessionStore`，使用 PostgreSQL 作为权威存储，Redis 作为热缓存。该接口同时服务普通问答和 Plan Execute 深度研究。

```python
class AgentSessionStoreProtocol(Protocol):
    def create_general_session(self, topic: str, messages: list[dict] | None = None) -> AgentSession: ...
    def create_session(self, topic: str, plan: dict | str | None, todos: list[ResearchTodo], messages: list[dict] | None = None) -> AgentSession: ...
    def get_session(self, session_id: str) -> AgentSession | None: ...
    def append_event(self, session_id: str, event: dict) -> None: ...
    def append_message(self, session_id: str, message: dict) -> None: ...
    def update_summary(self, session_id: str, summary: str, token_count: int, last_compacted_tokens: int, compact_failures: int = 0) -> AgentSession: ...
```

普通问答使用 `session_type=general_query` 与 `active` 状态；深度研究继续使用 `research_plan_execute` 与 planned/approved/running/completed 状态流。

---

## 7. MemoryStoreProtocol

三层记忆系统存储接口。当前实现为 `MemoryStore`，数据库为准。

```python
class MemoryStoreProtocol(Protocol):
    def get_active_core_memories(self, kind: str | None = None) -> list[CoreMemoryRevision]: ...
    def create_core_memory_revision(self, kind: str, title: str, content: str) -> CoreMemoryRevision: ...
    def list_memory_index(self, memory_types: list[MemoryType] | None = None) -> list[MemoryIndexItem]: ...
    def list_persistent_memories(self, status: MemoryStatus | None = None, memory_type: MemoryType | None = None) -> list[PersistentMemory]: ...
    def update_persistent_memory_status(self, memory_id: str, status: MemoryStatus) -> PersistentMemory: ...
```

核心记忆采用版本化 revision；持久记忆默认 pending，用户确认后变为 active 并进入 MEMORY 索引。
