# Logos 技术债务与架构遗留问题清单 (Tech Debt Tracker)

> **基于代码版本**：当前 main 分支最新代码
> **审计时间**：2026-05-19

---

## 一、已知缺陷

### 1. Scheduler 缺少日志持久化

**位置**：`scheduler/`

调度器的任务执行结果仅通过 `structlog` 输出到控制台/文件，无法从 API 查询历史执行记录。前端无法展示 Pipeline 的执行历史和状态。虽然 `tasks_router.py` 提供了通过 Celery `AsyncResult` 查询单次任务状态的能力，但缺乏历史执行记录的持久化和批量查询。

**建议**：将执行记录存储到 PostgreSQL 专用表中，增加 Pipeline/日报执行历史查询 API。

### 2. 测试覆盖不完整

**现有测试**（22 个测试文件）：
- `test_article_model.py`, `test_article_store.py`, `test_collector.py`
- `test_hybrid_search.py`, `test_markdown_converter.py`, `test_pgvector_store.py`
- `test_pipeline_service.py`, `test_react_agent.py`, `test_react_parser.py`
- `test_tools.py`, `test_query_service.py`, `test_query_router.py`
- `test_newsapi_router.py`, `test_research_plan_router.py`
- `test_summary_service.py`, `test_rerank_client.py`
- `test_agent_session_store.py`, `test_memory_service.py`
- `test_deep_research_service.py`, `test_plan_execute_runner.py`

**缺少测试的模块**：
- `services/webhook_service.py` — 无测试
- `services/brief_service.py` — 无测试
- `services/web_search_service.py` — 无测试
- `infrastructure/web_search_client.py` — 无测试
- `infrastructure/web_crawler.py` — 已有基础行为测试，仍缺少真实站点集成测试
- `infrastructure/embedding_client.py` — 仅通过集成测试间接覆盖，无独立单元测试
- `infrastructure/chunking_service.py` — 无独立单元测试
- `delivery/api/brief_router.py` — 无路由测试
- `delivery/api/config_router.py` — 无路由测试
- `delivery/api/webhook_router.py` — 无路由测试
- `delivery/api/settings_router.py` — 无路由测试
- `delivery/api/news_router.py` — 无路由测试
- `delivery/api/memory_router.py` — 无路由测试

### 3. `config.py` validator 中使用 `logging.warning` 而非 structlog

**位置**：`core/config.py` — `warn_empty_key()` (L101)

`AppConfig` 的 `field_validator` 中导入了 `structlog` 但实际使用的是标准库 `logging.warning()`。虽然有 `import structlog` 语句，但未实际使用。

```python
# 当前实现
import structlog
logging.warning(f"⚠️ {info.field_name} 为空 — 相关功能将被禁用")

# 应该使用
structlog.get_logger(__name__).warning(f"{info.field_name} 为空", field=info.field_name)
```

---

## 二、架构遗留问题

> ✅ **全部已修复**（2026-05-15）：通过将 Service 层实例的生命周期统一收归 `ConfigManager` 管理解决。

### ~~1. API Router 每次请求重建 Service 实例~~ ✅ 已修复

**修复方式**：在 `core/factory.py` 中新增 4 个 Service 工厂函数（`create_query_service`、`create_memory_service`、`create_webhook_service`、`create_deep_research_service`），`ConfigManager` 缓存这些 Service 单例并提供懒加载属性。`reload()` 时，当 LLM/Store/Embedding 等依赖变更，自动清空 `query_service`/`memory_service` 缓存触发下次访问重建。

**修改文件**：`core/factory.py`、`core/config_manager.py`、`delivery/api/query_router.py`、`delivery/api/research_router.py`、`delivery/api/webhook_router.py`、`scheduler/tasks.py`

**保留现状**：`BriefService`（仅 `/generate` 使用，含 `mgr.reload()`）和 `SummaryService`（仅 `/resummarize` 使用）保持请求级创建，因为它们使用频率低且需要读取 reload 后的最新配置。

### ~~2. WebhookService 缺少 Protocol 定义~~ ✅ 已修复

**修复方式**：在 `core/protocols.py` 新增 `WebhookServiceProtocol`，定义 4 个核心推送方法（`broadcast`、`send_to_channel`、`load_channels`、`get_auto_push`）。CRUD 方法保留在具体实现中。通过 `create_webhook_service()` 工厂函数创建，`ConfigManager` 统一管理生命周期。

**修改文件**：`core/protocols.py`、`core/factory.py`、`core/config_manager.py`

### ~~3. `DeepResearchService` 在 router 中被反复创建~~ ✅ 已修复

**修复方式**：`DeepResearchService` 通过 `create_deep_research_service()` 工厂函数创建，成为 `ConfigManager` 管理的单例。`research_router.py` 中 6 处 `DeepResearchService(output_dir=_RESEARCH_DIR)` 全部替换为 `get_config_manager().deep_research_service`。

**修改文件**：`core/factory.py`、`core/config_manager.py`、`delivery/api/research_router.py`

---

## 三、暂时 workaround 的地方

### 1. 语言检测过于简单

**位置**：`infrastructure/web_crawler.py` — `_detect_language()`、`infrastructure/collector.py` — `_detect_language()`

仅通过中文字符占比 >10% 判断中文、<1% 判断英文，无法处理：
- 日文/韩文等东亚语言
- 中英混排文章
- 其他语种

**建议**：使用 `langdetect` 或 `lingua-py` 等专业库替代。

### ~~2. Celery 任务缺乏细粒度重试补偿~~ ✅ 已修复

**位置**：`scheduler/tasks.py`

`run_pipeline_task`、`run_daily_brief_task`、`run_cleanup_task` 已统一启用 `autoretry_for=(Exception,)`、`retry_backoff` 与 `retry_jitter`。任务级异常会触发 Celery 自动重试；Pipeline 内部的阶段级/单源错误仍按原策略记录并继续。

---

## 四、需要重构的模块

暂无高优先级条目。

> 已处理：`models/article.py` 已拆出 `ArticleEntity`、`ArticleDTO` 与 `ArticleMapper`，并保留 `Article` 兼容别名以避免破坏现有 API 和服务调用。

---

## 五、性能/安全隐患

### ~~1. Pipeline 无并发抓取 (性能隐患)~~ ✅ 已修复

**位置**：`infrastructure/collector.py`, `services/pipeline_service.py`

`NewsCollector.fetch_all()` 已使用 `ThreadPoolExecutor` 并发抓取多个 RSS 源，单源失败仍独立记录，不影响其他源和后续 Pipeline 阶段。

### 2. 无认证/授权 (安全隐患)

所有 API 端点完全开放，无任何认证机制。特别是配置管理 API（`/api/config`）可以读写 `.env` 文件中的 API Key。

### 3. 配置 API 可能泄露敏感信息 (安全隐患)

**位置**：`delivery/api/config_router.py`

- `/api/config` GET 对 API Key 做了脱敏处理（只显示前后4位），这一点做得好
- 但 `/api/config` PUT 接口可以任意修改 `.env` 文件内容，无权限控制
- `/api/config/models` POST 接口在传入脱敏 key 时会从 .env 文件读取原始 key，间接暴露了读取真实 key 的路径

### 4. 单环境 .env 配置

**位置**：`core/config.py`

仅支持单一 `.env` 文件，无 dev/prod 环境区分。开发环境和生产环境共享同一份配置。

**建议**：支持 `.env.development`、`.env.production` 等多环境配置。

---

## 六、不规范实现

### 1. 日期提取逻辑重复

**位置**：
- `infrastructure/markdown_converter.py` — `_extract_from_meta_tags()` 和模块级 `_parse_datetime()`
- `infrastructure/web_crawler.py` — `_extract_publish_date()`

两个文件都实现了从 HTML meta 标签提取发布时间的逻辑，搜索的 meta 标签列表几乎完全一致（`article:published_time`, `publishdate`, `publish_date`, `og:article:published_time`）。`markdown_converter.py` 的实现更完善（支持更多日期格式），`web_crawler.py` 的实现更简单。

**建议**：将日期解析和 meta 标签提取抽取为共享工具函数，两处统一调用。

### 2. 语言检测逻辑重复

**位置**：
- `infrastructure/web_crawler.py` — `_detect_language()` 模块级函数
- `infrastructure/collector.py` — `NewsCollector._detect_language()` 静态方法

两处基于中文字符占比的语言检测逻辑完全一致，代码复制粘贴。

**建议**：抽取到 `core/utils.py` 作为公共方法。

### 3. ArticleStatus 状态机无强制约束

**位置**：`models/article.py` — `ArticleStatus`

定义了 5 个状态（`raw`, `stored`, `pending_summary`, `summarized`, `embedded`），但状态转换没有在代码中强制执行。任何代码都可以将文章设置为任意状态，没有状态机保护。

实际代码路径中 `raw` 状态从未被使用（`PostgresArticleStore.save_articles()` 默认保存为 `stored`），而 `stored` 状态在有摘要服务时会自动变为 `pending_summary`。

### 4. 前端 api/index.ts 是 TypeScript 但项目未配置 TypeScript

前端仅 `api/index.ts` 一个文件使用 TypeScript，其余所有文件（`main.js`, `router/index.js`, `App.vue`, `*.vue`）均为 JavaScript。项目缺少 `tsconfig.json` 配置，TypeScript 的类型检查能力未被利用。

**建议**：统一为 JS 或全面迁移到 TS。

### 5. newsapi_router 中的裸异常捕获

**位置**：`delivery/api/newsapi_router.py` — L175

`/save` 路由中向量化部分使用了 `except Exception:` 并静默吞掉异常（仅设置 `vectorized = False`），缺少日志记录。相比其他 router 的异常处理模式（使用 `logger.error`），此处不一致。

```python
# 当前 (L175)
except Exception:
    vectorized = False

# 建议
except Exception as e:
    logger.warning(f"向量化失败: {e}")
    vectorized = False
```

### ~~6. `scheduler/tasks.py` 跨层直接导入 Router 内部函数~~ ✅ 已修复

**位置**：`scheduler/tasks.py` — L44

RSS 源和网页爬取源的 JSON 读写已抽到 `core/source_config.py`。`settings_router.py` 和 `scheduler/tasks.py` 共同依赖该模块，避免 Scheduler 反向依赖 Delivery 层私有函数。

### ~~7. `WebCrawler.crawl_all` 中临时修改 `self.max_pages` 非线程安全~~ ✅ 已修复

**位置**：`infrastructure/web_crawler.py` — L148-151

`max_pages` 已作为参数从 `crawl_all()` 传入 `crawl_site()` / `_crawl()`，不再临时覆盖实例属性。新增测试覆盖 per-site `max_pages` 传递与实例状态不变。

---

## 七、优先级建议

| 优先级 | 问题 | 分类 | 状态 |
|---|---|---|---|
| 🔴 高 | 无认证/敏感信息泄露 | 性能/安全隐患 | ⬜ 待修复 |
| ~~🔴 高~~ | ~~API Router 每次请求重建 Service~~ | ~~架构遗留问题~~ | ✅ 已修复 |
| ~~🟡 中~~ | ~~Pipeline 无并发抓取~~ | ~~性能/安全隐患~~ | ✅ 已修复 |
| 🟡 中 | 测试覆盖不完整 | 已知缺陷 | ⬜ 待修复 |
| ~~🟡 中~~ | ~~Celery 缺乏细粒度重试~~ | ~~暂时 workaround~~ | ✅ 已修复 |
| ~~🟡 中~~ | ~~scheduler 跨层导入 router 私有函数~~ | ~~不规范实现~~ | ✅ 已修复 |
| 🟡 中 | 裸异常捕获 (newsapi_router) | 不规范实现 | ⬜ 待修复 |
| 🟢 低 | 日期提取/语言检测重复 | 不规范实现 | ⬜ 待修复 |
| ~~🟢 低~~ | ~~WebhookService 缺少 Protocol~~ | ~~架构遗留问题~~ | ✅ 已修复 |
| 🟢 低 | TS/JS 混用 | 不规范实现 | ⬜ 待修复 |
| 🟢 低 | 单环境 .env 配置 | 性能/安全隐患 | ⬜ 待修复 |
| 🟢 低 | config.py 中 logging 使用不一致 | 已知缺陷 | ⬜ 待修复 |
| ~~🟢 低~~ | ~~WebCrawler.max_pages 非线程安全~~ | ~~不规范实现~~ | ✅ 已修复 |
