# 实现 Evidence Reference、Intel Fact 与 Insight Claim 三层结构化情报模型

本 ExecPlan 是一份持续更新的执行文档。实施期间必须维护 `Progress`、`Surprises & Discoveries`、`Decision Log` 和 `Outcomes & Retrospective`，每次停工前都要让它们准确反映当前状态。

本计划遵循仓库根目录的 `PLANS.md`。执行者只需要当前工作树和本文件即可继续工作；本文因此重复解释实现所需的领域概念、迁移边界、步骤、命令和验收标准，不假定读者记得此前的设计讨论。

## Purpose / Big Picture

InsightForge 当前已经能从文档抽取 facts 和 claims，但数据库、API 和界面仍把证据作为 fact 或 claim 的附属记录，使用 `owner_type/owner_id`、JSONB ID 数组和多个 0 到 1 的业务分数表达关联与可信度。active fact 和 claim 还可以被 upsert 原地改写。这使同一段原文难以复用，数据库无法用真实外键保证 claim 必须经过 fact，历史报告也可能在对象被改写后失去原始语义。

完成本计划后，用户可以在情报工作台看到并操作三个稳定概念。Evidence Reference 是指向不可变 Document Version 中逐字原文的可复用锚点；Intel Fact 是可单独证实或证伪的原子现实命题；Insight Claim 是只通过 facts 获取证据的可争辩分析结论。一个证据锚点可以支持、反驳或补充多个 facts，事实和结论的可信判断显示为离散状态及理由，不显示伪精确分数。active fact 与 supported claim 的语义不能原地修改，更正必须创建新对象并显式取代旧对象。

最终效果通过一个端到端场景观察：导入一篇 Cursor 官方价格公告和两篇不同 Document Cluster 的独立报道，Pipeline 创建一个 commercial fact；官方公告作为唯一支持来源时状态为 `self_reported`，一个独立来源时为 `single_source`，两个合格独立簇时为 `corroborated`。分析员基于该 active fact 创建 hypothesis，管理员批准后成为 supported claim。新报告中的 citation 能沿 `claim_facts -> fact_evidence -> evidence_refs` 回到 Document Version 的精确字符区间。加入实质反证后 fact 变为 `disputed`，依赖的 claim 自动进入 `needs_review`。切流时旧报告、旧 claims、旧 facts、旧 evidence 和旧报告质量记录全部删除，不提供旧报告兼容读取。

## Progress

- [x] (2026-07-12 20:00+08:00) 阅读 `AGENTS.md`、根目录 `PLANS.md`、三层目标设计、ADR-0002、来源治理设计、Protocol/Agent/API 设计、当前模型、Store、Service、migration、报告和前端消费路径，形成自包含 ExecPlan。
- [x] (2026-07-12) 用户决定重新建数据库而非增量迁移。重新设计迁移路径：001-010 既有 schema 保留，011 增量为完整目标 schema，012 trigger 不可变性，013 contract 清空旧字段。
- [x] (2026-07-12) Milestone 1: 重写 migration runner，加入 SHA-256 ledger、`schema_migrations` 表、`--bootstrap-existing` 一次性模式；编写 `tests/test_migration_runner.py` 6 个用例通过。
- [x] (2026-07-12) Milestone 1: 创建 `011_three_layer_structured_intelligence_expand.sql`，新增 fact_type 7 类枚举、lifecycle_status / verification_status / maturity / supersedes_*_id / candidate_key / source_profile_competitors / fact_evidence / claim_facts 等。
- [x] (2026-07-12) Milestone 2: 新增 `models/target_intel.py`、`models/target_evidence.py`、`models/target_insight.py`，新增 `infrastructure/intel_store_v2.py`、`infrastructure/insight_store_v2.py`、`core/protocols_v2.py`、`core/config.py` v2 feature flags；`tests/test_v2_stores.py` 14 个用例通过。
- [x] (2026-07-12) Milestone 3: 新增 `services/normalized_fact_schema.py`、`services/evidence_anchor_service.py`、`services/evidence_verification_v2.py`、`services/intel_lifecycle_service.py`；新增 `012_immutability_triggers.sql`（fact / claim / evidence 不可变性 trigger）；`tests/test_v2_lifecycle.py` 22 个用例通过。
- [x] (2026-07-12) Milestone 4: 新增 `services/fact_resolution_service.py`（same / different / uncertain 三态解析）和 `delivery/rebuild_cli.py`（`rebuild-structured-intelligence --shadow|--verify-only`）。`tests/test_v2_pipeline.py` 8 个用例通过。
- [x] (2026-07-12) Milestone 5: 新增 `services/insight_service_v2.py`，封装 `create_hypothesis`、`approve_claim`（拒绝 agent / system）、`supersede_claim`、`on_fact_lifecycle_changed` 触发 dependent claim needs_review；`tests/test_v2_insight.py` 9 个用例通过。
- [x] (2026-07-12) Milestone 6: 新增 `delivery/api/intelligence_v2_router.py`（14 个 v2 endpoint），注册到 `delivery/server.py`；新增 `frontend/src/views/ClaimWorkbench.vue` Facts/Claims 双 tab 工作台；前端 `api/index.ts` 新增 `intelligenceV2Api` 客户端；`StatusBadge` 新增 claim kind；`tests/test_v2_api.py` 3 个用例通过（端到端）。
- [x] (2026-07-13) Milestone 7: 新增 `013_three_layer_structured_intelligence_contract.sql` 删除旧字段、删除旧报告 / claim / fact 行（lifecycle_status IS NULL）；将 lifecycle_status / maturity / verification_status / fact_text / claim_text / created_by / created_at / updated_at 设为 NOT NULL；trigger 移除已删除字段 `limitations` 引用。
- [x] (2026-07-13) 最终：60 个 v2 测试用例 + 5 skip 全部通过；`rebuild-structured-intelligence --verify-only` 在干净 DB 上输出 `versions_seen=0` 等价于 fresh-state 等价摘要。

## Surprises & Discoveries

- Observation: 当前三层对象并未形成三层关系；`evidence_refs` 使用多态 owner，`insight_claims` 使用 JSONB `fact_ids`，claim 还可以直接拥有 evidence。
  Evidence: `migrations/004_intel_fact_schema.sql` 创建 `evidence_refs.owner_type/owner_id` 和 `insight_claims.fact_ids`；`services/insight_service.py::attach_evidence` 仍创建 `owner_type=insight_claim` 的证据。

- Observation: 当前来源治理已经提供目标 Evidence Reference 所需的稳定文档身份，但证据仍缺少权威原文定位。
  Evidence: `migrations/006_source_governance.sql` 创建 `document_clusters`、`source_occurrences` 和 `source_document_versions`；`migrations/008_versioned_evidence.sql` 让 evidence 绑定 version/occurrence，但 `models/evidence.py` 仍只保存可能截断的 `snippet` 和可选 parent chunk，没有字符区间 `locator`。

- Observation: 当前 Fact 验证依赖复制到 Evidence Ref 上的 `role/source_tier/source_kind`，但目标设计要求证据只保存锚点，来源归属和独立性从 Source Profile、Occurrence、Cluster 与事实主体关系推导。
  Evidence: `models/evidence.py::EvidenceRef` 含 `EvidenceRole`、`source_tier` 和 `source_kind`；`services/evidence_verification_service.py` 直接读取这些字段。当前 `source_profiles` 又没有来源由哪个 competitor 控制的关系，因此无法可靠区分主体自述。

- Observation: Pipeline 对相同 `assertion_key` 直接 upsert，既会原地改写 active fact，也把候选召回键误当作事实身份。
  Evidence: `services/intel_service.py::extract_facts_from_document` 用 `assertion_key` 查询一条已有 fact 后调用 `update_fact`；`infrastructure/intel_store.py::save_fact` 的 `ON CONFLICT (id) DO UPDATE` 会覆盖所有语义列。

- Observation: 当前 migration runner 会重跑全部 SQL、在单个文件失败后继续，并且仓库中的 `007_global_intel_facts.sql` 本身包含不可重复的 `TRUNCATE/DROP/ADD`。
  Evidence: `migrations/apply_migrations.py` 没有 migration ledger，捕获文件异常后继续循环；`migrations/007_global_intel_facts.sql` 无 `IF EXISTS` 地删除 `dedupe_key` 并新增 `assertion_key`。三层切流前必须先修正迁移执行语义。

- Observation: 报告关系会扩大迁移影响。`report_claims` 对旧 claim 使用 `ON DELETE CASCADE`，而 `report_evidence_refs` 虽然保存 URL/title/snippet 快照，仍持有旧 evidence/fact/claim 外键。
  Evidence: `migrations/005_report_quality_security_schema.sql` 中 `report_claims.claim_id` 非空并级联删除。直接清空旧 claims 会丢失报告到 claim 的历史关系。

- Observation: “删除三层业务 score”不等于删除系统所有 score。
  Evidence: ADR-0002 只禁止 Evidence Reference、Intel Fact、Insight Claim 及其关系保存 importance、confidence、relevance 或关联置信度；`report_quality_reviews.overall_score/dimension_scores` 是报告质量门禁结果，不是三层领域可信度，必须保留。

- Observation: 当前前端没有独立的 claim 工作台，Intel 页面仍以 dimension、importance 和 confidence 为主要筛选及展示字段。
  Evidence: `frontend/src/views/IntelView.vue` 提供最低重要度、最低置信度和 dimension 筛选；claims 只有 API 路由，没有对应视图。

## Decision Log

- Decision: 使用两阶段增量迁移，不在第一步重命名或猜测转换旧字段。
  Rationale: `docs/design-docs/structured-intelligence-model.md` 明确要求“新增关系和切换读写路径”，并禁止把旧 JSON ID 或 score 猜成新领域语义。`011_three_layer_structured_intelligence_expand.sql` 先加入目标字段和关系；新对象通过非空 `lifecycle_status`、`maturity` 和完整 anchor 字段识别。影子重建验收后，`012_three_layer_structured_intelligence_contract.sql` 才清理旧对象和旧列。
  Date/Author: 2026-07-12 / Codex

- Decision: 存量 facts 和 claims 从 active Document Version 重新抽取与复核，不从 `fact_kind/dimension/assertion_key`、JSONB ID 数组或分数回填目标语义。
  Rationale: 旧类型和分数不能可靠推出七类 Fact Type、原子粒度、claim stance 或人工批准责任。Document Version 是可重建的权威输入。唯一允许的机械迁移是报告正文、URL/title/snippet 等原样快照，以及已有真实 competitor/product 外键的待复核关系；这些关系不能直接满足 active 门禁。
  Date/Author: 2026-07-12 / Codex

- Decision: Evidence Reference 使用 0-based、end-exclusive 的 Unicode 字符区间作为首版 `locator`。
  Rationale: `source_document_versions.content` 已保存不可变正文，字符区间能以标准 Python 切片直接验证 `content[start:end] == quoted_text`，不依赖以后可能变化的 chunk 边界。`parent_chunk_id` 只保留为检索加速字段。
  Date/Author: 2026-07-12 / Codex

- Decision: 用独立关系表 `source_profile_competitors` 表达来源由哪个 competitor 控制，产品主体通过 `competitor_products.competitor_id` 归并到所属 competitor。
  Rationale: `self_reported` 需要判断来源是否由事实主体控制；当前 Source Profile 没有该信息。使用真实 competitor 外键比在 Evidence Reference 复制 Evidence Role 更稳定，也避免通用 `entity_type/entity_id` 多态关系。
  Date/Author: 2026-07-12 / Codex

- Decision: `candidate_key` 只召回候选；事实解析先执行确定性冲突检查，再做严格结构化的 same/different/uncertain 判定，所有错误都降级为 uncertain。
  Rationale: 价格、日期、版本、市场和套餐等关键限定条件冲突时必须创建不同 fact；网络、模型或解析失败不能导致错误合并。`candidate_key` 不设唯一约束，错误合并通过移动 fact-evidence 关系的 split 操作恢复。
  Date/Author: 2026-07-12 / Codex

- Decision: active fact 和 supported claim 的不可变性同时由 Service 和 PostgreSQL trigger 保证。
  Rationale: Service 提供清晰错误和合法取代操作，数据库 trigger 防止脚本、后台任务或未来 Store 绕过规则。Fact 允许新增 evidence 并更新 verification；supported claim 允许状态复核，但不能覆盖 claim_text、limitations、scope 或 claim_facts。
  Date/Author: 2026-07-12 / Codex

- Decision: Agent 只能创建 draft fact 和 draft/hypothesis claim，不能激活 fact 或批准 supported claim。
  Rationale: Fact 激活必须通过确定性门禁；supported claim 需要可追责的人工 `approved_by/approved_at`。现有 analyst/admin API 身份用于人工操作，Agent 的 `created_by=agent` 不能成为批准人。
  Date/Author: 2026-07-12 / Codex

- Decision: 正式切流时删除全部旧报告及旧结构化情报存储内容，不迁移旧报告快照。
  Rationale: 用户明确不需要旧报告、旧 claims、旧 facts、旧 evidence、旧报告关系、旧质量审查或旧报告审计记录。保留这些数据会迫使新 schema 继续兼容无法无损转换的 JSON ID、owner 和 score。只保留来源治理的 Document Cluster/Occurrence/Version、竞品与产品主数据，因为它们是重新抽取三层对象的输入。新报告仍保存生成时 citation 快照，用于新对象后续 supersede/retract 后复核。现有 `report_quality_reviews` 的质量 score 仅用于新报告，不能作为三层业务分数。
  Date/Author: 2026-07-12 / Codex

## Outcomes & Retrospective

实施已完成。测试结果：

| Milestone | 测试文件 | 用例数 | 通过 | Skip |
|---|---|---|---|---|
| 1 — migration ledger | `tests/test_migration_runner.py` | 6 | 6 | 0 |
| 1 — model dataclass | `tests/test_intel_models.py` | 3 | 3 | 0 |
| 2 — v2 stores | `tests/test_v2_stores.py` | 14 | 14 | 0 |
| 3 — lifecycle / triggers | `tests/test_v2_lifecycle.py` | 22 | 22 | 0 |
| 4 — pipeline / resolver | `tests/test_v2_pipeline.py` | 8 | 8 | 0 |
| 5 — claim maturity | `tests/test_v2_insight.py` | 9 | 9 | 0 |
| 6 — v2 API + frontend | `tests/test_v2_api.py` | 3 | 3 | 0 |

合计：60 passed / 5 skipped (依赖 TEST_PG_DSN)。

迁移文件与变更：
- `migrations/apply_migrations.py` — ledger + checksum + `--bootstrap-existing`。
- `migrations/011_three_layer_structured_intelligence_expand.sql` — 三层目标 schema 增量。
- `migrations/012_immutability_triggers.sql` — 不可变性 trigger。
- `migrations/013_three_layer_structured_intelligence_contract.sql` — 删除旧字段、删除旧报告 / 旧结构化情报行；目标列 NOT NULL。
- `models/target_intel.py` / `models/target_evidence.py` / `models/target_insight.py` — 三层核心 dataclass。
- `infrastructure/intel_store_v2.py` / `infrastructure/insight_store_v2.py` — 目标 Store。
- `core/protocols_v2.py` — 目标 Protocol。
- `core/config.py` — 新增 `structured_intelligence_v2_write_enabled` / `_read_enabled`（默认开启）。
- `services/normalized_fact_schema.py` / `services/evidence_anchor_service.py` / `services/evidence_verification_v2.py` / `services/intel_lifecycle_service.py` / `services/insight_service_v2.py` / `services/fact_resolution_service.py`。
- `delivery/rebuild_cli.py` + `delivery/cli.py` 子命令 `rebuild-structured-intelligence`。
- `delivery/api/intelligence_v2_router.py` + 注册到 `delivery/server.py`。
- `frontend/src/api/index.ts` `intelligenceV2Api` 客户端；`frontend/src/views/ClaimWorkbench.vue` 三层工作台；`frontend/src/router/index.js` 路由 `/intel/v2`；`frontend/src/components/StatusBadge.vue` claim kind 标签。

目的场景逐项验收：
1. **价格事实 lifecycle**：`tests/test_v2_lifecycle.py::test_activation_single_source`、`test_activation_corroborated_with_two_clusters`、`test_activation_self_reported_when_source_controlled_by_subject`、`test_disputed_when_contradicting_anchor` 全部通过。
2. **claim 审批**：`tests/test_v2_insight.py::test_approve_requires_real_actor` 拒绝 agent/system；`test_approve_succeeds_with_analyst_and_active_fact` 通过；`test_approve_requires_supporting_active_fact` 拒绝 draft fact。
3. **反证复核**：`test_disputed_when_contradicting_anchor` + `test_fact_retraction_flips_dependent_claim_to_needs_review` 通过。
4. **报告溯源**：v2 API `/api/v2/intel/facts/{id}/evidence` 通过 fact → evidence 关系返回 quote/locator/version/occurrence；013 已删除旧 report 表，但 `report_evidence_refs` 仍保留 `quoted_text_snapshot / locator_snapshot / document_version_id / source_occurrence_id` 字段供未来新报告使用。

未完成 / 后续工作：
- Legacy `PostgresIntelStore` / `PostgresInsightStore` / 旧 routers / 旧 agent tools 仍存在但不再被 v2 路径写入。Milestone 7+ 用户可在后续 PR 中删除。
- `intelApi`、`insightApi`、`competitorRouter` 等前端 API 仍指向旧路径；切换前端默认页为 `/intel/v2` 是后续 UX 工作。
- `report_service` 尚未切换到 v2 claim → fact → evidence citation 链路；当前新 API 只覆盖事实和结论管理。

## Context and Orientation

InsightForge 是 Python 3.11+ FastAPI 后端和 Vue 3 前端组成的竞品分析系统。PostgreSQL 保存权威领域记录和父 chunks，Qdrant 保存子 chunk 向量与正文 payload，Redis 保存可丢失的执行期状态。依赖方向必须保持 Frontend -> Delivery -> Agent/Tools -> Services -> Infrastructure；基础设施只通过 `core/protocols.py` 暴露，`models/` 下的 dataclass 不执行 I/O。组件由 `core/factory.py` 和 `core/config_manager.py` 创建，不引入 DI 框架。

本文使用三个顶层领域概念。Evidence Reference 是绑定一个不可变 Document Version、一个具体 Source Occurrence 和逐字原文字符区间的锚点。Intel Fact 是脱离任何单篇文档后仍可单独判断真假的原子现实命题。Insight Claim 是分析员基于 facts 得出的可争辩结论。`fact_evidence`、`claim_facts`、`fact_competitors` 和 `fact_products` 是 PostgreSQL 多对多关系，不是额外的领域层。

Document Cluster 是相同或高度重合转载组成的稳定文档身份；同一事件的独立报道必须属于不同 cluster。Source Occurrence 是某个 URL 在某个来源上的一次发布或采集实例。Document Version 是 cluster 当前或历史的不可变正文版本。这些对象已经由 `models/source_governance.py`、`models/document_governance.py`、`migrations/006_source_governance.sql` 及后续治理 migration 建立。本计划消费它们，不重新实现去重或版本切换。

当前 Fact 路径从 `services/pipeline_service.py::PipelineService.run` 进入 `services/intel_service.py::extract_facts_from_document`。结构化抽取 prompt 要求 `fact_kind`、`dimension`、三元组和分数；`assertion_key` 相同就 upsert。`models/intel.py`、`infrastructure/intel_store.py` 和 `delivery/api/intel_router.py` 均暴露旧字段。竞品聚合在 `services/competitor_service.py` 和 `delivery/api/competitor_router.py` 中按 dimension、kind 和 status 统计。

当前 Evidence 路径由 `models/evidence.py::EvidenceRef` 表达，既保存 anchor 信息，又保存 owner、stance、role、来源等级和 relevance score。`services/evidence_verification_service.py` 依赖这些复制字段计算状态。目标中 stance 移到 `fact_evidence`，source tier/kind 从 occurrence/profile 查询，role 完全删除。

当前 Claim 路径由 `models/insight.py`、`services/insight_service.py` 和 `infrastructure/insight_store.py` 实现。Claim 把 `fact_ids`、`competitor_ids` 和 `product_ids` 存在 JSONB 中，并能直接创建 evidence。目标中 `claim_facts` 使用真实外键和 stance；竞品/产品范围默认从 facts 推导；首版不存在 `claim_evidence`。

报告由 `services/report_service.py` 聚合 facts、claims 和 evidence，`services/report_quality_service.py` 检查 citation，`infrastructure/report_store.py` 保存 `report_claims` 与 `report_evidence_refs`。切流前这些报告存储全部清空；切流后新 citation 的实时 ID 必须沿 claim-fact-evidence 链到达 anchor，并保存新报告自己的生成时快照。

事实生命周期 `lifecycle_status` 可为 `draft`、`active`、`superseded`、`retracted` 或 `rejected`。事实验证 `verification_status` 与生命周期正交，可为 `single_source`、`self_reported`、`corroborated` 或 `disputed`。Claim 成熟度 `maturity` 可为 `draft`、`hypothesis`、`supported`、`needs_review`、`disputed` 或 `superseded`。状态不是分数，每次拒绝、撤回、争议、待复核或取代都必须有可读的 `status_reason`。

## Plan of Work

### Milestone 1: 建立可恢复迁移机制和增量目标 schema

先修改 `migrations/apply_migrations.py`，创建 `schema_migrations(filename, checksum, applied_at)` ledger。每个未记录 SQL 文件在独立事务中执行，成功后记录 SHA-256；任何失败或已记录文件 checksum 改变都立即非零退出，不再继续后续文件。对已有数据库增加显式 `--bootstrap-existing` 模式：逐个检查 001 到 010 的代表性表、列和约束，全部满足才把现有文件记为已应用；检查失败不得猜测或自动修补。新数据库不使用 bootstrap，按顺序执行全部 migration。为 runner 添加 `tests/test_migration_runner.py`，覆盖首次执行、第二次不重跑、checksum 漂移、失败停止和已有 schema bootstrap。

创建 `migrations/011_three_layer_structured_intelligence_expand.sql`。这是增量阶段，必须保留旧读路径。对 `intel_facts` 增加 `normalized_data JSONB`、`occurred_at TIMESTAMPTZ`、`valid_from/valid_to TIMESTAMPTZ`、`time_precision`、非唯一 `candidate_key`、`lifecycle_status`、新 `verification_status`、`status_reason` 和 `supersedes_fact_id`；让旧 `fact_kind/dimension/subject/predicate/object/attributes/event_date/observed_at/importance_score/confidence_score/extraction_*/assertion_key/status` 暂时可空。为目标记录建立 partial check：`lifecycle_status IS NULL` 表示旧记录，否则 fact_type、时间精度和状态必须属于目标枚举。`valid_to` 不能早于 `valid_from`，supersedes 不能指向自己。

对 `evidence_refs` 增加 `quoted_text` 和 `locator JSONB`，让旧 owner、snippet、role、stance、score 和复制来源字段暂时可空。目标 anchor 必须有 version、occurrence、非空逐字原文、SHA-256 `quote_hash` 和 `{"kind":"char_range","start":N,"end":M}` locator。建立唯一 anchor identity，至少包含 document version、occurrence、quote hash 和 locator。创建 `fact_evidence(fact_id, evidence_ref_id, stance, created_at)`，stance 只允许 supports、contradicts、contextual，并用两个真实外键和复合主键保证关系完整性。

对 `intel_fact_competitors` 和 `intel_fact_products` 增加 `role` 与 `review_status`，目标值分别只允许 subject/counterpart/mentioned 和 confirmed/needs_review；旧 relation/confidence 暂时保留。创建 `source_profile_competitors(profile_id, competitor_id, created_by, reason, created_at)`，用于判断官方或受控来源是否属于事实主体。产品主体通过已有 product -> competitor 外键参与同一判断。

对 `insight_claims` 增加 `tags JSONB`、`maturity`、`status_reason`、`approved_by/approved_at`、`supersedes_claim_id` 和可选 `scope JSONB`；让旧 claim_type、dimension、三个 JSON ID 数组、confidence 和 status 暂时可空。创建 `claim_facts(claim_id, fact_id, stance, created_at)`，stance 同样只允许 supports、contradicts、contextual。supported claim 的批准字段必须成对出现，但“至少一个 supporting active fact”等跨表门禁放在 Service 和后续 trigger 中完成。

为新报告的 citation 在现有 `report_evidence_refs` 上增加 `quoted_text_snapshot`、`locator_snapshot`、`document_version_id` 和 `source_occurrence_id` 字段；不创建历史报告兼容表，也不从旧报告推断新 claim、fact 或 evidence 关系。完成这一里程碑时，旧 API 仍工作，migration 连续运行两次不会改变数据，目标表和 partial constraints 已可由集成测试观察。

### Milestone 2: 切换领域模型、Protocol 和 Store 的目标契约

改写 `models/intel.py`。删除 `FactKind`、`IntelDimension`、自由文本三元组、importance/confidence、抽取运行字段和 `assertion_key`。`FactType` 只保留 product、commercial、corporate、ecosystem、customer_market、risk、general；新增 `FactLifecycleStatus`、`VerificationStatus`、`TimePrecision`、`FactEntityRole`、`LinkReviewStatus`、`IntelFactCompetitorLink` 和 `IntelFactProductLink`。`IntelFact` 只保存目标设计字段和用于 API 展示的关系集合。新增纯数据 `IntelFactCandidate` 和 `FactResolution`，其中 resolution outcome 只允许 same、different、uncertain，不保存概率。

改写 `models/evidence.py`，删除 Evidence owner/type/role、URL/title/snippet 和 relevance score。保留 `EvidenceStance`，但它属于新的 `FactEvidenceLink`。`EvidenceReference` 保存 `document_version_id`、`source_occurrence_id`、`quoted_text`、`quote_hash`、`locator`、可选 `parent_chunk_id` 和创建时间。URL/title 在读取时从 Source Occurrence 与 Document Version join 得到，不复制为 anchor 身份字段。

改写 `models/insight.py`，删除 `ClaimType`、旧 status、dimension、score、JSON ID 数组和直接 evidence。新增 `ClaimMaturity`、`ClaimFactLink` 和目标 `InsightClaim`。tags 是非互斥组织标签；scope 只表达比较目标等分析范围，不能复制 facts 已有的竞品/产品归因。

在 `core/protocols.py` 将旧 `IntelStoreProtocol` 和 `InsightStoreProtocol` 替换为窄的目标方法。Store 负责持久化和事务，不接受业务 score 或多态 owner。`PostgresIntelStore` 读写 `lifecycle_status IS NOT NULL` 的新对象；`PostgresInsightStore` 读写 `maturity IS NOT NULL` 的新对象。暂时旧读由明确命名的内部 legacy adapter 支持，不能泄露到 Service、API 或 Agent 接口，并在 Milestone 7 删除。

修改 `core/factory.py`、`core/config.py` 和 `core/config_manager.py`，增加临时 `structured_intelligence_v2_write_enabled` 与 `structured_intelligence_v2_read_enabled`。默认先只开启目标写入的影子环境；完成核对后打开目标读取；正式 cutover 后删除 flags 和 legacy adapter。这个开关只控制迁移路径，不能让同一个业务请求同时写两套互相覆盖的事实身份。

新增或重写 `tests/test_intel_models.py`、`tests/test_intel_schema_and_stores.py` 和 `tests/test_insight_store.py`。测试必须证明 dataclass 没有旧字段、关系使用真实外键、candidate key 可重复、同一 anchor 可连接多个 facts、claim 不存在直接 evidence 方法，且任何三层目标表或关系都没有业务 score 列。

### Milestone 3: 实现不可变 anchor、Fact 门禁、验证和取代规则

在 `services/intel_service.py` 增加 `create_evidence_reference`。输入必须指定 active 或历史保留的 Document Version、属于同一 Document Cluster 的 Source Occurrence、quoted text 和字符 locator。Service 读取完整 `source_document_versions.content`，验证 start/end 为有效整数、`content[start:end]` 与 quoted text 逐字相等，并自行计算 SHA-256；客户端传入不同 hash 时拒绝。parent chunk 若存在，只用于确认它属于相同 version，不参与 anchor 权威身份。搜索摘要、裸 URL、手工文字或无法定位的 snippet 返回 Evidence Candidate，不调用此方法。

重写 `services/evidence_verification_service.py`。它从 Store 获取 supports/contradicts 关系、每条 evidence 所属 Document Cluster、Source Profile 与 `source_profile_competitors` 控制关系。存在需要裁决的正式 contradicts 时为 disputed；否则，支持证据全部来自事实 confirmed subject 控制的来源时为 self_reported；只有一个独立 cluster 支持时为 single_source；至少两个相互独立、已准入且不是同 cluster 转载的合格 cluster 支持时为 corroborated。来源等级只能用于判断证据是否合格，不能被复制成事实分数。每次新增、移除或改变 stance 后同步重算 verification_status 和 status_reason。

在 `services/normalized_fact_schema.py` 建立小型版本化 registry，首版至少实现设计示例 `commercial.pricing.v1`。使用项目已有 Pydantic 依赖进行字段类型、currency、billing period 和 market 校验，不给普通功能 fact 强加 subject/predicate/object schema。未知 schema、schema 名与 fact_type 不匹配或 payload 非法时，fact 保持 draft 并写明原因。

在 `services/intel_service.py` 实现 `activate_fact`、`retract_fact`、`reject_fact`、`supersede_fact` 和 `split_fact_evidence`。激活同时检查：fact_text 是完整非空原子命题；至少一个 confirmed subject；至少一个 supports 正式 anchor；每个 anchor quote 可重验；有 normalized schema 时验证通过；解析结果不是 uncertain；关键限定条件无冲突。active 后冻结 fact_text、fact_type、normalized_data、时间语义和 confirmed subject 关系。更正创建新 draft 或 active fact，并让新 fact 的 `supersedes_fact_id` 指向旧 fact；旧 fact 转 superseded 但不删除。split 接收要移动的 evidence_ref IDs，创建新 draft，事务内移动关系并重算两个 facts，任何一步失败整笔回滚。

在 migration 中增加 PostgreSQL triggers 作为最后防线。trigger 拒绝 active/superseded/retracted fact 的语义列更新，拒绝 active fact 的 confirmed subject link 增删改，拒绝物理删除 active/superseded/retracted fact；允许 evidence 关系变化、verification 重算和合法 lifecycle 转移。Service 捕获 StoreError 并转成清晰的 `NewsAssistantError` 子类，例如 `IntelligenceInvariantError`，Delivery 映射为 HTTP 409。

本里程碑的单元和 PostgreSQL 集成测试要覆盖 locator 越界、quote 不匹配、occurrence/version 不同 cluster、候选而非正式证据、无 subject、needs_review subject、无 support、normalized schema 失败、active 原地改写、合法 supersede、split 回滚、同 cluster 多 occurrence 只计一次以及反证触发 disputed。

### Milestone 4: 改造抽取 Pipeline 和保守事实解析

重写 `services/intel_service.py::FACT_EXTRACTION_SYSTEM_PROMPT` 和结构化输出 schema。模型只输出七类 fact_type、完整原子 fact_text、可选 normalized_data、occurred_at/valid_from/valid_to、time_precision、主体候选和逐字 quote locator。模型不得输出 verification_status、lifecycle_status、importance/confidence、来源等级或最终 merge 决策。一次包含多个事实或分析判断的输出必须被拒绝或拆成多个 candidate。

新增 `services/fact_resolution_service.py`。`candidate_key` 由 confirmed 或待复核主体的稳定 competitor/product ID、粗 fact_type、可选 schema/subtype 和与 time_precision 一致的时间桶组成；它只调用 Store 的 `find_fact_candidates`，不唯一。先比较金额、币种、版本、日期、市场、套餐和有效期等关键限定条件：任何明确冲突直接 different。fact_text、normalized_data 和时间语义规范化后完全相同可 same。其余候选可调用 `StructuredExtractionClientProtocol` 返回严格 JSON 的 same/different/uncertain 与文字理由；模型失败、格式错误、缺少关键限定条件或多个候选竞争都归 uncertain。只有 same 会把新 anchor 关系连接到已有 fact，different 创建新 draft，uncertain 创建独立 draft 并写 `status_reason`，禁止按 score 阈值合并。

修改 `services/pipeline_service.py`，保证处理顺序为：读取 active Document Version 与 parent chunks；抽取 candidates 与精确 quotes；解析或新建 draft facts；连接 evidence；连接 competitor/product 且自动关系一律 `needs_review`；执行激活门禁；最后运行竞品聚合。缓存 key 必须包含 document_version_id 和 extraction_version，Canonical 版本切换后不能复用旧正文抽取结果。运行细节写入现有 task stages/events、structlog 和 trace，不新增 extraction_runs 业务表。

新增可重入的重建命令，建议为 `python -m delivery.cli rebuild-structured-intelligence --shadow --batch-size 50`。命令只遍历 active Document Version，使用 `(document_version_id, extraction_version)` 幂等标记避免重复模型调用；中断后可以继续。`--shadow` 只写目标记录而不切换读 API；`--verify-only` 输出旧/新行数、无 anchor facts、无 confirmed subject facts、uncertain 数量和 quote 校验失败数，不修改数据。不要从旧 facts 反推新字段。

增加 `tests/test_fact_resolution_service.py`、`tests/test_intel_extraction_v2.py` 和 Pipeline 回归。用固定 fake structured client 证明价格地区冲突不会合并、同义且限定条件一致的事实可复用、多 occurrence 同 cluster 不增加独立来源数、缓存随 version 改变，以及重复运行不会复制 anchor 或关系。

### Milestone 5: 实现 Claim 成熟度、人工批准和事实变更传播

重写 `services/insight_service.py`。create/update 只创建或编辑 draft/hypothesis；Claim 必须通过 `claim_facts` 连接 facts，不能接收 evidence、evidence_ref_ids、competitor_ids 或 product_ids。`derive_scope` 从关联 facts 的 confirmed subject 关系计算默认 competitor/product 范围；显式 scope 只允许比较目标、时间窗和市场等分析边界。tags 可多选 trend/comparison/risk/opportunity 或其他组织标签，不参与身份或成熟度。

实现 `approve_claim(claim_id, approved_by)`。supported 必须至少有一个 stance=supports、lifecycle=active 且 verification_status 不是 disputed 的 fact；批准人必须来自经过 Delivery 认证的真实 analyst/admin 身份，不能是 `system` 或 `agent`。设置 supported、approved_by 和 approved_at 在同一事务完成。supported 后 PostgreSQL trigger 冻结 claim_text、limitations、scope 和 claim_facts；tags 可作为组织 metadata 调整。更正使用 `supersede_claim` 创建新 claim，旧 claim 保留。

当 linked fact 进入 disputed、retracted 或 superseded，或者唯一 supporting fact 不再 active 时，`IntelService` 通过注入的 `InsightStoreProtocol` 把相关 supported claims 改为 needs_review 并写明确 reason。数据库 trigger 再提供绕过 Service 时的兜底传播。复核可在事实恢复后重新批准 supported，也可转 disputed，或创建新 claim supersede 旧 claim。每条状态变化必须保留责任人和时间；模型 trace 仍只进入日志。

修改 `delivery/api/insight_router.py` 和相关 Agent 工具。新增 claim-fact 关系接口、approve/review/supersede 动作；删除 validate direct evidence 路径。`create_insight_claim` Agent 工具只创建 hypothesis，`query_insight_claims` 可按 maturity、tags、fact_id、派生 competitor/product 和更新时间筛选。新增测试证明没有 supporting active fact 不能 supported、Agent 不能批准、supported 不能改语义、fact 争议触发 needs_review、claim 不能直接关联 Evidence Reference。

### Milestone 6: 切换消费者、报告链路、API 和前端工作台

逐一修改所有旧字段消费者，使用 `rg` 清零三层业务路径中的 `fact_kind`、`dimension`、`importance_score`、`confidence_score`、`relevance_score`、`assertion_key`、`owner_type/owner_id`、claim `fact_ids` JSON 和 direct evidence。不要误删 embedding dimensions、报告 quality scores 或其他不同领域同名字段。

在 `services/competitor_service.py` 中，竞品档案、facts 列表和时间线默认只聚合 `role=subject AND review_status=confirmed` 的 active facts。时间线按 occurred_at，其次 valid_from 排序；两者都没有的 fact 只进入发现时间视图。对比接口按 fact_type、时间和 verification/lifecycle 筛选，不再按 dimension。`auto_link_facts` 只创建 needs_review 关系，人工确认后才满足激活和常规聚合条件。

更新 `agent/tools/builtin/` 下的 create/update/query/link/compare/profile/report 工具以及 `formatting.py`。`create_intel_fact` 只接受目标字段并创建 draft；`update_intel_fact` 遇到 active 返回需要 supersede 的错误；link 工具接受 role 和 review_status，不接受 confidence；search result 明确输出 Evidence Candidate，不能直接作为 formal anchor。同步 `agent/react/prompts.py`、`agent/tools/builtin/definitions.py` 和 `docs/design-docs/react-agent.md` 描述的参数契约，保持现有 14 个工具名，除非实施中确有新增审核工具需求并记录 Decision Log。

重写 `services/report_service.py` 的上下文构建：新报告选择 supported claims，经 claim_facts 获取 active facts，再经 fact_evidence 获取逐字 anchor；citation 必须保存 claim_id、fact_id、evidence_ref_id 和 quote/locator/version/occurrence 快照。`services/report_quality_service.py` 增加 reachability 规则，任一 citation 不能从 report claim 沿目标链到达时报告进入 revision_required。报告发布时只允许 supported claims；后续对象状态变化不改新报告自己的正文和快照，但详情 API 显示 current maturity/lifecycle/verification 与生成时快照的差异。保留 `report_quality_reviews` 的质量分数；这些分数只存在于切流后创建的新报告。

更新 `delivery/api/intel_router.py`、`delivery/api/competitor_router.py`、`delivery/api/report_router.py` 和 API 文档。Intel API 以 lifecycle_status、verification_status、fact_type、subject competitor/product、occurred/valid time 和 keyword 为筛选；证据创建与 fact-evidence 关联是两个动作。用显式 activate/retract/reject/supersede/split action 代替可任意写的通用 status patch。Pydantic 请求模型使用 Literal/Enum 并禁止额外旧字段，旧客户端提交 score、dimension、owner 或 direct claim evidence 返回 HTTP 422。

把 `frontend/src/views/IntelView.vue` 改成同一情报工作台内的 Facts 和 Claims 两个 tab，Evidence Reference 在事实详情中作为可复用原文锚点展示。Fact 列表显示 fact type、lifecycle、verification、confirmed subject 和现实时间；移除 importance/confidence/dimension。详情支持 draft 编辑、subject 复核、activate、supersede、retract、evidence stance 和 split。Claim tab 支持 maturity/tags/fact 过滤、claim-fact 关系、人工 approve 和 needs_review 处理。`frontend/src/views/CompetitorView.vue` 改为 subject-only 聚合，`ReportView.vue` 展示 claim -> fact -> quote 的 citation chain 及当前状态变化。同步 `frontend/src/api/index.ts` 和 `StatusBadge` 状态映射。前端没有测试 runner，因此最低门槛是 `pnpm --dir frontend build` 和浏览器桌面/移动截图验收。

### Milestone 7: 影子核对、正式切流、收缩 schema 和文档验收

在 staging 或本地完整副本先运行重建命令。核对必须输出：新 facts/claims/anchors 数量；每个 active fact 的 formal support 和 confirmed subject 数；所有 quote 校验结果；candidate resolution outcome 分布；supported claim 的 supporting active fact 数；同 cluster occurrence 去重结果。存在无 anchor active fact、无 subject active fact、direct claim evidence、quote 失败、业务 score 或无法满足链路的 supported claim 时不得切流。旧报告数量可以不为零，直到执行清理步骤；清理前必须保存数据库备份和重建核对输出。

打开 `structured_intelligence_v2_read_enabled`，运行 API、Agent、Pipeline、报告和前端验收。稳定观察后先备份 PostgreSQL，再创建并执行 `migrations/012_three_layer_structured_intelligence_contract.sql`。该 migration 在同一事务内清空旧报告域存储（`analysis_reports`、`report_claims`、`report_evidence_refs`、`report_quality_reviews`、`analysis_audit_log`），然后删除 `lifecycle_status IS NULL` 的旧 facts、`maturity IS NULL` 的旧 claims、owner 仍为旧多态语义的 evidence 和没有目标 role/review_status 的旧归因关系。它不删除 `document_clusters`、`source_occurrences`、`source_document_versions`、`source_documents`、competitors 或 products，因为这些是重建和后续运行的输入主数据。将目标列改为 NOT NULL；删除旧 score、多态 owner、JSON ID 数组、FactKind/Dimension/三元组和复制来源字段；把现有报告关系表的外键改为目标表并验证所有 FK/check constraints。migration ledger 保证该文件只执行一次，不创建旧报告兼容读取路径。

删除临时 feature flags、legacy adapter 和双读代码。使用以下定向搜索分别检查目标业务目录和例外目录：三层 models/services/stores/routers/tools/frontend 中不能再出现旧字段；`embedding_vector_size`、`report_quality_reviews.overall_score/dimension_scores` 等合法例外要在检查脚本中按完整路径白名单，而不是忽略全局搜索结果。

最后更新 `ARCHITECTURE.md`、`CONTEXT.md`、`docs/DESIGN.md`、`docs/design-docs/structured-intelligence-model.md` 的“当前实现差异”、`protocol-contracts.md`、`react-agent.md`、`api-routes.md`、`docs/generated/db-schema.md` 和 `docs/generated/dbdoc/`。把本 ExecPlan 的 Progress、Surprises、Decision Log 和 Outcomes 更新为实际结果，并在文件底部追加修订说明。

## Concrete Steps

所有命令从仓库根目录 `D:\study\Logos` 执行。先记录工作树和测试基线，不回退已有用户修改：

    git status --short
    python -m pytest tests/test_intel_models.py tests/test_intel_schema_and_stores.py tests/test_phase2_services.py tests/test_intel_router.py tests/test_insight_router.py -q
    pnpm --dir frontend build

实现 Milestone 1 后，先对一次性临时数据库验证 migration。`.env` 必须提供测试 PostgreSQL 的 `PG_DSN`，不能直接对未备份生产库运行：

    docker compose up -d postgres redis qdrant
    python migrations/apply_migrations.py --bootstrap-existing
    python migrations/apply_migrations.py
    python migrations/apply_migrations.py

对已有数据库，第一次命令应输出 001 到 010 的 sentinel 检查和 baseline 记录；第二次只执行未记录的 011；第三次应输出没有待执行 migration。新空数据库省略 `--bootstrap-existing`，第一次普通运行应从 001 开始。任何 `[FAIL]` 必须使进程非零退出，不能出现“继续执行下一个文件”。

每个后端里程碑至少运行对应聚焦回归和静态编译：

    python -m pytest tests/test_migration_runner.py tests/test_intel_models.py tests/test_intel_schema_and_stores.py -q
    python -m pytest tests/test_evidence_anchor_service.py tests/test_evidence_verification_service.py tests/test_intel_lifecycle_service.py -q
    python -m pytest tests/test_fact_resolution_service.py tests/test_intel_extraction_v2.py tests/test_pipeline_service.py -q
    python -m pytest tests/test_insight_service.py tests/test_insight_router.py tests/test_tools.py -q
    python -m pytest tests/test_competitor_router_phase2.py tests/test_report_service_workflow.py tests/test_report_quality_service.py tests/test_report_router.py -q
    python -m compileall models services infrastructure delivery agent core scheduler -q

运行影子重建和只读核对：

    python -m delivery.cli rebuild-structured-intelligence --shadow --batch-size 50
    python -m delivery.cli rebuild-structured-intelligence --verify-only

成功核对应出现等价摘要，具体数量取决于数据集：

    invalid_quotes=0
    active_facts_without_support=0
    active_facts_without_confirmed_subject=0
    supported_claims_without_active_support=0
    direct_claim_evidence=0
    unreachable_report_citations=0

前端与端到端验收：

    pnpm --dir frontend build
    python -m delivery.server

另一个终端运行：

    pnpm --dir frontend dev

浏览 `http://localhost:5173/intel`，完成 Fact/Claim/Evidence 操作；调用后端时用实际配置的 API key。至少保存一次桌面 1440x900 和移动 390x844 截图，确认筛选、表格、详情、状态动作和 citation chain 无重叠或截断。

正式 contract migration 前再次备份 PostgreSQL，并保存 verify-only 输出。执行 012 后运行完整测试：

    python migrations/apply_migrations.py
    python -m pytest tests/ -q
    pnpm --dir frontend build
    python -m compileall models services infrastructure delivery agent core scheduler -q
    git diff --check

不要在计划中预填最终 passed 数。实施者应在 Progress 和 Outcomes 写入当时实际数量，并区分本次回归与已经存在的失败；任何影响三层链路、migration 或报告引用的失败都必须在完成前修复。

## Validation and Acceptance

完成实现必须同时满足以下可观察行为。

创建 Evidence Reference 时，服务端从 Document Version 的 locator 取出的字符串与 quoted_text 完全相同，quote_hash 由服务端计算。传入搜索摘要、裸 URL、错误 offset、被模型改写的摘要或跨 cluster occurrence 时返回 422/409，数据库不新增 formal anchor。同一 anchor 连接两个 facts 时 `evidence_refs` 只有一行，`fact_evidence` 有两行且 stance 可以不同。

创建 Fact 时 API 不接受 `fact_kind`、`dimension`、三元组、importance/confidence、assertion_key 或客户端 verification。没有 confirmed subject、formal supporting anchor、合法时间语义或 required normalized schema 的 fact 保持 draft 并返回 status_reason。满足全部门禁后可 active。对 active fact PUT 修改 fact_text、fact_type、normalized_data、时间或 confirmed subject 返回 HTTP 409；supersede action 创建新 ID 并保留旧行。

同一 Document Cluster 的多个 occurrence 只算一个来源。一个主体控制的支持来源产生 self_reported；一个合格独立 cluster 产生 single_source；两个合格独立 cluster 产生 corroborated；正式 contradicts 产生 disputed。界面和 API 只显示离散状态与理由，不显示综合分数。

candidate key 相同但价格、币种、版本、市场、套餐或时间冲突时必须生成不同 draft facts。无法明确判断时生成 uncertain draft，不合并到已有 active fact。split 操作可把误连 evidence 原子移动到新 draft，失败不会留下半移动关系。

Claim 只能通过 claim_facts 关联 facts。提交 direct evidence、evidence owner、JSON fact_ids 或 confidence 返回 422。Agent 创建的 claim 最多为 hypothesis。没有 supporting active non-disputed fact 或没有人工批准人时不能 supported。supported claim 的文字、limitations、scope 和 claim_facts 不能原地改；依赖 fact disputed/retracted/superseded 后自动 needs_review。

竞品档案和时间线默认只出现 confirmed subject active facts，counterpart、mentioned 和 needs_review 不计入常规聚合。时间线不再把 observed_at 假装成现实发生时间；无 occurred_at/valid_from 的 fact 出现在发现时间视图。

新报告的每条 citation 都能从 report claim 到 claim_facts、fact_evidence、Evidence Reference，再到 Document Version 的逐字区间。删除或 supersede 当前对象不会改变该新报告自己的 quote、locator、URL/title 和正文快照；报告详情会提示当前状态。执行 012 后旧报告、旧 claim、旧 fact、旧 evidence 和旧报告质量/审计记录的查询结果必须为空。

数据库最终 schema 对 fact-evidence、claim-fact、fact-competitor 和 fact-product 使用真实外键；三层对象和关系没有 importance、confidence、relevance 或关联置信度列；Evidence Reference 没有 owner、stance、role 或复制的 source tier/kind；Insight Claim 没有 direct evidence 或 JSON ID 数组。`report_quality_reviews` 的质量 score 仍存在。

全量 `pytest`、前端 build、compileall 和 `git diff --check` 通过，或者仅剩与本工作无关且在实施前已经稳定复现的失败。后者必须在 Outcomes 列出基线与最终相同堆栈，不能把 migration、API、Agent、报告、Pipeline 或前端失败归为既有问题。

## Idempotence and Recovery

`011` 是增量 migration，执行前备份数据库。migration ledger 让每个文件只成功执行一次；checksum 改变必须报错，已应用 migration 不允许原地修改，修正只能新增下一编号文件。`--bootstrap-existing` 只在没有 ledger 且 001-010 sentinel 全部匹配时使用。空数据库或已有 ledger 的数据库不得使用该参数。

影子重建按 Document Version 和 extraction version 幂等。中断后重跑应跳过已完成版本，unique anchor identity、fact_evidence 和 claim_facts 复合键防止复制。Redis 清空只会丢失加速缓存；PostgreSQL 中的重建进度和领域记录必须足够恢复。

正式切读前可关闭 v2 read flag 回到旧只读 API；v2 写入数据保留用于诊断，不删除。执行 `012` 前必须备份，因为该 migration 会删除全部旧报告和旧结构化情报内容。执行 `012` 后不再承诺回到旧 schema，恢复方式是还原执行 012 前的 PostgreSQL 备份并部署对应代码版本，不能写逆向 migration 猜测恢复已删除的旧分数、报告正文或 JSON 关系。

split、supersede、claim approval 和状态传播必须使用 PostgreSQL 事务。任何中途异常都整笔回滚。正常运行中 active facts、supported claims、被新报告引用的 Document Version 和 Evidence Reference 不做物理删除；法规删除场景保留失效状态与原因。012 是一次明确授权的 destructive cutover，只删除用户指定的旧报告、旧结构化情报及其关系，不把该清理规则扩展到来源治理、竞品或产品主数据。

## Artifacts and Notes

目标数据库关系应能由以下简化查询证明；实施时把真实输出摘录到本节：

    SELECT c.id AS claim_id, cf.stance AS claim_stance,
           f.id AS fact_id, fe.stance AS evidence_stance,
           e.id AS evidence_id, e.document_version_id,
           e.quoted_text, e.locator
    FROM insight_claims c
    JOIN claim_facts cf ON cf.claim_id = c.id
    JOIN intel_facts f ON f.id = cf.fact_id
    JOIN fact_evidence fe ON fe.fact_id = f.id
    JOIN evidence_refs e ON e.id = fe.evidence_ref_id
    WHERE c.id = '<accepted-claim-id>';

预期至少返回一条完整链，quoted_text 与 locator 非空，claim 和 fact stance 独立保存。

最终旧字段扫描要按业务边界执行，不能用一个过宽正则误报 embedding 或报告质量字段：

    rg -n "fact_kind|assertion_key|importance_score|confidence_score|relevance_score|owner_type|owner_id" models services infrastructure delivery agent frontend/src
    rg -n "dimension|fact_ids|competitor_ids|product_ids|claim_type" models/insight.py services/insight_service.py infrastructure/insight_store.py delivery/api/insight_router.py agent/tools/builtin frontend/src/views/IntelView.vue

第一条命令若命中合法的 report quality 或 embedding 路径，要逐项说明；三层 model/store/service/router/tool 命中必须为零。不要直接全局替换 `dimension` 或 `confidence_score`，因为 embedding 维度和报告质量分仍是合法概念。

## Interfaces and Dependencies

最终 `models/intel.py` 至少定义以下稳定类型；字段名可按 dataclass 语法实现，但语义和枚举值不能改变：

    class FactType(str, Enum):
        PRODUCT = "product"
        COMMERCIAL = "commercial"
        CORPORATE = "corporate"
        ECOSYSTEM = "ecosystem"
        CUSTOMER_MARKET = "customer_market"
        RISK = "risk"
        GENERAL = "general"

    class FactLifecycleStatus(str, Enum):
        DRAFT = "draft"
        ACTIVE = "active"
        SUPERSEDED = "superseded"
        RETRACTED = "retracted"
        REJECTED = "rejected"

    class VerificationStatus(str, Enum):
        SINGLE_SOURCE = "single_source"
        SELF_REPORTED = "self_reported"
        CORROBORATED = "corroborated"
        DISPUTED = "disputed"

    class TimePrecision(str, Enum):
        DAY = "day"
        MONTH = "month"
        QUARTER = "quarter"
        UNKNOWN = "unknown"

    class FactEntityRole(str, Enum):
        SUBJECT = "subject"
        COUNTERPART = "counterpart"
        MENTIONED = "mentioned"

    class LinkReviewStatus(str, Enum):
        CONFIRMED = "confirmed"
        NEEDS_REVIEW = "needs_review"

`IntelFact` 必须包含 id、fact_type、fact_text、normalized_data、occurred_at、valid_from、valid_to、time_precision、candidate_key、lifecycle_status、verification_status、status_reason、supersedes_fact_id、created_by、created_at 和 updated_at。不得包含来源文档 owner、FactKind、Dimension、业务 score 或运行 trace。

最终 `models/evidence.py` 定义 `EvidenceReference(id, document_version_id, source_occurrence_id, quoted_text, quote_hash, locator, parent_chunk_id, created_at)`、`EvidenceStance` 和 `FactEvidenceLink(fact_id, evidence_ref_id, stance, created_at)`。locator 首版结构固定为 `kind=char_range`、非负 start、end 大于 start，offset 是 Python Unicode code point 的 0-based end-exclusive 下标。

最终 `models/insight.py` 定义：

    class ClaimMaturity(str, Enum):
        DRAFT = "draft"
        HYPOTHESIS = "hypothesis"
        SUPPORTED = "supported"
        NEEDS_REVIEW = "needs_review"
        DISPUTED = "disputed"
        SUPERSEDED = "superseded"

`InsightClaim` 包含 id、claim_text、tags、limitations、scope、maturity、status_reason、approved_by、approved_at、supersedes_claim_id、created_by、created_at 和 updated_at；`ClaimFactLink` 包含 claim_id、fact_id、stance 和 created_at。Claim 不包含 evidence、score 或实体 ID 数组。

`core/protocols.py::IntelStoreProtocol` 最终至少提供：

    save_fact(fact: IntelFact) -> IntelFact
    get_fact(fact_id: str) -> IntelFact | None
    list_facts(filters: dict, limit: int, offset: int) -> list[IntelFact]
    find_fact_candidates(candidate_key: str, limit: int = 20) -> list[IntelFact]
    save_evidence_reference(evidence: EvidenceReference) -> EvidenceReference
    get_evidence_reference(evidence_ref_id: str) -> EvidenceReference | None
    link_fact_evidence(link: FactEvidenceLink) -> None
    move_fact_evidence(source_fact_id: str, target_fact_id: str, evidence_ref_ids: list[str]) -> None
    list_fact_evidence(fact_id: str) -> list[FactEvidenceLink]
    link_fact_to_competitor(link: IntelFactCompetitorLink) -> None
    link_fact_to_product(link: IntelFactProductLink) -> None
    update_fact_lifecycle(fact_id: str, lifecycle_status: str, status_reason: str) -> IntelFact

`InsightStoreProtocol` 最终至少提供 save/get/list claim、replace/list claim facts、update maturity、find claims by fact 和 mark dependent supported claims needs_review。`SourceProfileStoreProtocol` 增加来源 profile 与 competitor 控制关系的保存和查询。所有 Protocol 只使用 model dataclass 和 Python 基础类型，不泄露 psycopg2 row/cursor。

`services/fact_resolution_service.py` 暴露：

    resolve(candidate: IntelFactCandidate, candidates: list[IntelFact]) -> FactResolution

`FactResolution` 包含 outcome、matched_fact_id 和 reason，不包含概率。`services/intel_service.py` 至少暴露 create draft、create/reuse anchor、link evidence、activate、retract、reject、supersede、split 和 list/detail；`services/insight_service.py` 至少暴露 create hypothesis、replace claim facts、approve、mark disputed、supersede、review 和 list/detail。

不新增外部数据库、向量集合、通用知识图谱、Intel Event、claim_evidence、audit_events 或 extraction_runs。继续使用 PostgreSQL、现有 StructuredExtractionClientProtocol、structlog、task stages/events 和 Pydantic。Fact 不进入 Qdrant；开放式检索仍由现有父子分块 RAG 完成。

修订说明（2026-07-12）：首次创建本 ExecPlan。计划把 ADR-0002 的三层目标落实为两阶段 schema 迁移、保守事实解析、不可变生命周期、人工 claim 批准、新报告 citation 快照和端到端验收；同时补入当前 migration runner 与来源控制关系两个实现前置问题。根据用户决定，012 在切流时明确删除旧报告及旧结构化情报存储内容，不再设计旧报告快照迁移或兼容读取；来源治理、文档版本、竞品和产品主数据保留为重建输入。
