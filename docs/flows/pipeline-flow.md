# Pipeline 定时管线全流程

> 覆盖从 Celery Beat 触发到文章可被检索的完整数据摄入链路。

---

## 触发机制

Pipeline 由 Celery Beat 定时触发（每 5 分钟检查一次），通过 Redis 频率门控保证实际执行间隔：

\Celery Beat (crontab */5)
  -> scheduler.tasks.run_pipeline_task
  -> Redis GET logos:last_pipeline_run
  -> 检查 elapsed_hours >= fetch_interval_hours (默认 4h)
  -> 通过则执行，否则返回 Skipped
\
也可通过 CLI 或 API 手动触发：
- CLI: python -m delivery.cli pipeline
- API: POST /api/news/pipeline 返回 task_id，前端再轮询 GET /api/tasks/{task_id}

手动触发绕过频率门控，强制执行。

---

## 总体流程

\\mermaid
sequenceDiagram
    participant Beat as Celery Beat
    participant Worker as Celery Worker
    participant PS as PipelineService
    participant NC as NewsCollector
    participant WC as WebCrawler
    participant MDC as NewsMarkdownConverter
    participant PAS as PostgresArticleStore
    participant SS as SummaryService
    participant CS as ChunkingService
    participant EC as EmbeddingClient
    participant PVS as PgVectorStore

    Beat->>Worker: run_pipeline_task
    Worker->>PS: run()
    
    Note over PS: Step 1-2: 采集
    PS->>NC: fetch_all() (RSS/feedparser)
    NC-->>PS: rss_articles
    PS->>WC: crawl_all(sites)
    WC-->>PS: web_articles
    
    Note over PS: Step 3: Markdown 转换
    PS->>MDC: convert_batch(articles)
    MDC-->>PS: articles (content=Markdown)
    
    Note over PS: Step 4: 存储去重
    PS->>PAS: save_articles(articles)
    PAS-->>PS: new_count (INSERT ON CONFLICT DO NOTHING)
    
    Note over PS: Step 5: AI 摘要
    PS->>SS: summarize_pending()
    SS->>SS: _process_batch(batch_size=5, max_retries=3)
    SS->>PAS: mark_summarized(ids)
    
    Note over PS: Step 6-9: 分块+向量化
    PS->>PAS: get_unembedded()
    PAS-->>PS: pending articles
    PS->>CS: chunk_articles(articles)
    CS-->>PS: all_children, all_parents
    PS->>EC: embed(child_texts)
    EC-->>PS: embeddings
    PS->>PVS: add_chunks(children, embeddings)
    PS->>PAS: save_parent_chunks(parents)
    PS->>PAS: mark_embedded(ids)
\
---

## 各阶段详解

### 阶段 1: 数据采集 (_collect_all)

**RSS 抓取** — NewsCollector.fetch_all()
- 读取 data/feeds_config.json 中的 RSS 源列表
- 使用 ThreadPoolExecutor 并发抓取多个 RSS 源
- 使用 feedparser 解析每个 RSS/Atom feed
- 提取标题、链接、发布时间、作者、摘要
- 语言检测：按 source 配置的 language 字段标记

**网页爬取** — WebCrawler.crawl_all()
- 读取 data/sites_config.json 中的爬虫规则
- 使用 Crawlee (BeautifulSoupCrawler) 抓取网页
- 支持 CSS selector 自定义提取规则
- 单页面超时 + 错误隔离（单源失败不影响其他源）

**错误处理**：RSS 和爬虫各自独立 try/except，一个源失败不会终止整个采集阶段。
Celery 任务本身启用 autoretry/backoff；任务级异常会自动重试，单源失败则记录并继续。

### 阶段 2: Markdown 转换 (NewsMarkdownConverter)

NewsMarkdownConverter.convert_batch(articles)
- HTML 正文提取：	rafilatura 或 BeautifulSoup + markdownify
- 保留标题层级结构
- 提取元数据：作者、发布日期、语言
- rticle.content 存储 Markdown 格式正文

### 阶段 3: 存储去重 (PostgresArticleStore)

PostgresArticleStore.save_articles(articles)
- 去重策略：SHA256(url) -> url_hash 字段，UNIQUE 约束
- 写入：INSERT ... ON CONFLICT (url_hash) DO NOTHING
- 初始状态：status = pending_summary
- 返回实际新增文章数 
ew_count

### 阶段 4: AI 摘要 (SummaryService)

SummaryService.summarize_pending()
- 获取 status = pending_summary 的文章
- 按 summary_batch_size (默认 5) 分批发送给 LLM
- Prompt：生成 50-150 字中文摘要 + 2-5 个分类标签
- 单批最多重试 3 次（MAX_RETRIES = 3）
- 3 次全部失败：直接标记 summarized（无摘要），让文章继续流转
- LLM 返回 JSON 解析失败时自动重试
- 成功则写入 summary + 	ags (JSONB) 并标记 summarized

**回退路径**：如果 SummaryService 未配置（summary_llm_client=None），直接将 pending_summary 标记为 summarized。

### 阶段 5: 父子分块 (ChunkingService)

ChunkingService.chunk_articles(articles)
- 子 chunk：按 Markdown 标题结构切分，每个 <= chunk_max_child_tokens (默认 512)
- 父 chunk：聚合若干子 chunk，目标大小 chunk_target_parent_tokens (默认 1024)
- 重叠：父 chunk 间共享尾部子 chunk，实现 ~ chunk_overlap_tokens (默认 100)
- 短文档 (<= 1024 tok) 同时视为子 chunk 和父 chunk
- 子 chunk 通过 parent_chunk_id 明确归属一个父 chunk

**回退路径**：如果 ChunkingService 未配置，跳过向量化阶段。

### 阶段 6: 向量化写入

**子 chunk Embedding** — OpenAICompatibleEmbeddingClient.embed()
- 批量 50 条，自动分批
- 兼容任何 OpenAI 格式 Embedding API

**向量存储** — PgVectorStore.add_chunks()
- 写入 PostgreSQL child_chunks 表 (pgvector cosine 距离)
- 批量 50 条

**父 chunk 存储** — PostgresArticleStore.save_parent_chunks()
- 写入 PostgreSQL parent_chunks 表
- 自动触发 jieba 分词生成 search_vector (tsvector)

**状态更新** — mark_embedded(article_ids) 将文章状态从 summarized 更新为 embedded

---

## ArticleStatus 生命周期

\\mermaid
stateDiagram-v2
    [*] --> stored: 新入库
    stored --> pending_summary: 标记待摘要
    pending_summary --> summarized: AI 摘要完成
    pending_summary --> summarized: 无摘要服务，直接跳过
    summarized --> embedded: 分块+向量化完成
    embedded --> [*]: 可被检索

    note right of stored: status initially set
    note right of pending_summary: 等待 SummaryService 处理
    note right of summarized: 向量化前等待状态
    note right of embedded: 最终状态
\
---

## 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| etch_interval_hours | 4 | Pipeline 执行间隔（小时） |
| max_articles_per_fetch | 20 | 单次采集最大文章数 |
| summary_batch_size | 5 | AI 摘要每批文章数 |
| summary_use_same_llm | true | 摘要是否复用主 LLM |
| chunk_max_child_tokens | 512 | 子 chunk 最大 token |
| chunk_target_parent_tokens | 1024 | 父 chunk 目标 token |
| chunk_overlap_tokens | 100 | 父 chunk 重叠 token |
| embedding_vector_size | 1536 | pgvector 向量维度 |

---

## 错误处理策略

Pipeline 每个阶段独立 try/except，失败记日志不终止后续：

| 阶段 | 失败后果 | 影响 |
|------|---------|------|
| 采集 | 记录错误，继续后续处理 | 本次可能缺少部分来源文章 |
| Markdown 转换 | 跳过该阶段，原文入库 | content 可能为 HTML |
| 存储 | 记录错误 | 文章丢失 |
| AI 摘要 | 标记 summarized 跳过，文章继续流转 | 缺少摘要和标签 |
| 向量化 | 记录错误，下次重试 | 文章暂不可检索 |

---

## 相关文档

- [ARCHITECTURE.md](../../ARCHITECTURE.md) §4 — 分层架构
- [ARCHITECTURE.md](../../ARCHITECTURE.md) §7 — 数据模型
- [db-schema.md](../generated/db-schema.md) — ArticleStatus 生命周期
- [search-flow.md](search-flow.md) — 向量化后的检索链路
- [config-flow.md](config-flow.md) — 配置管理
