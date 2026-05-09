# Logos 当前架构问题清单

> **基于代码版本**：当前 main 分支最新代码

---

## 一、重复实现问题

### 1.1 RerankError 重复定义

**位置**：`core/exceptions.py` (L26-28) 和 `infrastructure/rerank_client.py` (L19-21)

两处都定义了 `RerankError`，且都继承自 `NewsAssistantError`。`rerank_client.py` 中的定义导入并使用了 `core.exceptions.NewsAssistantError` 但没有复用 `core.exceptions.RerankError`，而是自己重新定义了一个同名异常。

**建议**：删除 `rerank_client.py` 中的重复定义，统一使用 `core.exceptions.RerankError`。

### 1.2 日期提取逻辑重复

**位置**：
- `infrastructure/markdown_converter.py` — `_extract_from_meta_tags()` 和 `_parse_datetime()`
- `infrastructure/web_crawler.py` — `_extract_publish_date()`

两个文件都实现了从 HTML meta 标签提取发布时间的逻辑，搜索的 meta 标签列表几乎完全一致（`article:published_time`, `publishdate`, `publish_date`, `og:article:published_time`）。`markdown_converter.py` 的实现更完善（支持更多日期格式），`web_crawler.py` 的实现更简单。

**建议**：将日期解析和 meta 标签提取抽取为共享工具函数，两处统一调用。

### 1.3 语言检测逻辑重复

**位置**：
- `infrastructure/web_crawler.py` — `_detect_language()` 函数
- `infrastructure/collector.py` 中也有类似的语言检测逻辑

基于中文字符占比的简单语言检测在多处重复出现。

**建议**：抽取到 `core/utils.py` 或 `models/article.py` 作为公共方法。

### 1.4 QueryService 中的 RAG 检索与 QueryKnowledgeBaseTool 功能重叠

**位置**：
- `services/query_service.py` — `search()`, `answer()`, `answer_stream()` 方法
- `agent/tools/builtin/query_knowledge_base.py` — `QueryKnowledgeBaseTool._run()`

`QueryService` 中保留了旧的直接 RAG 检索逻辑（`search` + `answer` + `answer_stream`），同时 Agent 工具层有 `QueryKnowledgeBaseTool` 实现了更完善的语义检索（支持 Rerank）。但 `QueryService.answer_agent_stream()` 才是实际使用的入口，旧的 `answer()` / `answer_stream()` 方法已经是死代码。

**建议**：
- 移除 `QueryService` 中的旧 `search()`, `answer()`, `answer_stream()` 方法
- `QueryService` 简化为仅保留 `answer_agent_stream()` 作为 Agent 调度入口
- 或者将 `QueryService` 旧方法标记为 deprecated

---

## 二、架构设计问题

### 2.1 Protocol 接口与实际使用不一致

**问题**：`ArticleStoreProtocol` 仅定义了 7 个基础方法，但 `SQLiteArticleStore` 实际提供了超过 15 个方法（`get_article_by_id`, `get_articles`, `count_articles`, `delete_articles`, `get_pending_summary`, `mark_pending_summary`, `mark_summarized`, `update_summary` 等）。

大量代码直接依赖 `SQLiteArticleStore` 的额外方法而非 Protocol，导致 Protocol 的"可替换性"承诺无法兑现。例如：
- `SummaryService` 使用了 `update_summary()`, `mark_summarized()`, `get_pending_summary()`，TYPE_CHECKING 中直接导入 `SQLiteArticleStore`
- `ReadArticleTool` 使用了 `get_article_by_id()`
- 多个 Router 使用了 `get_articles()`, `delete_articles()` 等

**建议**：
- 将常用的额外方法加入 `ArticleStoreProtocol`
- 或承认当前阶段 Protocol 仅覆盖核心方法，其他方法允许 concrete 依赖

### 2.2 API Router 每次请求重建服务实例

**位置**：`delivery/api/` 下的所有 router 文件

每个 API 请求都通过 `get_config_manager()` 获取组件后即时创建 Service 实例：

```python
@router.post("/api/briefs/generate")
def generate_brief():
    mgr = get_config_manager()
    service = BriefService(mgr.article_store, mgr.llm_client, mgr.config.output_path)
    ...
```

虽然 `ConfigManager` 是单例（组件本身不重建），但每次请求都创建 `BriefService`、`PipelineService` 等 Service 对象，增加了不必要的对象创建开销。

**建议**：使用 FastAPI 的 `Depends()` 注入已缓存的 Service 单例，或在 `ConfigManager` 中缓存 Service 层实例。

### 2.3 newsapi_router.py 中的保存逻辑质量低

**位置**：`delivery/api/newsapi_router.py` — `save_article()` 方法 (L100-157)

存在多个问题：
- 调用了不存在的方法 `embedding_client.embed_text()` 和 `vector_store.add_article()`（实际 API 是 `embed()` 和 `add_articles()`）
- 裸 `except:` 异常捕获
- 保存成功时返回 `saved[0]`，但 `save_articles()` 返回的是 `int`（新增数量），不是文章列表
- 注释中包含 mock/placeholder 说明（如 `# mock update`）

**严重程度**：高 — 该接口在运行时会抛出 `AttributeError`，功能完全不可用。

### 2.4 WebhookService 缺少 Protocol 定义

**位置**：`services/webhook_service.py`

`WebhookService` 没有对应的 Protocol 接口，也没有通过 Factory 创建，而是在各 Router/Service 中直接 `WebhookService()` 实例化。与系统其他组件的依赖注入模式不一致。

**建议**：如果未来有替换需求（如改用消息队列推送），应提取 Protocol 接口。

---

## 三、过于简单 / 待完善的实现

### 3.1 语言检测过于简单

**位置**：`infrastructure/web_crawler.py` — `_detect_language()`

仅通过中文字符占比 >10% 判断中文、<1% 判断英文，无法处理：
- 日文/韩文等东亚语言
- 中英混排文章
- 其他语种

**建议**：使用 `langdetect` 或 `lingua-py` 等专业库替代。

### 3.2 关键词搜索过于简单

**位置**：`infrastructure/article_store.py` — `search_by_keyword()`

目前使用 SQLite 的 `LIKE '%keyword%'` 实现关键词搜索，性能差且不支持：
- 多关键词 AND/OR 组合
- 中文分词
- 相关度排序

**建议**：升级为 SQLite FTS5 全文搜索，或引入 Elasticsearch。

### 3.3 DeepResearchService 对 prompts 的硬依赖

**位置**：`services/deep_research_service.py`

`research_stream()` 方法内部直接 import 并使用 `agent.react.prompts.build_deep_research_prompt`，且直接创建 `ReActAgent` 实例。Service 层直接依赖 Agent 层，违反了分层架构的依赖规则（应该是 Agent 调用 Service，而非反过来）。

**建议**：将深度研究作为 Agent 层的一个模式，而非 Service 层的功能。

### 3.4 Pipeline 无并发抓取

**位置**：`infrastructure/collector.py`, `services/pipeline_service.py`

RSS 抓取仍然是串行的（逐个 feed 处理），当 RSS 源较多时抓取缓慢。虽然 `WebCrawler` 使用了 Crawlee 实现了异步并发，但 RSS Collector 没有。

**建议**：使用 `ThreadPoolExecutor` 或 `asyncio` 并发抓取多个 RSS 源。

### 3.5 Scheduler 缺少日志持久化

调度器的任务执行结果仅通过 `logging` 输出到控制台/文件，无法从 API 查询历史执行记录。前端无法展示 Pipeline 的执行历史和状态。

**建议**：将执行记录存储到 SQLite 或专用表中。

---

## 四、代码质量问题

### 4.1 Article 模型承担过多职责

**位置**：`models/article.py`

`Article` dataclass 同时包含：
- 领域属性（title, url, content, summary, tags, author）
- 数据库元数据（id, url_hash, status, created_at）
- Embedding 相关逻辑（`to_embedding_text()`）
- LLM context 格式化逻辑（`to_context_str()`）
- HTML 原文（html_content，仅抓取阶段使用）

职责过多，不符合单一职责原则。

**建议**：分离为 `Article`（纯领域）和 `ArticleEntity`（含 DB 元数据）或使用 DTO 模式。

### 4.2 ArticleStatus 状态机无强制约束

**位置**：`models/article.py` — `ArticleStatus`

定义了 5 个状态（`raw`, `stored`, `pending_summary`, `summarized`, `embedded`），但状态转换没有在代码中强制执行。任何代码都可以将文章设置为任意状态，没有状态机保护。

实际上 `raw` 状态从未被使用（`save_articles()` 默认保存为 `stored`），而 `stored` 状态在有摘要服务时会自动变为 `pending_summary`。

### 4.3 前端 api/index.ts 是 TypeScript 但项目未配置 TypeScript

前端仅 `api/index.ts` 一个文件使用 TypeScript，其余所有文件（`main.js`, `router/index.js`, `*.vue`）均为 JavaScript。项目缺少 `tsconfig.json` 配置，TypeScript 的类型检查能力未被利用。

**建议**：统一为 JS 或全面迁移到 TS。

### 4.4 测试覆盖不完整

**缺少测试的模块**：
- `services/webhook_service.py` — 无测试
- `services/brief_service.py` — 无测试
- `services/summary_service.py` — 无测试
- `services/web_search_service.py` — 无测试
- `services/deep_research_service.py` — 无测试
- `infrastructure/rerank_client.py` — 无测试
- `infrastructure/web_search_client.py` — 无测试
- `infrastructure/web_crawler.py` — 无测试
- `delivery/api/*` — 无任何 API 路由测试

---

## 五、安全问题

### 5.1 无认证/授权

所有 API 端点完全开放，无任何认证机制。配置管理 API（`/api/config`）可以读写 `.env` 文件中的 API Key。

### 5.2 配置 API 可能泄露敏感信息

`/api/config` 虽然对 API Key 做了脱敏处理（只显示前后几位），但 `/api/config` 的 PUT 接口可以任意修改 `.env` 文件内容。

### 5.3 newsapi_router 中的裸异常捕获

`newsapi_router.py` 中多处使用 `except:` 或 `except Exception`，且日期解析处使用裸 `except:`，吞掉了所有异常。

---

## 六、优先级建议

| 优先级 | 问题 | 影响 |
|---|---|---|
| 🔴 高 | newsapi_router.save 功能完全不可用 | 功能损坏 |
| 🔴 高 | RerankError 重复定义 | 异常捕获混乱 |
| 🟡 中 | Protocol 与实际使用不一致 | 架构承诺虚化 |
| 🟡 中 | QueryService 死代码 | 维护负担 |
| 🟡 中 | DeepResearchService 违反分层依赖 | 架构混乱 |
| 🟡 中 | 测试覆盖不完整 | 重构风险 |
| 🟢 低 | 日期提取/语言检测重复 | 代码冗余 |
| 🟢 低 | Article 职责过多 | 可维护性 |
| 🟢 低 | TS/JS 混用 | 开发体验 |
