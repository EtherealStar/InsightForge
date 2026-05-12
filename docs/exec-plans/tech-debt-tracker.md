# Logos 技术债务与架构遗留问题清单 (Tech Debt Tracker)

> **基于代码版本**：当前 main 分支最新代码

---

## 一、已知缺陷

### 1. Scheduler 缺少日志持久化

**位置**：`scheduler/`

调度器的任务执行结果仅通过 `logging` 输出到控制台/文件，无法从 API 查询历史执行记录。前端无法展示 Pipeline 的执行历史和状态。

**建议**：将执行记录存储到 PostgreSQL 或专用表中。

### 2. 测试覆盖不完整

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

## 二、架构遗留问题

### 1. API Router 每次请求重建服务实例

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

### 2. WebhookService 缺少 Protocol 定义

**位置**：`services/webhook_service.py`

`WebhookService` 没有对应的 Protocol 接口，也没有通过 Factory 创建，而是在各 Router/Service 中直接 `WebhookService()` 实例化。与系统其他组件的依赖注入模式不一致。

**建议**：如果未来有替换需求（如改用消息队列推送），应提取 Protocol 接口。

---

## 三、暂时workaround的地方

### 1. 语言检测过于简单

**位置**：`infrastructure/web_crawler.py` — `_detect_language()`

仅通过中文字符占比 >10% 判断中文、<1% 判断英文，无法处理：
- 日文/韩文等东亚语言
- 中英混排文章
- 其他语种

**建议**：使用 `langdetect` 或 `lingua-py` 等专业库替代。

---

## 四、需要重构的模块

暂无高优先级条目。

> 已处理：`models/article.py` 已拆出 `ArticleEntity`、`ArticleDTO` 与 `ArticleMapper`，并保留 `Article` 兼容别名以避免破坏现有 API 和服务调用。

---

## 五、性能/安全隐患

### 1. Pipeline 无并发抓取 (性能隐患)

**位置**：`infrastructure/collector.py`, `services/pipeline_service.py`

RSS 抓取仍然是串行的（逐个 feed 处理），当 RSS 源较多时抓取缓慢。虽然 `WebCrawler` 使用了 Crawlee 实现了异步并发，但 RSS Collector 没有。

**建议**：使用 `ThreadPoolExecutor` 或 `asyncio` 并发抓取多个 RSS 源。

### 2. 无认证/授权 (安全隐患)

所有 API 端点完全开放，无任何认证机制。配置管理 API（`/api/config`）可以读写 `.env` 文件中的 API Key。

### 3. 配置 API 可能泄露敏感信息 (安全隐患)

`/api/config` 虽然对 API Key 做了脱敏处理（只显示前后几位），但 `/api/config` 的 PUT 接口可以任意修改 `.env` 文件内容。

---

## 六、不规范实现

### 1. 日期提取逻辑重复

**位置**：
- `infrastructure/markdown_converter.py` — `_extract_from_meta_tags()` 和 `_parse_datetime()`
- `infrastructure/web_crawler.py` — `_extract_publish_date()`

两个文件都实现了从 HTML meta 标签提取发布时间的逻辑，搜索的 meta 标签列表几乎完全一致（`article:published_time`, `publishdate`, `publish_date`, `og:article:published_time`）。`markdown_converter.py` 的实现更完善（支持更多日期格式），`web_crawler.py` 的实现更简单。

**建议**：将日期解析和 meta 标签提取抽取为共享工具函数，两处统一调用。

### 2. 语言检测逻辑重复

**位置**：
- `infrastructure/web_crawler.py` — `_detect_language()` 函数
- `infrastructure/collector.py` 中也有类似的语言检测逻辑

基于中文字符占比的简单语言检测在多处重复出现。

**建议**：抽取到 `core/utils.py` 或 `models/article.py` 作为公共方法。

### 3. ArticleStatus 状态机无强制约束

**位置**：`models/article.py` — `ArticleStatus`

定义了 5 个状态（`raw`, `stored`, `pending_summary`, `summarized`, `embedded`），但状态转换没有在代码中强制执行。任何代码都可以将文章设置为任意状态，没有状态机保护。

实际上 `raw` 状态从未被使用（`save_articles()` 默认保存为 `stored`），而 `stored` 状态在有摘要服务时会自动变为 `pending_summary`。

### 4. 前端 api/index.ts 是 TypeScript 但项目未配置 TypeScript

前端仅 `api/index.ts` 一个文件使用 TypeScript，其余所有文件（`main.js`, `router/index.js`, `*.vue`）均为 JavaScript。项目缺少 `tsconfig.json` 配置，TypeScript 的类型检查能力未被利用。

**建议**：统一为 JS 或全面迁移到 TS。

### 5. newsapi_router 中的裸异常捕获

`newsapi_router.py` 中多处使用 `except:` 或 `except Exception`，且日期解析处使用裸 `except:`，吞掉了所有异常。

---

## 七、优先级建议

| 优先级 | 问题 | 模块 | 影响 |
|---|---|---|---|
|  高 | API Router 重建实例 | 架构遗留问题 | 性能、内存开销 |
|  高 | 无认证/敏感信息泄露 | 性能/安全隐患 | 安全风险 |
|  中 | Pipeline 无并发抓取 | 性能/安全隐患 | 性能瓶颈 |
|  中 | 测试覆盖不完整 | 已知缺陷 | 重构风险 |
|  中 | Article 模型职责过多 | 需要重构的模块 | 可维护性 |
|  中 | 裸异常捕获 | 不规范实现 | 故障排查困难 |
|  低 | 日期提取/语言检测重复 | 不规范实现 | 代码冗余 |
|  低 | WebhookService 缺少 Protocol | 架构遗留问题 | 扩展性 |
|  低 | TS/JS 混用 | 不规范实现 | 开发体验 |
