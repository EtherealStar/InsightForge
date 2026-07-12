# 实现来源治理、稳定文档簇与多证据验证

本 ExecPlan 是一份持续更新的执行文档。实施期间必须维护 `Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective`，每次停工前都要让它们准确反映当前状态。

本计划遵循仓库根目录的 `PLANS.md`。执行者只需要当前工作树和本文件即可继续工作；本文因此重复解释实现所需的领域概念、架构边界、步骤、命令和验收标准，不假定读者记得此前的设计讨论。

## Purpose / Big Picture

InsightForge 现在把每个 URL 当成一篇独立知识文档。相同文章被不同网站转载时，系统会重复保存正文、分块、生成向量并抽取事实；来源可信程度则被压缩成一个无法解释的浮点数。完成本计划后，运营人员可以给信息来源分级，系统会在昂贵的向量化和大模型调用之前识别完全重复或轻度改写的转载，只为一个稳定文档簇维护一份当前生效正文。后来采集到更可信、更完整的来源时，系统能够先构建新版本，再无中断地切换主文章。

用户还可以在治理工作台查看来源审核队列、重复候选的正文差异、主文章晋升记录和证据角色冲突。一个情报事实可以由多个独立来源共同支持或反驳，并明确显示为未验证、自述、已互证或有争议，而不再依赖一个综合可信度分数。

最终效果可以通过一个端到端场景观察：输入两篇 URL 不同但正文相同的文章和一篇同事件的独立报道，运行 Pipeline 后前两篇应属于同一文档簇且只产生一组 chunks 和向量，第三篇应保留为独立文档簇；清空 Redis 后再次处理，结论必须不变；加入第二个合格独立证据后，对应 Intel Fact 的验证状态应从 `unverified` 或 `self_reported` 变为 `corroborated`。

## Progress

- [x] (2026-07-12 00:00+08:00) 阅读根目录 `PLANS.md`、`AGENTS.md`、目标设计、领域术语表、ADR 和当前 Pipeline/Intel 模型，形成自包含 ExecPlan。
- [x] (2026-07-12 01:10+08:00) 建立来源档案、稳定文档簇、来源实例和文档版本的数据模型、migration、Protocol 与来源档案 PostgreSQL Store。
- [x] (2026-07-12 01:20+08:00) 实现来源准入，并以 `source_governance_enabled` 特性开关接入采集 Pipeline。
- [x] (2026-07-12 01:25+08:00) 实现版本化正文正规化、SHA-256、SimHash、两套 band 索引和 shingle 复核核心；已加入纯算法与去重判定测试。
- [x] (2026-07-12 02:10+08:00) 实现独立 `document_clusters`、PostgreSQL advisory transaction lock 权威归簇、URL/哈希幂等复查及 Redis 可重建热点索引核心；缓存异常统一降级为 miss。
- [x] (2026-07-12 02:25+08:00) 实现 `DocumentVersionService` 的 building/active/failed 状态机、事务内版本号分配和 active pointer 原子切换核心。
- [x] (2026-07-12 03:30+08:00) Pipeline 已消费 PostgreSQL 权威归簇结果：新簇或未完成构建的簇进入 SourceDocument、分块、向量和事实链路，已完成的 `duplicate/unchanged` 仅保留 occurrence；Celery 与 CLI 已完成治理/归簇服务装配，并删除 URL UUID 保存旁路。
- [ ] 启用 PostgreSQL 并发归簇、Redis 热点索引、正式去重、对账和隔离清理。
- [ ] 实现 Canonical Article 选择、派生数据版本化构建和 active version 原子切换。
- [ ] 将 Intel Fact 改为全局事实，实现多 Evidence Reference、Evidence Role 和 Verification Status。
- [x] (2026-07-12 15:30+08:00) 删除 Intel Fact 的单文档归属与相关 API/Agent/Store 旧路径；assertion key 改为来源无关的统一算法，来源筛选经 Evidence Reference 完成，验证状态与理由可完整持久化和返回。
- [ ] 接入检索来源先验、治理 API 与 Vue 工作台，并移除旧 URL 文档身份和 `source_reliability` 路径。
- [ ] 完成全量测试、端到端演练、缓存重建演练、文档同步和生产启用验收。

## Surprises & Discoveries

- Observation: 当前 `services/pipeline_service.py::_article_to_document` 使用 URL 的 UUID5 直接生成 `SourceDocument.document_id`，而 `content_hash` 仅被保存，没有参与入库判重。
  Evidence: 该函数先构造 `source_key = article.url ...`，再调用 `uuid5(NAMESPACE_URL, source_key)`；随后才计算 SHA-256。

- Observation: 当前事实模型仍把事实绑定到单篇文档，并公开 `source_reliability`。
  Evidence: `models/intel.py::IntelFact` 要求 `source_document_id`，同时包含 `source_reliability`；`services/intel_service.py` 和 `delivery/api/intel_router.py` 均读写这两个字段。

- Observation: `4 × 16-bit` 分段不能完整召回汉明距离 4–6 的候选。
  Evidence: 64 位指纹被分成四段时，距离不超过 3 才能保证至少一段完全不变。增加 `8 × 8-bit` 后，距离不超过 6 可保证至少两段完全不变，因此灰区检索必须维护第二套索引并要求至少两个 8 位 band 命中。

- Observation: 工作树在撰写计划前已有与本计划无关的修改。
  Evidence: `git diff --stat` 显示配置、服务、生成数据库文档等多个文件已有变更。实施者不得回退这些用户修改，应只处理与当前里程碑相关的文件。

- Observation: 64 位 SimHash 是无符号值，而 PostgreSQL `BIGINT` 是有符号值。
  Evidence: 指纹最高位为 1 时直接写入会溢出；Store 现在在持久化边界执行二补数有符号转换，读取时恢复无符号值。

- Observation: 本轮 Docker daemon 查询超时，无法运行 PostgreSQL、Redis 和 Qdrant 集成验收。
  Evidence: `docker info --format '{{.ServerVersion}}'` 在 14 秒后超时；本轮仅记录纯 Python 测试与静态编译结果，不宣称基础设施验收通过。

- Observation: Intel Service 与 Evidence Verification Service 曾各自实现 assertion key，且字段顺序不同。
  Evidence: 审查发现两者分别使用 `fact_type|subject|...` 和 `subject|fact_type|...`；现已统一委托给 `EvidenceVerificationService.assertion_key()`。

- Observation: 全局 Fact 按来源文档过滤不能再读取 Fact 自身字段。
  Evidence: `CompetitorService.auto_link_facts()` 已改为通过 Evidence Reference 判断来源；当前实现仍有 1000 条上限和 N+1 查询，后续应下沉为 Intel Store 的 SQL evidence join。

## Decision Log

- Decision: 用稳定的 Document Cluster 作为知识文档身份，URL 只标识 Source Occurrence。
  Rationale: 同一内容可以在多个 URL 出现，而簇身份必须在主来源晋升和 URL 变更时保持稳定。这也落实 `docs/adr/0001-stable-document-clusters-and-source-occurrences.md` 的已接受决策。
  Date/Author: 2026-07-12 / Codex

- Decision: PostgreSQL 是去重、评级、版本和证据状态的唯一权威存储；Redis 只做可重建加速。
  Rationale: 缓存淘汰或 Redis 故障只能让处理变慢，不能改变归簇结论或丢失审计数据。
  Date/Author: 2026-07-12 / Codex

- Decision: 同时维护 `4 × 16-bit` 高精度 band 和 `8 × 8-bit` 灰区 band。
  Rationale: 前者保证召回汉明距离 0–3 的候选，后者补齐距离 4–6 的召回保证。两套召回结果取并集后仍要计算完整汉明距离和正文 shingle 重合，band 命中本身不是合并结论。
  Date/Author: 2026-07-12 / Codex

- Decision: 先影子记录判定和人工标注，再启用自动归簇与正文清理。
  Rationale: 去重必须精确率优先；同一事件的独立报道被误合并会破坏多来源验证，风险高于漏掉一篇转载。
  Date/Author: 2026-07-12 / Codex

- Decision: Canonical Article 晋升采用新版本完整构建后再切换 active pointer，不原地覆盖正文。
  Rationale: Qdrant、PostgreSQL 全文索引、chunks 和事实抽取跨多个存储，原地覆盖会产生检索空窗和新旧派生数据混读。
  Date/Author: 2026-07-12 / Codex

- Decision: Intel Fact 成为全局对象，编辑状态与验证状态分开。
  Rationale: `draft/active/rejected/archived` 表示编辑工作流，`unverified/self_reported/corroborated/disputed` 表示证据情况，两者不能互相替代。
  Date/Author: 2026-07-12 / Codex

- Decision: 不迁移旧的文档级 fact identity，migration 直接清空可重建 facts 后删除 `dedupe_key` 和 `source_document_id`。
  Rationale: 旧 assertion key 包含来源文档身份，重命名会把错误语义带入全局事实；计划已允许从来源文档重新抽取旧 facts，并明确禁止保留兼容路径。
  Date/Author: 2026-07-12 / Codex

## Outcomes & Retrospective

当前只完成了计划撰写，尚未实现功能。实施完成后，本节必须按里程碑记录实际交付、未完成项、测试结果、性能数据和阈值校准结论，并将结果与 Purpose 中的端到端场景逐项比较。不能仅写“代码已合入”。

实施记录（2026-07-12）：已完成来源治理与去重算法的第一批实现，新增 `migrations/006_source_governance.sql`、`migrations/007_global_intel_facts.sql`，并通过 `python -m pytest tests/test_document_fingerprints.py tests/test_document_dedup_service.py tests/test_pipeline_service.py -q`（8 passed）。PostgreSQL/Qdrant 并发归簇、版本原子切换、治理 API/前端和全量证据迁移尚未完成，不能据此开启自动正文清理。

实施记录（2026-07-12 02:30+08:00）：新增 PostgreSQL 去重 Store、Redis 去重缓存、归簇协调服务和文档版本状态机。`python -m pytest tests/test_document_version_service.py tests/test_document_clustering_service.py tests/test_dedup_cache.py tests/test_document_dedup_store.py tests/test_document_fingerprints.py tests/test_document_dedup_service.py tests/test_pipeline_service.py -q` 结果为 14 passed；`python -m compileall models services infrastructure core -q` 与 `git diff --check` 通过。Docker daemon 无响应，尚未完成 migration、并发 worker、Redis 清空重建和 Qdrant 版本过滤演练；Pipeline 正式消费归簇结果、对账任务和隔离清理仍待实现。

实施记录（2026-07-12 03:30+08:00）：Pipeline 正式归簇分流已接通，权威重复稿不会再次保存 SourceDocument、分块、向量化或抽取 facts，新增稳定 cluster ID、URL 正规化和未完成构建重放测试。构建需求由 PostgreSQL 中 `source_documents.parse_status` 恢复，不再只依赖一次性的 `new_cluster` 返回值；`fetch_and_store()` 和关闭自动归簇时的 URL UUID 保存旁路已删除。相关回归为 26 passed、4 skipped。全量测试为 266 passed、8 skipped、25 failed；其中 24 项因当前工作树缺少 `evals` 包，1 项为既有 embedding mock 不接受 `http_client` 参数，均与本里程碑无关。事务内近重复正文复核、Document Version 派生数据版本化、对账和清理仍未完成，不能开启自动正文清理。

实施记录（2026-07-12 15:30+08:00）：完成全局 Intel Fact 身份切流，模型、PostgreSQL Store、Intel Service、API、Agent 创建工具和竞品序列化均删除 Fact 自身的 `source_document_id`；来源仍由 Evidence Reference 审计。统一 assertion key 算法并补齐 verification status/reason 往返。聚焦回归为 23 passed，相关扩展回归为 18 passed、4 skipped，`compileall` 与 `git diff --check` 通过；全量为 268 passed、8 skipped、25 failed，失败集合仍为缺失 `evals` 包的 24 项及既有 embedding mock 的 1 项。候选事实的 equivalent/supports/contradicts/unrelated 分类、Evidence Role 规则、状态自动重算和 SQL evidence join 尚未完成，因此 Milestone 5 保持未完成。

代码审查记录（2026-07-12 03:00+08:00）：修复 `intel_facts` INSERT 占位符数量错误、Redis 更新异常越过 best-effort 边界、同簇多条 independent evidence 被重复计数三个问题；事实 API 和 Store 已删除 `source_reliability` 并统一使用 `assertion_key`。相关回归命令结果为 29 passed。审查仍确认四个未完成 P1：Pipeline 未按权威归簇结果分流、事务内尚未完成近重复 band 复查、派生对象尚未携带 `document_version_id`、全局 fact 仍保留 `source_document_id` 归属。这些项目不得在后续实施中以兼容旧字段方式绕过。

## Context and Orientation

InsightForge 是 Python 3.11+ FastAPI 后端和 Vue 3 前端组成的竞品分析系统。PostgreSQL 保存权威文档元数据、父 chunks、全文索引、事实和审计数据；Qdrant 保存子 chunk 向量与 payload；Redis 支持 Celery、执行期锁和缓存。依赖方向必须保持 Delivery -> Agent/Tools -> Services -> Infrastructure，基础设施通过 `core/protocols.py` 中的 Protocol 暴露能力，`models/` 中的 dataclass 不执行 I/O。

当前采集入口是 `services/pipeline_service.py::PipelineService.run`。它从 RSS 和网页抓取文章，经 `infrastructure/markdown_converter.py` 转成 Markdown并过滤低质量页面，然后把每篇文章变成 `models/document.py::SourceDocument`，保存后立即分块、向量化并调用 `services/intel_service.py` 抽取事实。`services/document_ingestion_service.py` 处理上传等其他长期知识文档入口；它也必须最终使用同一套来源准入、文档版本和去重服务，不能形成旁路。

本计划使用以下统一领域语言。Source Profile 是一个信息来源的受治理档案，通常以规范化域名识别，包含来源类型、等级和评级历史。Source Tier 是 A、B、C、D 或 unknown 的离散等级，只描述来源基础属性，不代表某条事实已经被验证。Source Occurrence 是一篇内容在一个来源 URL 上的一次具体发布或抓取观测。Document Cluster 是完全重复或高度重合的 Source Occurrence 组成的内容族；同一事件的独立报道不是同一簇。Canonical Article 是簇内当前作为主文章的 Source Occurrence。Document Version 是某个主文章正文的一次可生效版本。Duplicate Candidate 是被指纹召回但尚未确定是否归簇的一对来源实例。

Intel Fact 是独立于单篇文档的规范化事实。Evidence Reference 是事实到具体 Document Version、Source Occurrence 和原文片段的可审计引用。Evidence Role 表示证据相对于某个事实的语境，可为 `primary`、`independent`、`interested_claim`、`community_report`、`aggregator` 或 `unknown`。Verification Status 表示事实的证据验证结果，可为 `unverified`、`self_reported`、`corroborated` 或 `disputed`。

设计依据位于 `docs/design-docs/source-governance-and-deduplication.md`，统一术语位于 `CONTEXT.md`，已接受架构决策位于 `docs/adr/0001-stable-document-clusters-and-source-occurrences.md`。这些文件是实现的约束来源，但本计划已经包含执行所需的关键结论。

## Plan of Work

### Milestone 1: 建立权威模型与来源准入

先创建只表达数据、不执行 I/O 的领域模型。建议在 `models/source_governance.py` 定义 `SourceProfile`、`SourceProfileRevision`、`SourceTier` 和 `SourceKind`，在 `models/document_governance.py` 定义 `DocumentCluster`、`SourceOccurrence`、`DocumentVersion`、`DuplicateCandidate` 和 `DedupDecision`。如果实施时发现拆分会与现有模型循环依赖，可以将文档治理类型并入 `models/document.py`，但必须在 Decision Log 记录原因。

新增下一编号的 SQL migration。创建来源档案与修订、来源实例、文档版本、重复候选、band 索引和治理审计所需表。保留 `source_documents` 表名作为稳定 Document Cluster 的数据库身份，逐步移走 URL 和正文语义。Source Occurrence 的规范化 URL 必须唯一；每个簇最多一个 active version；所有 band 记录必须携带算法版本；每个人工操作必须保存 actor、reason、before 和 after。旧数据允许在切流时清理重建，不实现复杂回填。

在 `core/protocols.py` 增加窄接口 `SourceProfileStoreProtocol` 和 `DocumentDedupStoreProtocol`，在 `infrastructure/` 增加 PostgreSQL 实现，在 `core/factory.py` 增加工厂。不要把治理操作继续塞入现有 `DocumentStoreProtocol`。创建 `services/source_governance_service.py`，实现域名规范化、精确域名查找、显式子域继承、准入和评级修订。A/B/C 来源可进入正式知识链路；D 来源隔离且正文最多保留七天；unknown 进入 `pending_review`，不得写 Qdrant、全文索引或 facts。每个 occurrence 保存入库时的 Source Profile revision、tier 和 source kind 快照，后来重新评级不得修改历史快照。

先为模型、migration、Store 和 Service 添加测试，再在 `PipelineService` 中插入 admission gate。使用特性开关使未启用环境仍可运行旧链路。里程碑结束时，A/B/C/D/unknown 的准入结果可由测试和 API 观察，D/unknown 进入索引或事实抽取的计数必须为零。

### Milestone 2: 影子运行两阶段近重复检测

创建一个无 I/O 的指纹模块和 `services/document_dedup_service.py`。正文正规化要移除 Markdown 格式符、链接目标、重复空白和已知公共模板，但保留用户可见文字；中文生成字符 3-gram，英文生成单词 3-shingle，混合文本合并两类特征。保存 `normalization_version`、`simhash_version` 和 `shingle_version`，使历史决定可以重放。

每篇正文先计算 SHA-256，再计算 64 位 SimHash。把 SimHash 同时分成四个 16 位 band 和八个 8 位 band。高精度候选由任一 16 位 band 相同召回；灰区候选要求至少两个 8 位 band 相同。候选并集去重后计算完整汉明距离，只对距离 0–6 的候选计算正文 shingle Jaccard、containment、正文长度比例和标题相似度。SHA-256 相同可直接视为完全重复；其他候选必须经过正文重合条件。短文本不自动近重复合并，发布时间差只能作为解释信号，不能作为硬时间窗口。

这一里程碑只记录 `DuplicateCandidate` 和建议，不改变现有簇、不删除正文、不减少向量化。建立人工标注样本，至少包含完全重复、换标题转载、删减少量段落、模板变化、跨月转载、短文本、中文、英文、混合文本和同一事件独立报道。自动合并建议精确率达到 98% 且完全重复识别率达到 100% 前，不得进入 Milestone 3。

### Milestone 3: 启用并发归簇与可重建 Redis 索引

在 `DocumentDedupStoreProtocol` 的 PostgreSQL 实现中提供全历史 band 查询和短事务归簇。高精度路径按稳定顺序获取由 16 位 band 派生的 PostgreSQL advisory transaction locks，然后在同一事务内重新查询候选、创建或选择 Document Cluster、写入 Source Occurrence、band 和审计记录。唯一约束是最后一道并发保护。灰区 band 用于发现和对账，不把 Redis 锁当作正确性边界。

增加 `DedupCacheProtocol` 及 Redis 实现，保存规范化 URL 幂等缓存、`content_hash -> document_id` 热点映射、带算法版本的 band 集合和 Source Profile 域名缓存。处理时可先查 Redis，但缓存 miss、异常或不完整结果必须查询 PostgreSQL。数据库事务提交后 best-effort 更新 Redis；更新失败不回滚权威结论。

让 Pipeline 消费 `DedupDecision`，其结果至少包括 `new_cluster`、`duplicate`、`review_required`、`canonical_promoted`、`quarantined` 和 `unchanged`。只有 `new_cluster` 进入首次版本构建；`duplicate` 只保存 occurrence；`review_required` 进入治理队列；`quarantined` 不进入知识索引。增加 Celery 重复簇对账、Redis 索引重建和 D 级正文清理任务，全部使用稳定幂等键。并发相同输入只能产生一个权威簇；即使短暂产生异常簇，对账也必须稳定收敛。

### Milestone 4: 构建和原子切换 Canonical Article

创建 `services/document_version_service.py`。Canonical 候选先满足正文和抽取质量底线，再按 Source Tier、正文完整度、发布时间更早、保持当前主文章的顺序比较。更高等级候选正文不足当前正文长度 70% 时，不自动晋升，只产生治理候选。

晋升时先创建 `building` 状态的下一 Document Version。修改 parent chunks、Qdrant point payload、PostgreSQL point 状态和 Evidence Reference，使所有派生对象携带 `document_version_id`。以 version ID 作为幂等命名空间生成 chunks、向量、全文索引和事实候选。全部构建并校验成功后，在一个 PostgreSQL 事务中把新版本设为 active、旧版本设为 superseded，并更新簇的 `active_version_id`。查询层始终过滤 active version，因此提交前继续读旧版本，提交后一次性读新版本。

构建失败时把新版本标记为 failed，旧版本保持 active。事务成功后异步删除旧 Qdrant points 和无需永久保存的旧正文；清理失败可以安全重试，不影响当前服务。版本构建任务用 `document_id + target_version` 作为幂等键。

### Milestone 5: 将事实改为全局对象并验证多份证据

在 `models/intel.py` 中让 `IntelFact` 不再强制属于单个 `source_document_id`，删除业务层对 `source_reliability` 的使用，增加稳定且版本化的 `assertion_key`、`verification_status` 和验证理由。先用兼容 migration 允许旧字段与新字段并存，切换所有调用后再删除旧字段。更新 `infrastructure/intel_store.py`、`services/intel_service.py`、`delivery/api/intel_router.py`、竞品聚合、Agent 工具和报告引用。

创建 `EvidenceVerificationStoreProtocol` 和 `services/evidence_verification_service.py`。用主体、fact type、谓词、对象和事件日期构造规范化 assertion key，先召回可能相同的全局事实。结构化抽取 LLM 只能在候选范围内返回 `equivalent`、`supports`、`contradicts` 或 `unrelated`，同时返回原文引用、理由、模型和 Prompt 版本。输出不完整或规则冲突时进入人工复核，不自动归并。

Evidence Role 使用“LLM 提议、确定性规则校验、冲突降级、人工覆盖”。代码根据域名归属、source kind、竞品关系和文档簇关系限制角色：社区来源不能成为官方 primary，聚合站不能成为独立原始调查。人工覆盖必须记录原因。验证状态按独立 Document Cluster 计数，同簇多个 occurrence 只算一个来源；单个 C 级证据不能产生 `corroborated`；主要由主体自身陈述时为 `self_reported`；存在实质反证时为 `disputed`。验证状态变化不得自动把编辑状态从 draft 改成 active。

### Milestone 6: 完成检索排序、治理界面和全面切流

保持现有向量、关键词、RRF 和可选 reranker 的相关性计算顺序，在其后应用 Source Tier 先验：A 为 1.00，B 为 0.95，C 为 0.85。需要返回 `top_k` 条结果时先至少召回 `top_k * 3`，加权后再截断。D、unknown 和非 active version 必须在查询过滤层排除。这个权重只影响排序，不能替代 Verification Status 或报告质量门禁。

新增 `/api/governance` 路由组，提供 Source Profile CRUD、修订历史、unknown 审核队列、批量评级、Duplicate Candidate 详情、正文 diff、`merge`、`keep_separate`、Document Cluster/occurrence/version 查看、`promote_source` 和 Evidence Role 人工覆盖。所有写操作沿用现有 RBAC，并保存操作者、理由、时间和前后值。

在 Vue 前端增加治理工作台，至少有 Sources、Duplicates 和 Evidence 三个标签视图。重复详情必须同时展示标题、来源等级、发布时间、正文差异、汉明距离、shingle 重合度和判定理由。来源评级可批量处理，簇合并、保持独立和晋升默认逐条确认并要求理由。页面要覆盖空状态、加载、失败、分页和长文本布局。

影子与生产指标达到验收门槛后，清空允许重建的旧知识数据，按新模型重新采集。最后删除 URL 派生 document ID、fact 单文档归属和 `source_reliability` 兼容路径，更新 `docs/generated/db-schema.md`、API 参考、设计索引和运维 runbook。

## Concrete Steps

所有命令都从仓库根目录 `D:\study\Logos` 运行。开始每个里程碑前先确认工作树，避免覆盖用户已有修改：

    git status --short
    git diff -- docs/exec-plans/source-governance-and-deduplication-implementation-plan.md

先运行相关基线测试，确认失败不是本次修改引入：

    python -m pytest tests/test_pipeline_service.py tests/test_document_ingestion_service.py tests/test_intel_models.py tests/test_intel_schema_and_stores.py tests/test_phase2_services.py -q

Milestone 1 完成后运行模型、Store、migration 和 Pipeline 准入测试。新测试文件名应清楚表达职责，建议为 `tests/test_source_governance_models.py`、`tests/test_source_profile_store.py`、`tests/test_source_governance_service.py` 和 `tests/test_source_admission_pipeline.py`：

    python -m pytest tests/test_source_governance_models.py tests/test_source_profile_store.py tests/test_source_governance_service.py tests/test_source_admission_pipeline.py -q

Milestone 2 完成后运行纯算法和影子判定测试：

    python -m pytest tests/test_document_fingerprints.py tests/test_document_dedup_service.py tests/test_dedup_shadow_pipeline.py -q

测试必须随机或枚举验证两条数学性质：汉明距离 0–3 时至少一个 16 位 band 相同；汉明距离 0–6 时至少两个 8 位 band 相同。还要包含一个距离 4–6 且变更分散在四个 16 位 band 中的样本，证明它会被 8 位灰区索引召回。

Milestone 3 和 4 需要 PostgreSQL、Redis 和 Qdrant。启动基础设施并应用 migration：

    docker compose up -d postgres redis qdrant
    python migrations/apply_migrations.py

然后运行去重 Store、并发和版本切换集成测试：

    python -m pytest tests/test_document_dedup_store.py tests/test_dedup_cache.py tests/test_dedup_concurrency.py tests/test_document_version_service.py -q

Milestone 5 完成后运行事实与证据测试：

    python -m pytest tests/test_intel_models.py tests/test_intel_schema_and_stores.py tests/test_phase2_services.py tests/test_evidence_verification_service.py tests/test_intel_router.py tests/test_competitor_router_phase2.py tests/test_report_service_workflow.py -q

Milestone 6 完成后构建前端并运行后端全量测试：

    pnpm --dir frontend build
    python -m pytest tests/ -q

启动应用进行人工端到端验证：

    python -m delivery.server

后端默认监听 `http://localhost:8005`。使用治理 API 创建 A/B/C/unknown 来源档案，投递固定夹具文章，随后在前端治理工作台观察簇、occurrences、版本、重复候选和证据状态。每次实际命令、测试数量、耗时和关键输出都要补记到本文件的 Progress 或 Artifacts and Notes，不能保留未经执行的“预计通过”描述。

## Validation and Acceptance

来源准入的可观察验收是：A、B、C 来源文章能进入正式知识处理；unknown 出现在待审核队列；D 出现在隔离列表；查询 PostgreSQL point 状态、Qdrant 和 facts 时，D/unknown 数量均为零。修改 Source Profile 等级后，已有 occurrence 的 tier revision 快照保持不变。

去重的可观察验收是：完全相同正文即使 URL、标题和采集时间不同，也只生成一个 Document Cluster 和一组 active chunks/points；轻度删改稿在校准阈值内归入同簇；同事件的独立报道保持独立。完全重复识别率必须为 100%，人工标注集上的自动近重复合并精确率必须至少为 98%，独立报道误合并率应接近零。

并发和缓存验收是：多个 Worker 同时摄入相同内容时只留下一个权威簇和幂等 occurrence。清空全部 dedup Redis keys 后重跑相同输入，簇结论不变；执行重建任务后 Redis 热点索引恢复。Redis 不可用时系统可以变慢或记录降级日志，但不得丢失来源实例或产生不同结论。

版本验收是：更高等级且正文不少于当前正文 70% 的来源可以触发晋升；building 期间查询仍返回旧 active version；构建成功后一次性返回新版本；模拟 Qdrant 写入或事实抽取失败时旧版本仍可检索；重复执行晋升与清理任务不会生成重复 chunks、points 或 Evidence Reference。

证据验收是：同一簇的多个转载只算一个证据来源；单个 C 级证据不能令 fact 变为 corroborated；两个合格独立簇支持同一事实时可以变为 corroborated；有效反证使状态变为 disputed；来源主体自己的声明显示 self_reported；所有状态变化都有解释，且不会自动改变 draft/active 编辑状态。

治理界面验收是：管理员能完成来源评级、查看修订历史、比较重复正文、选择 merge 或 keep separate、晋升来源和覆盖 Evidence Role。每次操作都要求理由并能在审计记录中看到 actor、时间和前后值。普通 viewer 只能查看，不能执行治理写操作。

正式启用前还必须观察抓取数、准入数、隔离数、新簇数、完全重复数、近重复数、灰区数、人工推翻率、候选查询延迟、band 热点、锁等待、Redis 命中率、晋升失败数和各 Verification Status 分布。没有这些指标或指标无法解释时，不得开启自动正文删除。

## Idempotence and Recovery

所有 migration 使用现有 `migrations/apply_migrations.py` 管理，不手工修改生产表。执行前备份 PostgreSQL；旧文档数据允许清理重建，但来源档案、评级修订、occurrence 元数据、人工判定和审计记录不得删除。清理脚本必须先提供 dry-run 输出待删除数量，再由管理员显式执行。

Source Occurrence 依靠规范化 URL 唯一约束幂等；版本构建依靠 `document_id + target_version` 幂等；Evidence Reference 依靠 fact、version、occurrence 和片段身份组成的唯一键幂等；Celery 重试必须复用这些键。数据库事务提交前不更新 Redis，提交后缓存更新失败可以重试。

发布开关至少独立控制来源准入、影子去重、自动归簇、Canonical 晋升、全局 fact 和 tier 排序。自动归簇异常时退回 shadow-only，保留已写审计；晋升异常时停止新 building version，继续服务旧 active version；Redis 异常时回退 PostgreSQL；证据模型异常时把事实留在 unverified 或人工复核，不自动激活。

Qdrant 不是文档版本的权威存储。如果 active 切换前构建失败，按 version ID 删除未生效 points 后重试。如果 active 切换后旧 points 清理失败，保留它们并重试后台清理，因为查询过滤 active version 后不会读到它们。严禁用 `git reset --hard` 或回退用户已有修改来恢复工作区。

## Artifacts and Notes

实现时在此保留简短证据，包括最终 migration 编号、关键测试输出、影子标注集规模、precision 结果、并发演练结果和 Redis 清空重建结果。输出示例应保持短小，例如：

    2026-07-12 focused unit tests: 14 passed in 1.30s
    compileall: passed
    docker integration: blocked by daemon timeout

    dedup labeled samples: 500
    exact duplicate recall: 100.0%
    automatic merge precision: 98.6%
    independent-report false merges: 0
    redis rebuild: 12480 band entries restored

快速查找目标设计时，可在 `docs/design-docs/source-governance-and-deduplication.md` 使用以下关键词。搜索 `Source Profile`、`SourceProfileRevision`、`inherit_to_subdomains` 可找到来源字段、修订和子域继承；搜索 `Source Tier`、`pending_review`、`unknown` 可找到准入路径；搜索 `Document Cluster`、`Source Occurrence`、`source_document_versions`、`duplicate_candidates` 可找到持久化语义。

搜索 `正规化与特征`、`字符 3-gram`、`单词 3-shingle` 可找到指纹输入；搜索 `4 x 16-bit`、`不超过 3` 可找到高精度召回保证；搜索 `8 x 8-bit`、`至少两个 8 位 band`、`4-6` 可找到灰区修正；搜索 `全历史候选检索` 可找到无时间窗口要求；搜索 `同 URL 更新`、`url_reused`、`versioned_content` 可找到重抓分支。

搜索 `Canonical Article 选择与晋升`、`70%` 可找到晋升规则；搜索 `building`、`active_version`、`原子切换` 可找到版本流程；搜索 `Redis 与 PostgreSQL 的职责`、`advisory transaction locks` 可找到并发与存储边界；搜索 `全局 Intel Fact`、`assertion_key` 可找到事实归并；搜索 `Evidence Role 分类`、`确定性规则校验` 和 `Verification Status` 可找到证据验证；搜索 `top_k * 3` 和 `final_score` 可找到检索降权；搜索 `治理 API 与界面`、`可观测性与验收`、`分阶段交付` 可找到运营与发布门槛。

在 `CONTEXT.md` 中搜索英文领域术语可以确认统一定义和必须避免的旧称。在 `docs/adr/0001-stable-document-clusters-and-source-occurrences.md` 搜索 `Consequences`、`URL` 和 `active`，可以快速确认稳定簇、单一生效版本、PostgreSQL 权威和无需兼容回填四项架构约束。

## Interfaces and Dependencies

实现结束时，`core/protocols.py` 中应存在以下职责明确的 Protocol。实际参数可根据现有 Store 风格补充分页和事务上下文，但不得合并成一个宽泛治理接口：

    class SourceProfileStoreProtocol(Protocol):
        def resolve_domain(self, domain: str) -> SourceProfile | None: ...
        def save_profile(self, profile: SourceProfile, *, actor: str, reason: str) -> SourceProfile: ...
        def list_revisions(self, profile_id: str) -> list[SourceProfileRevision]: ...

    class DocumentDedupStoreProtocol(Protocol):
        def find_exact(self, content_hash: str) -> list[SourceOccurrence]: ...
        def find_by_bands(self, fingerprint: SimHashFingerprint) -> list[SourceOccurrence]: ...
        def commit_decision(self, decision: DedupDecision) -> DedupDecision: ...
        def get_active_version(self, document_id: str) -> DocumentVersion | None: ...
        def activate_version(self, document_id: str, version_id: str) -> DocumentVersion: ...

    class DedupCacheProtocol(Protocol):
        def find_exact(self, content_hash: str) -> list[str]: ...
        def find_by_bands(self, fingerprint: SimHashFingerprint) -> list[str]: ...
        def index_occurrence(self, occurrence: SourceOccurrence) -> None: ...
        def rebuild(self) -> int: ...

    class EvidenceVerificationStoreProtocol(Protocol):
        def find_fact_candidates(self, assertion_key: str) -> list[IntelFact]: ...
        def save_evidence(self, evidence: EvidenceReference) -> EvidenceReference: ...
        def update_verification(self, fact_id: str, status: VerificationStatus, reason: str) -> IntelFact: ...

`DocumentDedupService` 必须能在不连接数据库的情况下对正文计算特征并给候选打出决策建议。`DocumentDedupStoreProtocol` 的 PostgreSQL 实现负责锁、事务内复查和权威落库。`DocumentVersionService` 负责 building/active/superseded/failed 状态机。`EvidenceVerificationService` 负责 assertion key、证据角色规则和验证状态，不负责把 draft fact 激活。

本计划不要求引入新的第三方去重库。优先用 Python 标准库实现 SHA-256、bit 操作和集合相似度，避免为少量稳定算法增加运行依赖。如果评估后确需引入 SimHash 库，必须先在 Decision Log 记录其算法稳定性、中文 token 支持、版本固定和迁移影响。

---

Revision note (2026-07-12): 按仓库根目录 `PLANS.md` 的 ExecPlan 规范整体重写。新增强制 living-plan 章节、面向新执行者的领域与仓库说明、叙事式里程碑、精确命令、可观察验收、幂等恢复、接口草案和修订记录；保留来源治理、双 SimHash band、原子版本切换、全局 fact、多证据验证及设计关键词导航的原始范围。
