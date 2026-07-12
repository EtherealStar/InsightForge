---
status: accepted
---

# 按来源扇出并移除 Crawlee

采集系统不再由单个全局 Pipeline 任务串行协调所有来源，也不再使用 Crawlee 作为网页采集框架。Beat 只创建一个 Collection Run，由编排器为每个 Source Profile 扇出独立的 Source Fetch Task；抓取结果先保存为 Raw Fetch Artifact，再由后续任务完成清洗、质量评估、去重和入库。默认 Fetch Engine 使用异步 `httpx` 获取 RSS 和静态 HTML；只有来源明确要求渲染或静态抓取质量持续不达标时才使用 Playwright。`feedparser` 只解析 Feed，`trafilatura` 只参与后续正文清洗，不再自行下载页面。

## Considered Options

- 继续调高 Crawlee 的站点内并发：不能解决 `crawl_all` 的跨来源串行、全局 Pipeline 锁和故障隔离问题。
- 保留 Crawlee 并把它提升为全局调度器：会把来源策略、浏览器生命周期和 Celery 任务状态耦合在一起，难以实现来源级游标和独立重试。
- 按来源扇出、按阶段汇合：增加任务编排和状态模型，但能隔离慢源/坏源，并让不同来源选择合适的抓取引擎。

## Consequences

- 需要新增 Collection Run、Source Fetch Task 和 Raw Fetch Artifact 的状态与幂等模型。
- 单个来源失败不再阻塞其他来源；重试、限速、熔断和动态渲染策略可以按来源独立演进。
- 清洗、去重、向量化和事实抽取不应继续绑定在来源抓取任务的同步调用栈中。
- 直接移除 Crawlee 依赖及其 RequestQueue/Statistics 生命周期，不保留旧 WebCrawler、全局 Pipeline 或双写兼容路径；迁移前只提取有代表性的原始页面作为新链路的回放测试夹具。
- Playwright 不是默认抓取路径；每个 Source Profile 必须显式声明或经治理策略升级到动态渲染，避免浏览器成本吞噬来源级并发。
- Raw Fetch Artifact 的 body 默认只保留 24 小时；形成 active/superseded Document Version 或被 Evidence Reference 引用后晋升为 Retained Fetch Artifact 并长期保存。普通重复转载、隔离、待审核和失败产物不自动晋升，除非管理员设置治理保留。
- PostgreSQL 保存 artifact 元数据、生命周期和内容哈希，Blob Store 保存原始 body；Celery 消息只传 artifact ID，Redis 不承担权威原文或保留状态。
- Collection Run 和 Source Fetch Task 采用 PostgreSQL 状态机汇合；不把 Celery chord callback 当作唯一完成信号。任务重复执行、worker 重启或部分来源失败后，汇总器都依据数据库中的权威状态恢复并推进。
- Redis 仅承担 Celery 消息、来源级限速、短期租约、幂等热点、熔断冷却和进度缓存。永久游标、任务最终状态、artifact 生命周期和去重结论必须能从 PostgreSQL 恢复。
- Redis 不可用时，普通 RSS/静态 HTTP 来源使用 PostgreSQL 幂等与保守的进程内限速继续运行；Playwright、严格限速及反爬敏感来源暂停。Redis 恢复后，编排器依据数据库状态补偿调度未完成任务。
- Celery 至少隔离 `fetch.http`、`fetch.browser`、`normalize`、`ingest` 和 `enrich` 队列，并为每类负载部署独立 Worker 与并发预算。浏览器渲染、Embedding 或 LLM 变慢时不得占用静态抓取的执行槽。
- 并发采用来源级自适应控制。`fetch.http` 初始全局并发为 32、单域名默认为 2，来源可配置 4-8 的上限；`fetch.browser` 每个 Worker 初始最多运行 2 个 browser context。系统根据 p95 延迟、429/403、超时率和正文成功率缓慢增并发、快速降并发并进入冷却，具体数值属于可配置初值而非协议常量。
- URL 发现与页面获取分离。`SourceConnectorProtocol` 的 RSS、Sitemap、Listing、API 和 Search 实现以声明式配置覆盖大多数来源，少量复杂站点使用专用 Connector；所有 Connector 统一输出 Fetch Candidate，Fetch Engine 不进行无边界的站点遍历。
- 调度以每个 Source Profile 的 `next_due_at` 为准，替代全局固定抓取间隔。连续无变化时延长、发现更新时缩短、连续失败时退避熔断；关键来源设置最大允许陈旧时间。调度使用离散业务优先级与近期变更记录，不生成统一来源分数。
- PDF 是一等 Fetch Candidate，下载后校验 MIME、文件头、大小和哈希，并复用文档解析链路生成 Content Block；扫描型 PDF 进入独立 OCR 队列。Office 附件只按来源显式开启，普通正文图片不默认 OCR，除非图片本身是主要内容。
- 系统只采集公开且无需登录的内容，尊重 robots.txt、来源条款和来源级频率配置。Playwright 只负责正常页面渲染，不破解 CAPTCHA、设备指纹或登录墙；403、429 和验证码响应记录为 `blocked` 并触发冷却。代理只用于固定出口、地域可用性或网络稳定性，不用于轮换规避封禁。
- 单机容量基线为 100 个 Source Profile、每日 10,000 个 Fetch Candidate、每日 1,000 篇 accepted Normalized Document；30 个同时到期的静态来源应在 10 分钟内完成抓取阶段，静态抓取成功率至少 95%，Playwright fallback 低于 10%。单个来源故障不得阻塞本轮其他来源，增加独立队列 Worker 后吞吐应近似线性扩展。
- OpenTelemetry trace 从 Collection Run 贯穿来源任务、artifact、清洗、去重和入库；Prometheus 记录队列等待、抓取耗时、HTTP 状态、重试熔断、浏览器 fallback、Normalization Outcome、重复命中和清理。日志、trace 与数据库记录共享 `collection_run_id`、`source_task_id` 和 `artifact_id`，正式运维必须展示来源健康度与 `discovered -> fetched -> normalized -> accepted -> clustered -> indexed` 漏斗。
- 迁移采用直接切换：先完成新模型、Store、Connector、Fetch Engine、Normalize 和队列任务，再一次性切换入口并删除旧代码。旧链路不得与新链路同时写入 Document Cluster，也不为旧配置或任务状态提供兼容适配器。
