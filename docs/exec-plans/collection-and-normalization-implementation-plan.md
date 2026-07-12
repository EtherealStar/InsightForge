# 实现来源采集与内容清洗升级

本 ExecPlan 是一个持续维护的实现规格，必须遵循仓库根目录 `PLANS.md` 的格式和要求。它描述如何将当前单体式采集 Pipeline 升级为来源级扇出、阶段级队列、可重放原始产物和版本化确定性清洗系统。执行者只需要本文件和当前工作树即可完成实现；每个里程碑都应先写测试、再接入下一层，并把实际结果补回本文件。

## Purpose / Big Picture

完成后，系统可以为每个受治理来源独立发现候选、限速抓取、重试和熔断；一个来源失败不会阻塞其他来源。静态 HTTP、RSS、JSON、PDF 和明确要求渲染的页面分别走合适的 Fetch Engine，原始响应可在 24 小时内离线重放。清洗结果以不可变的 Content Block 保存逐字正文、结构和定位，任何重清洗都产生新版本；低质量页面会明确进入静态重试、浏览器重试、治理审核或拒绝，而不会悄悄进入知识库。

可观察的结果是：启动 Celery worker 后运行一次 Collection Run，PostgreSQL 中能看到每个 Source Fetch Task 和 Raw Fetch Artifact 的状态；固定页面夹具重放后能看到 `accepted`、`retry_render`、`review_required`、`rejected` 四种门禁结果；只有 `accepted` 结果进入 `ingest`，并交给来源治理/Document Cluster 计划继续处理。

## Progress

- [x] （2026-07-13）完成现状盘点、窄 Protocol 和 `014_collection_normalization.sql` 数据库迁移设计。
- [x] （2026-07-13）实现 Collection Run、Source Fetch Task、Fetch Candidate、artifact、Normalized Document 和 Content Block 模型及 PostgreSQL/Blob Store。
- [x] （2026-07-13）实现 RSS、Sitemap、Listing、API、Search Connector 与 HTTP/Browser Fetch Engine；HTTP 聚焦测试覆盖 304、大小限制和阻断页。
- [ ] （2026-07-13）部分实现来源级限速、条件请求、队列隔离、reconciler 和 Redis 降级（已完成保守进程内 limiter、六队列路由和 PostgreSQL fan-in；剩余 Redis 分布式 token bucket、动态升降并发和恢复演练）。
- [x] （2026-07-13）实现无网络 Normalize、稳定 Content Block ID、版本化规则和四态门禁。
- [ ] （2026-07-13）部分接入 `ingest`/`enrich` 边界（已完成 accepted 且 A/B/C 来源才发 ingest 消息；剩余实际知识入库适配器及删除旧兼容 Pipeline 函数）。
- [ ] （2026-07-13）部分完成固定夹具、集成、故障恢复、容量和可观察性验收（已有四态脱敏 fixture；尚未执行 PostgreSQL/Redis/worker、容量和 Prometheus 验收）。

## Surprises & Discoveries

- Observation: 当前目标设计明确要求直接切换，不保留 Crawlee、旧 WebCrawler、全局 Pipeline 或生产 shadow 双写。
  Evidence: `docs/adr/0003-source-fanout-fetch-architecture.md` 的 Consequences；`docs/design-docs/collection-and-normalization.md` 的“直接迁移”。
- Observation: Markdown 不是证据权威表示，Content Block 才是可引用的逐字正文。
  Evidence: `docs/adr/0004-versioned-deterministic-normalization.md` 的 Consequences 和设计文档第 7 节。
- Observation: Redis 只能提供可重建的加速与协调，Collection Run 的 fan-in 必须读取 PostgreSQL 状态机。
  Evidence: `docs/design-docs/collection-and-normalization.md` 第 3、9、10 节。
- Observation: 现有 `core.retry.with_retry` 原先只包装同步函数，无法捕获异步 `httpx` 请求抛出的异常。
  Evidence: 已增加 coroutine 分支；`test_fetch_engine.py` 与旧 `test_tools.py` 合跑 69 passed。
- Observation: 当前工作树缺少测试引用的 `evals/` 实现，且 embedding mock 与既有 `http_client` 参数不兼容，导致全量测试存在与本计划无关的基线失败。
  Evidence: 全量结果 299 passed、32 failed、53 skipped；其中 25 个为 `evals.*` ModuleNotFoundError，1 个为既有 embedding mock TypeError，事件循环相关 7 个本次诱发失败已修复并复测通过。

## Decision Log

- Decision: 采用六类独立队列 `fetch.http`、`fetch.browser`、`normalize`、`ingest`、`enrich`、`ocr`。
  Rationale: 浏览器、OCR、Embedding 或 LLM 变慢时不能占用静态抓取槽位；队列边界与资源特征在目标设计中已固定。
  Date/Author: 2026-07-13 / Codex。
- Decision: HTTP 默认路径使用异步 `httpx`，Playwright 每个 artifact 最多升级一次。
  Rationale: 静态来源应获得高并发；无限 browser fallback 会造成循环重试和内存失控。
  Date/Author: 2026-07-13 / Codex。
- Decision: Normalize 只读 artifact，不访问网络；LLM 只提供候选分类或异常元数据建议。
  Rationale: 固定输入可重放，证据正文不会被生成式改写，质量门禁可解释。
  Date/Author: 2026-07-13 / Codex。
- Decision: 以 PostgreSQL 状态和幂等键作为正确性边界，Redis 故障时静态 HTTP 可保守降级，browser/严格限速来源暂停。
  Rationale: 缓存丢失只能降低吞吐，不得改变任务、artifact 或最终入库结论。
  Date/Author: 2026-07-13 / Codex。

## Outcomes & Retrospective

截至 2026-07-13，基础领域、发现、HTTP 获取、artifact、确定性清洗和 Celery 队列边界已经落地，但真实基础设施端到端和容量演练尚未完成。本次不能宣称完整生产切换：旧 Pipeline 兼容函数仍存在，discover 来源配置和实际 ingest adapter 仍需完成。静态成功率、browser fallback、100 来源/10,000 candidate、Redis 清空恢复均未执行。

## Context and Orientation

当前旧链路由 `infrastructure/web_crawler.py`、旧 `NewsCollector` 和全局 Pipeline 负责下载、Markdown 转换、保存文档、分块、向量化和事实抽取。目标链路把这些职责拆成发现、获取、artifact、清洗、准入/去重和知识增强几个阶段。`Collection Run` 是一批来源的调度周期；`Source Fetch Task` 是一个来源在本轮的可重试任务；`Fetch Candidate` 只是 Connector 发现的资源线索；`Raw Fetch Artifact` 保存响应事实；`Normalized Document` 是指定规则版本生成的结构化结果；`Content Block` 是可稳定引用的逐字单元。

基础设施实现放在 `infrastructure/`，编排和业务规则放在 `services/`，Celery task 只传 ID、调用 Service 和推进状态。`core/protocols.py` 增加窄 Protocol，`core/factory.py` 负责组装。PostgreSQL 保存 run/task、游标、artifact 元数据、生命周期和最终结论；Blob Store 保存压缩 body；Redis 保存消息、token bucket、短租约、热点幂等和冷却信息。来源治理与近重复归簇由 `source-governance-and-deduplication-implementation-plan.md` 负责，本计划只向它交付 `accepted Normalized Document`。

## Plan of Work

### Milestone 1: 建立领域模型、Protocol、迁移和回放夹具

在 `models/` 创建纯数据模型：Collection Run、Source Fetch Task、Fetch Candidate、Raw Fetch Artifact、Normalized Document、Content Block、Source Cursor、Source Fetch Policy、Fetch Result 和 Normalization Outcome。为状态使用离散枚举和明确原因码，不添加统一质量分数。

在 `core/protocols.py` 增加 `SourceConnectorProtocol`、`FetchEngineProtocol`、`CollectionRunStoreProtocol`、`FetchArtifactStoreProtocol`、`FetchBlobStoreProtocol`、`NormalizationServiceProtocol`、`NormalizedDocumentStoreProtocol` 和 `SourceRateLimiterProtocol`。在 `infrastructure/` 创建 PostgreSQL/Blob/Redis 实现，在 `core/factory.py` 注册工厂。新增 migration 保存稳定幂等键、来源游标、ETag/Last-Modified、artifact MIME、body hash、生命周期、规则版本和审计字段；Celery 消息只携带 ID。

从 RSS、静态 HTML、动态 HTML、PDF、阻断页、噪声页和字符集异常页面采集脱敏回放夹具。夹具包含预期媒体类型、状态码、正文定位和最终 outcome，使后续测试不依赖外网。

### Milestone 2: 实现 Connector 与来源级调度

实现 `RssConnector`、`SitemapConnector`、`ListingConnector`、`ApiConnector` 和 `SearchConnector`。Connector 只发现候选，不下载正文，不递归遍历站点；每个候选包含 source profile、规范化 URL、发现时间、cursor、预期媒体类型和稳定幂等键。URL 规范化必须处理默认端口、fragment、追踪参数和重定向后的 canonical 候选，并在测试中验证重复发现不会生成重复候选。

实现 Collection Orchestrator：Beat 创建一个 Collection Run，按每个 Source Profile 的 `next_due_at` 扇出 Source Fetch Task；连续无变化延长间隔，发现更新缩短间隔，连续失败指数退避并熔断。PostgreSQL 状态机负责 fan-in，允许 `partial_failed`，reconciler 根据 pending/running/超时状态补偿丢失的 Celery 消息。

### Milestone 3: 实现 HTTP/Browser Fetch Engine 与 artifact 生命周期

`HttpFetchEngine` 使用异步 `httpx`，支持 RSS/HTML/JSON/PDF/附件、重定向、压缩、字符集和条件请求。304 只更新观测时间；200 先计算 Raw body SHA-256，命中相同 body 时复用已有 Normalize 结果。双重校验 MIME 与文件头，限制响应大小、解压比例和 PDF/Office 类型；403、429、验证码和阻断页记录为 blocked 并触发来源冷却。

`BrowserFetchEngine` 使用 Playwright，只处理来源显式 `render_required` 或 outcome 为 `retry_render` 的候选。每个 artifact 只允许一次静态到浏览器升级，仍失败则 `review_required` 或 `rejected`，禁止循环。Raw body 默认保留 24 小时；形成 active/superseded Document Version 或被 Evidence Reference 引用时晋升为 retained。清理只删除 body，保留元数据、hash、响应结果和原因码。

### Milestone 4: 实现来源限速、队列隔离、Redis 降级与可观测性

实现来源级 token bucket、域名并发和冷却状态。初始基线为 `fetch.http` 全局并发 32、单域名默认并发 2、来源上限 4-8；`fetch.browser` 每 Worker 最多 2 个 browser context。429、403、高超时和阻断页快速降并发，连续健康时缓慢恢复。Redis 正常时保存热点租约和限速；Redis 不可用时 RSS/普通静态 HTTP 使用 PostgreSQL 幂等与进程内保守限速，browser/严格限速来源暂停，恢复后由 PostgreSQL 状态补偿。

为每个阶段部署独立 Celery worker 和 routing key。日志、trace 和数据库共享 `collection_run_id`、`source_task_id`、`candidate_id`、`artifact_id`。Prometheus 记录发现数、HTTP 状态、队列等待、重试/超时/熔断、304、body 复用、browser fallback、artifact 晋升/清理和 `discovered -> fetched -> normalized -> accepted` 漏斗。

### Milestone 5: 实现可重放 Normalize 与 Content Block 门禁

创建无网络的 `NormalizationService`。按固定顺序校验媒体和编码，收集 JSON-LD/OpenGraph/meta/feed/header 元数据候选，应用来源 selector，运行 `markdownify`、`trafilatura`、HTML text fallback，去除导航、广告、推荐、版权、订阅、模板和重复段落，再构建 heading、paragraph、list、table、quote、code、caption 等 Content Block。

每个 block 保存由规范化版本、顺序和逐字内容派生的稳定 `block_id`、`heading_path`、CSS/XPath/页码定位、extractor 和 `normalizer_version`。Markdown 由 blocks 派生，不作为证据唯一锚点。清洗必须保存候选检测事实和选择理由，但输出只允许 `accepted`、`retry_render`、`review_required`、`rejected` 及原因码，例如 `body_too_short`、`link_density_high`、`title_mismatch`、`blocked_page`、`date_conflict`、`extractor_disagreement`、`unsupported_media_type`、`empty_body`、`not_article`。

LLM 如启用，只能判断页面类型或提出异常元数据候选；确定性规则必须校验建议，LLM 不得补写、翻译、摘要、润色或修改逐字 Content Block。Normalize 重跑创建新版本，Evidence Reference 永远指向具体版本和 block ID。

### Milestone 6: 接入准入/去重/知识增强并完成切换

新增 `normalize`、`ingest`、`enrich` 和 `ocr` Celery task。`normalize` 完成后按 outcome 分流：accepted 交给来源准入和 Document Cluster；retry_render 回到 browser 一次；review_required 进入治理队列；rejected 进入 24 小时清理。只有 accepted 才允许创建 Source Occurrence、Document Cluster、Document Version、chunks、vectors、facts 和 evidence。

先在 staging 用全部夹具运行新链路，确认旧代码不再写入新表；然后一次性切换 Beat、API 和 CLI 入口，删除 Crawlee 依赖、旧 WebCrawler、旧 NewsCollector 网络下载职责、`sites_config.json` 兼容路径、全局 Pipeline 锁和旧阶段名称。不要实现 adapter、feature flag 双写或旧任务状态迁移；迁移前保留回放夹具即可。

## Concrete Steps

所有命令从 `D:\study\Logos` 执行。每个里程碑开始前运行：

    git status --short
    git diff -- docs/exec-plans/collection-and-normalization-implementation-plan.md

先运行现有采集/入库基线测试，记录失败：

    python -m pytest tests/test_pipeline_service.py tests/test_document_ingestion_service.py -q

Milestone 1 的模型、migration、Protocol 和 fixture 测试建议命名为 `tests/test_collection_models.py`、`tests/test_collection_run_store.py`、`tests/test_fetch_artifact_store.py` 和 `tests/fixtures/collection/`，运行：

    python -m pytest tests/test_collection_models.py tests/test_collection_run_store.py tests/test_fetch_artifact_store.py -q

Milestone 2-4 运行 Connector、条件请求、限速、故障恢复和队列路由测试：

    python -m pytest tests/test_source_connectors.py tests/test_fetch_engines.py tests/test_rate_limiter.py tests/test_collection_orchestrator.py tests/test_collection_reconciler.py -q

需要基础设施时启动：

    docker compose up -d postgres redis qdrant

Milestone 5 运行确定性清洗和固定夹具回放：

    python -m pytest tests/test_normalization_service.py tests/test_content_blocks.py tests/test_normalization_fixtures.py -q

Milestone 6 运行全量测试并启动后端/worker 进行端到端观察：

    python -m pytest tests/ -q
    python -m delivery.server
    celery -A scheduler.celery_app worker -l info -P threads

实际迁移编号、测试数量、耗时和关键日志必须补到 `Artifacts and Notes`。

## Validation and Acceptance

Connector 验收：相同 cursor/URL 重放只产生一个 Fetch Candidate；分页、lastmod、API cursor 和规范化 URL 在边界输入下可恢复。HTTP 验收：304 不产生新 body，重复 200 复用 hash，MIME/文件头/大小/解压限制生效，重定向和字符集正确保存。Browser 验收：静态到浏览器最多一次升级，升级后失败不会回到静态循环。

状态验收：单来源失败只使对应 Source Fetch Task 失败；Collection Run 可变为 `partial_failed` 并完成其他来源；worker 中断、Celery callback 丢失和超时后 reconciler 能依据 PostgreSQL 补偿，重复执行不重复创建 artifact 或 normalized version。清空 Redis 后重新运行，候选、artifact、outcome 和入库结论不变。

Normalize 验收：每个 fixture 能稳定生成同样的 block ID、顺序、逐字文本和定位；规则版本变化产生新 Normalized Document 而不覆盖旧版本；accepted/retry_render/review_required/rejected 四态及原因码均有测试；LLM mock 的任何改写建议都不能改变 Content Block；D/unknown、review_required 和 rejected 不能进入 Qdrant、全文索引或 fact 抽取。

容量验收：100 个 Source Profile、每日 10,000 个 Fetch Candidate、每日 1,000 篇 accepted 文档；30 个同时到期静态来源在 10 分钟内完成抓取，静态成功率至少 95%，Playwright fallback 低于 10%，增加独立 worker 后吞吐近似线性扩展。

## Idempotence and Recovery

Candidate 使用 `source_profile_id + normalized_url + discovery_cursor` 形成稳定幂等键；Fetch Task 使用 `collection_run_id + source_profile_id`；artifact 使用请求事实和 body hash；Normalize 使用 `artifact_id + normalizer_version`；每次 Celery 重试只传这些身份键。数据库事务提交前不写 Redis，提交后 Redis 更新失败可重试。

PostgreSQL 迁移前备份并通过 `migrations/apply_migrations.py` 执行。artifact 清理先 dry-run，再删除超过 24 小时且未晋升的 body；永不删除最小审计元数据。Qdrant、Embedding 或 LLM 阶段失败时，accepted 文档和 normalized version 保留，任务可从 `enrich` 重试；旧 active version 继续可检索。禁止用 `git reset --hard` 或回退用户已有修改恢复工作区。

## Artifacts and Notes

执行过程中记录如下证据：

    migration: <实际编号>
    focused tests: <数量> passed in <耗时>
    fixture outcomes: accepted=<n>, retry_render=<n>, review_required=<n>, rejected=<n>
    static fetch success: <百分比>
    browser fallback: <百分比>
    redis rebuild: <恢复候选/索引数量>
    recovery drill: <worker interruption / redis loss / reconciler result>

当前证据（2026-07-13）：

    migration: 014_collection_normalization.sql
    focused tests: 71 passed, 5 skipped in 5.49s（采集新测试 + 既有工具/迁移回归）
    fixture outcomes: accepted=1, retry_render=1, review_required=1, rejected=1（文件已加入；尚未作为参数化 fixture suite 执行）
    full suite: 299 passed, 32 failed, 53 skipped in 21.59s（失败基线见 Surprises & Discoveries）
    static fetch success: 未执行
    browser fallback: 未执行
    redis rebuild: 未执行
    recovery drill: 未执行；`docker info` 在 24.1s 后超时，本机 Docker daemon 不可用

变更说明（2026-07-13）：执行 Milestone 1-5 的基础切片并更新真实进度；未通过基础设施验收的项目保持未完成，避免把代码骨架误记为可观察的生产结果。

## Interfaces and Dependencies

最终 `core/protocols.py` 应提供以下最小职责接口，实际分页和事务参数可按现有 Store 风格扩展，但不能合并成宽泛的 Pipeline 接口：

    class SourceConnectorProtocol(Protocol):
        def discover(self, profile: SourceProfile, cursor: SourceCursor | None) -> DiscoveryResult: ...

    class FetchEngineProtocol(Protocol):
        async def fetch(self, candidate: FetchCandidate, policy: SourceFetchPolicy) -> FetchResult: ...

    class CollectionRunStoreProtocol(Protocol):
        def create_run(self, run: CollectionRun) -> CollectionRun: ...
        def claim_task(self, task_id: str) -> SourceFetchTask: ...
        def advance_task(self, task_id: str, status: str, error: dict | None = None) -> None: ...
        def reconcile(self, run_id: str) -> CollectionRun: ...

    class FetchArtifactStoreProtocol(Protocol):
        def save_artifact(self, artifact: RawFetchArtifact) -> RawFetchArtifact: ...
        def find_by_body_hash(self, body_hash: str) -> list[RawFetchArtifact]: ...
        def promote(self, artifact_id: str, reason: str) -> None: ...
        def expire_unretained(self, before: datetime) -> int: ...

    class NormalizationServiceProtocol(Protocol):
        def normalize(self, artifact: RawFetchArtifact, body: bytes, rules: NormalizerRules) -> NormalizedDocument: ...

第三方依赖优先使用现有 `httpx`、`feedparser`、`trafilatura`、`markdownify`、Playwright 和 Blob Store；Normalize 不应引入会自行下载 URL 的库。外部网络调用统一遵循项目 `with_retry` 约定，日志使用 `structlog.get_logger()`，异常继承 `NewsAssistantError` 层次。

## Design Document Search Guide

需要快速回查机制时，可在 `docs/design-docs/collection-and-normalization.md` 搜索：`Collection Run`、`Source Fetch Task`、`Fetch Candidate`、`Raw Fetch Artifact`、`Normalized Document`、`Content Block`；这些词定位领域对象和生命周期。

搜索 `SourceConnectorProtocol`、`RssConnector`、`SitemapConnector`、`ListingConnector`、`ApiConnector`、`SearchConnector` 可定位发现层；搜索 `FetchEngineProtocol`、`HttpFetchEngine`、`BrowserFetchEngine`、`retry_render`、`最多一次` 可定位引擎选择和 browser fallback；搜索 `ETag`、`Last-Modified`、`304`、`Raw body SHA-256` 可定位条件请求与早期复用。

搜索 `并发、限速与调度`、`next_due_at`、`token bucket`、`熔断`、`fetch.http`、`fetch.browser` 可定位吞吐和资源隔离；搜索 `artifact`、`24 小时`、`Retained Fetch Artifact`、`晋升`、`清理` 可定位保留和治理边界；搜索 `Redis 不可用时`、`PostgreSQL 保存`、`reconciler` 可定位故障语义。

搜索 `Normalize Pipeline`、`markdownify`、`trafilatura`、`Content Block`、`source_locator`、`normalizer_version` 可定位清洗顺序和权威输出；搜索 `Normalization Outcome`、`body_too_short`、`link_density_high`、`extractor_disagreement` 可定位四态门禁和原因码；搜索 `LLM 只能辅助`、`不得补写` 可定位生成式组件的边界。

在 `docs/design-docs/source-governance-and-deduplication.md` 搜索 `处理位置`、`accepted`、`Source Occurrence`、`Document Cluster` 可确认本计划和去重计划的交接；搜索 `Source Profile`、`Source Tier`、`Document Version`、`Canonical Article` 可确认准入和版本晋升。不要在本计划中重新实现 SimHash、shingle 或 Evidence Verification。

在 `docs/design-docs/protocol-contracts.md` 搜索 `DocumentStoreProtocol`、`UploadStoreProtocol`、`Protocol`、`PostgreSQL 权威` 可对齐现有 Store 风格；在 `docs/adr/0003-source-fanout-fetch-architecture.md` 搜索 `Considered Options`、`直接移除 Crawlee`、`队列`；在 `docs/adr/0004-versioned-deterministic-normalization.md` 搜索 `Content Block`、`版本化`、`四种`、`Evidence Reference`；在 `docs/design-docs/structured-intelligence-model.md` 搜索 `Evidence Reference`、`Source Occurrence`、`Document Version` 以确认下游证据引用不变量。

在 `docs/design-docs/tech-decisions.md` 搜索 `Celery`、`Redis`、`PostgreSQL`、`Playwright`、`trafilatura` 和 `httpx` 可快速核对基础设施选型理由。统一英文领域术语则搜索 `CONTEXT.md` 中的 `Collection Run`、`Fetch Candidate`、`Normalized Document`、`Content Block` 和 `Source Occurrence`。
