# 第二阶段结构化情报事实与服务层重构计划

> **状态**：规划文档  
> **撰写日期**：2026-05-23  
> **依据文档**：`docs/exec-plans/enterprise-ai-competitor-analysis-plan.md`、`docs/exec-plans/phase-1-infrastructure-refactor-plan.md`、`ARCHITECTURE.md`、`docs/DESIGN.md`、`docs/design-docs/protocol-contracts.md`、`docs/generated/db-schema.md`  
> **阶段定位**：企业级 AI 竞品分析改造的第二阶段，面向 PostgreSQL 业务表、领域模型、服务层与 Agent 原子工具边界。  
> **核心原则**：不把结构化情报做成 RAG 摘要索引；RAG 继续负责原文证据检索，第二阶段只新增可过滤、可聚合、可审计的业务事实层。彻底重构，不为旧 News/Brief/Article 摘要链路保留兼容分支；可复用的组件必须更名到新语义，若不更名必须写明理由。

---

## 1. 背景

第一阶段已经把知识底座改为：

- PostgreSQL 保存 `source_documents`、`document_parent_chunks`、`document_vector_points`、任务历史、竞品和报告。
- Qdrant 保存子 chunk 向量和 payload。
- Redis 保存执行期状态、锁、幂等和短期缓存。
- Pipeline 将 RSS/Web/上传文档转为 `SourceDocument`，再生成父子分块并向量化。

企业级竞品分析的下一步不是再给文章生成一份摘要，也不是给摘要再做一套检索。当前父子分块 RAG 已经可以通过 Qdrant 子块语义检索和 PostgreSQL 父块关键词检索找到原文证据。如果第二阶段只是新增 `IntelItem.summary`，再让 Agent 先查摘要、再查原文，会与 RAG 产生重复链路。

因此第二阶段的目标应调整为：**从原文证据中抽取可审计的业务事实和事件**，为时间线、过滤、聚合、对比矩阵、报告 claim 和人工复核提供稳定结构化数据。

结构化事实抽取属于高频、批处理、格式约束强的任务，不应强制复用 Agent 对话和报告生成使用的主 LLM。第二阶段应提供独立的结构化抽取 AI 接口，让用户可以为事实抽取选择更低价、更快的模型，同时保留主 LLM 给复杂问答、报告撰写和后续质量审查使用。

---

## 2. 核心判断

### 2.1 RAG 与结构化情报事实的边界

| 层 | 负责 | 不负责 |
|---|---|---|
| 父子分块 RAG | 开放式语义检索、原文证据召回、未知问题探索、抽取遗漏兜底、报告引用核验 | 稳定结构化过滤、统计聚合、业务事实去重 |
| IntelFact / IntelEvent | 已确认业务事实、事件时间线、竞品/产品/维度归因、过滤聚合、事实去重、报告素材 | 替代原文检索、保存长摘要、作为唯一证据 |
| InsightClaim | 基于多个事实和证据形成的分析结论 | 直接替代报告正文、绕过证据检查 |
| ReportService | 基于 claim 和 evidence 组织报告上下文 | 在 Phase 2 完整实现质量门禁 |

第二阶段必须避免把结构化情报设计成：

```text
SourceDocument -> parent chunk -> summary -> summary search
```

正确方向是：

```text
SourceDocument -> parent chunk -> IntelFact / IntelEvent -> InsightClaim
                           \-> RAG evidence search and verification
```

### 2.2 删除旧摘要阶段，改为结构化事实抽取

现有 Pipeline 的 `summary` 阶段不应继续作为“文章摘要给 Agent 阅读”的阶段，也不应作为可选兼容任务长期存在。第二阶段将其删除，并新增：

```text
extract_intel_facts
```

该阶段可以生成短文本字段，但短文本只是业务事实的展示字段，不是 RAG 替代品。所有关键事实必须能回链到 `source_document_id` 和 `parent_chunk_id`。旧 `SummaryService` 如果仍有可复用的 prompt 解析、批处理或缓存逻辑，应更名并重构为 `StructuredExtractionService` 的内部实现；如果只是服务 `articles.summary`，直接删除。

---

## 3. 阶段目标

第二阶段完成后，系统应具备以下能力：

1. PostgreSQL 中有独立的结构化情报事实/事件表，而不是继续把情报塞进 `articles.summary` 或 `source_documents.analysis_notes`。
2. 每条事实都能指向原文证据：`source_documents.id`、`document_parent_chunks.parent_chunk_id`、URL、snippet。
3. 服务层提供完整领域能力：事实抽取、事实 CRUD、证据绑定、竞品/产品归因、事实检索、claim 创建。
4. Agent 工具全部原子化，并且只能通过服务层白名单修改业务数据。
5. Agent 可以增删改查业务表中的数据，但不能修改表结构、执行 DDL 或运行任意 SQL。
6. 报告生成工具不再在 Tool 内直接拼业务逻辑，而是逐步迁移到 `ReportService` / `InsightService`。
7. 删除旧 News/Brief/Article 摘要分析链路；新增能力统一使用 `intel`、`fact`、`event`、`claim`、`evidence` 命名。
8. 结构化事实抽取使用独立 AI 接口，可配置低价模型，不强制复用 Agent 主 LLM。

---

## 4. 明确非目标

第二阶段不做以下事项：

- 不删除父子分块 RAG，不删除 Qdrant 子块向量检索。
- 不把 IntelFact 向量化为第二套语义检索主路径。
- 不实现完整报告质量门禁；质量门禁属于 Phase 3。
- 不引入 Multi-agent 运行时。
- 不给 Agent 任意 SQL、DDL、migration 或 schema 修改工具。
- 不要求前端一次性完成完整工作台改版。
- 不迁移历史旧数据；按新 schema 从空库或新数据开始。
- 不保留旧 `articles.summary`、`get_recent_news`、`read_article` 等新闻助手链路作为第二阶段运行路径。

---

## 5. 删除、复用与更名原则

第二阶段按彻底重构执行，旧内容处理遵循以下规则：

1. **能删除就删除**：只服务 News/Brief/Article 摘要链路的表、字段、服务、工具和 API 直接删除。
2. **复用必须更名**：如果组件能力仍有价值但名称绑定旧语义，必须更名。例如 `SummaryService` 的可复用部分迁移为 `StructuredExtractionService`。
3. **不更名必须写理由**：名称仍准确表达当前职责时才保留，例如 `web_search`、`list_competitors`、`analysis_reports`。
4. **不做隐式兼容层**：不提供旧 DTO、旧路由、旧工具名到新实现的透明转发。
5. **不迁移旧数据**：旧表删除后从新 schema 开始，避免为了历史数据污染新模型。

---

## 6. 领域命名

总计划中使用 `IntelItem` 作为结构化情报项名称。经过边界讨论，第二阶段建议改为更精确的两个对象：

| 名称 | 说明 | 使用场景 |
|---|---|---|
| `IntelFact` | 从原文抽取出的原子业务事实 | 功能发布、定价变化、合作、招聘、客户案例等 |
| `IntelEvent` | 带明确时间点或时间窗口的业务事件 | 时间线、竞品动态、报告“关键变化” |
| `EvidenceRef` | 指向原文和父块的证据引用 | fact、event、claim 的支撑来源 |
| `InsightClaim` | 基于多个 fact/event/evidence 形成的分析结论 | 报告、对比分析、风险和机会判断 |

实现上可以选择一张 `intel_facts` 表覆盖事实与事件，通过 `fact_kind` 区分：

```text
fact / event / signal
```

不保留 `IntelItem.summary` 作为核心名词，避免再次滑向“摘要表”。

---

## 7. PostgreSQL Schema 计划

新增 migration：

```text
migrations/004_intel_fact_schema.sql
```

如果当前 migration 编号已有变更，按实际下一个编号创建。

### 7.1 `intel_facts`

结构化业务事实权威表。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PRIMARY KEY | 事实 ID |
| `source_document_id` | UUID NOT NULL | 引用 `source_documents.id` |
| `fact_kind` | TEXT NOT NULL | `fact/event/signal` |
| `fact_type` | TEXT NOT NULL | `feature_release/pricing_change/partnership/hiring/funding/customer_case/security/legal/market_signal/general` |
| `dimension` | TEXT NOT NULL | `product/technology/go_to_market/pricing/customer/ecosystem/risk/financial/talent/general` |
| `subject` | TEXT NOT NULL | 事实主体，如竞品、产品、功能名 |
| `predicate` | TEXT NOT NULL | 事实动作，如 released、changed pricing、partnered |
| `object` | TEXT DEFAULT '' | 事实客体，如功能、价格、合作方 |
| `fact_text` | TEXT NOT NULL | 人类可读原子事实，不是长摘要 |
| `attributes` | JSONB NOT NULL DEFAULT `{}` | 结构化属性，如 feature_name、price、plan、region |
| `event_date` | DATE NULL | 事件发生日期，未知则为空 |
| `observed_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 系统观察时间 |
| `importance_score` | FLOAT NOT NULL DEFAULT 0.0 | 重要度 0-1 |
| `confidence_score` | FLOAT NOT NULL DEFAULT 0.0 | 抽取置信度 0-1 |
| `source_reliability` | FLOAT NOT NULL DEFAULT 0.0 | 来源可靠度 0-1 |
| `extraction_method` | TEXT NOT NULL DEFAULT 'llm' | `llm/rule/manual/imported` |
| `extraction_version` | TEXT NOT NULL DEFAULT '' | Prompt 或规则版本 |
| `dedupe_key` | TEXT NOT NULL DEFAULT '' | 去重键 |
| `status` | TEXT NOT NULL DEFAULT 'active' | `draft/active/rejected/archived` |
| `created_by` | TEXT NOT NULL DEFAULT 'system' | `system/agent/user` |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 创建时间 |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 更新时间 |

索引：

- `(source_document_id)`
- `(fact_type, event_date DESC)`
- `(dimension, event_date DESC)`
- `(status, event_date DESC)`
- `(dedupe_key)`，允许空值重复；非空建议唯一或按 `source_document_id + dedupe_key` 唯一。
- GIN `attributes`

约束：

- `fact_text` 不允许为空。
- `confidence_score`、`importance_score`、`source_reliability` 范围为 0-1。
- Agent 创建的事实默认 `status='draft'`，系统抽取高置信度事实可为 `active`。

### 7.2 `intel_fact_competitors`

事实与竞品多对多关联。

| 字段 | 类型 | 说明 |
|---|---|---|
| `fact_id` | UUID NOT NULL | 引用 `intel_facts.id` |
| `competitor_id` | INT NOT NULL | 引用 `competitors.id` |
| `relation_type` | TEXT NOT NULL DEFAULT 'subject' | `subject/mentioned/affected/competitor` |
| `confidence_score` | FLOAT NOT NULL DEFAULT 1.0 | 关联置信度 |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 创建时间 |

主键：`(fact_id, competitor_id, relation_type)`

### 7.3 `intel_fact_products`

事实与产品线多对多关联。

| 字段 | 类型 | 说明 |
|---|---|---|
| `fact_id` | UUID NOT NULL | 引用 `intel_facts.id` |
| `product_id` | INT NOT NULL | 引用 `competitor_products.id` |
| `relation_type` | TEXT NOT NULL DEFAULT 'subject' | `subject/mentioned/affected` |
| `confidence_score` | FLOAT NOT NULL DEFAULT 1.0 | 关联置信度 |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 创建时间 |

主键：`(fact_id, product_id, relation_type)`

### 7.4 `evidence_refs`

统一证据引用表。证据可以挂到 fact 或 claim。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PRIMARY KEY | 证据 ID |
| `owner_type` | TEXT NOT NULL | `intel_fact/insight_claim` |
| `owner_id` | UUID NOT NULL | 对应 fact 或 claim ID |
| `source_document_id` | UUID NULL | 引用 `source_documents.id` |
| `parent_chunk_id` | TEXT NULL | 引用 `document_parent_chunks.parent_chunk_id` |
| `url` | TEXT NOT NULL DEFAULT '' | 原始 URL |
| `title` | TEXT NOT NULL DEFAULT '' | 来源标题 |
| `snippet` | TEXT NOT NULL DEFAULT '' | 支撑事实的原文片段 |
| `quote_hash` | TEXT NOT NULL DEFAULT '' | snippet hash，用于追踪引用稳定性 |
| `evidence_type` | TEXT NOT NULL DEFAULT 'source_chunk' | `source_chunk/url/manual/search_result` |
| `relevance_score` | FLOAT NOT NULL DEFAULT 0.0 | 与事实/claim 的相关度 |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 创建时间 |

索引：

- `(owner_type, owner_id)`
- `(source_document_id)`
- `(parent_chunk_id)`
- `(url)`

规则：

- `intel_fact` 至少需要一条 evidence。
- 有 `parent_chunk_id` 时应能回查父块正文。
- 不保存长篇原文，只保存短 snippet 和定位信息。
- Phase 2 的 evidence 只挂 `intel_fact` 和 `insight_claim`。报告引用在 Phase 3 通过独立 report-evidence 关系表接入，不用 `owner_id` 兼容 INT report ID。

### 7.5 `insight_claims`

分析结论表。Phase 2 只提供基础 claim 创建和查询，Phase 3 再接质量门禁。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PRIMARY KEY | claim ID |
| `claim_text` | TEXT NOT NULL | 分析结论 |
| `claim_type` | TEXT NOT NULL | `trend/comparison/risk/opportunity/finding/hypothesis` |
| `dimension` | TEXT NOT NULL | 分析维度 |
| `competitor_ids` | JSONB NOT NULL DEFAULT `[]` | 涉及竞品 |
| `product_ids` | JSONB NOT NULL DEFAULT `[]` | 涉及产品 |
| `fact_ids` | JSONB NOT NULL DEFAULT `[]` | 支撑事实 ID |
| `confidence_score` | FLOAT NOT NULL DEFAULT 0.0 | 结论置信度 |
| `limitations` | TEXT NOT NULL DEFAULT '' | 数据不足与推断边界 |
| `status` | TEXT NOT NULL DEFAULT 'draft' | `draft/active/rejected/archived` |
| `created_by` | TEXT NOT NULL DEFAULT 'system' | `system/agent/user` |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 创建时间 |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 更新时间 |

索引：

- `(claim_type, created_at DESC)`
- `(dimension, created_at DESC)`
- `(status, created_at DESC)`
- GIN `competitor_ids`
- GIN `fact_ids`

规则：

- `active` claim 必须至少有一个 `fact_id` 或一条 evidence。
- `draft` claim 可以由 Agent 创建，等待后续人工或质量门禁确认。

### 7.6 旧表与旧字段删除计划

第二阶段是彻底重构，不设计旧数据迁移。旧对象按“删除、重建、复用但更名、复用且说明理由”四类处理。

| 旧表/字段/对象 | Phase 2 处理 | 理由 |
|---|---|---|
| `source_documents.intel_type` | 删除 | 结构化类型属于 `intel_facts.fact_type`，不应放在文档表 |
| `source_documents.analysis_notes` | 删除 | 自由文本批注会绕过 fact/evidence 审计链路 |
| `source_documents.source_reliability` | 删除 | 来源可靠度属于具体 fact 的抽取结果，进入 `intel_facts.source_reliability` |
| `source_documents.competitor_ids/product_ids` | 保留且不更名 | 文档级粗过滤字段仍服务 Qdrant payload 过滤，不承担事实归因 |
| `intel_competitors/intel_products` | 删除 | 文档级情报关联被 `intel_fact_competitors/intel_fact_products` 替代 |
| `articles` 及 `articles.summary` | 删除 | 新知识来源统一为 `source_documents`，摘要不再是分析输入 |
| `analysis_reports.source_refs` | Phase 3 删除并迁移到 report-evidence 关系表 | Phase 2 不扩展报告表，Phase 3 统一证据引用 |
| `analysis_reports` 表名 | 暂不更名 | 名称仍准确表达“分析报告”，不是 News/Brief 遗留命名 |

---

## 8. 模型改造计划

### 8.1 新增 `models/intel.py`

建议数据类：

- `IntelFact`
- `IntelFactCompetitorLink`
- `IntelFactProductLink`
- `FactKind`
- `FactType`
- `IntelDimension`
- `FactStatus`

`IntelFact` 字段与 `intel_facts` 表保持一致。枚举采用 `str, Enum`，但 Store 层应能容忍未知字符串并回退到 `general`，避免历史数据卡死。

### 8.2 新增 `models/evidence.py`

建议数据类：

- `EvidenceRef`
- `EvidenceOwnerType`
- `EvidenceType`

Evidence 不依赖 Agent 或 Service，保持纯数据。

### 8.3 新增 `models/insight.py`

建议数据类：

- `InsightClaim`
- `ClaimType`
- `ClaimStatus`

`InsightClaim.fact_ids` 用 `list[str]` 保存 UUID 字符串，避免 dataclass 与数据库 UUID 类型耦合。

### 8.4 调整 `models/report.py`

Phase 2 不围绕报告模型做兼容扩展。处理原则：

- 删除或废弃 `SourceRef.intel_id = articles.id` 语义。
- 不新增面向旧 `source_refs` JSON 的兼容 DTO。
- Phase 3 统一把报告引用改为 `claim_ids` 和 report-evidence 关系表。
- `models.report.AnalysisReport` 可以暂时保留类名，因为它不是旧 News/Brief 命名，且仍准确表达报告领域对象。

---

## 9. Protocol 计划

### 9.1 `StructuredExtractionClientProtocol`

结构化事实抽取和结构化摘要生成使用独立 AI 接口，不复用 Agent 主 LLM。该接口可以接 OpenAI-compatible、Gemini、Anthropic 或本地模型，但默认配置应允许用户选择低价模型。

```python
class StructuredExtractionClientProtocol(Protocol):
    def extract_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]: ...
```

配置建议：

| 配置项 | 说明 |
|---|---|
| `structured_extraction_provider` | 结构化抽取供应商；默认可复用 openai-compatible 适配层 |
| `structured_extraction_model` | 结构化抽取模型，默认选择低成本模型 |
| `structured_extraction_base_url` | 独立 base URL |
| `structured_extraction_api_key` | 独立 API key |
| `structured_extraction_temperature` | 默认 0 |
| `structured_extraction_max_tokens` | 限制批处理成本 |

边界：

- `IntelService.extract_facts_from_document()` 只能依赖该接口执行结构化事实抽取。
- 如果用户希望结构化抽取复用主 LLM 服务，必须显式把 `structured_extraction_*` 配置成同一服务；系统不隐式回退。
- Agent 问答和报告撰写继续使用 `LLMClientProtocol`。
- Phase 3 的 LLM-as-Judge 可另建 `JudgeClientProtocol`，不要复用结构化抽取接口。

### 9.2 `IntelStoreProtocol`

新增到 `core/protocols.py`。

```python
class IntelStoreProtocol(Protocol):
    def save_fact(self, fact: IntelFact) -> IntelFact: ...
    def get_fact(self, fact_id: str) -> IntelFact | None: ...
    def list_facts(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IntelFact]: ...
    def update_fact_status(self, fact_id: str, status: str) -> IntelFact: ...
    def delete_fact(self, fact_id: str) -> None: ...

    def link_fact_to_competitor(
        self,
        fact_id: str,
        competitor_id: int,
        relation_type: str = "subject",
        confidence_score: float = 1.0,
    ) -> None: ...
    def unlink_fact_from_competitor(
        self,
        fact_id: str,
        competitor_id: int,
        relation_type: str | None = None,
    ) -> None: ...
    def link_fact_to_product(
        self,
        fact_id: str,
        product_id: int,
        relation_type: str = "subject",
        confidence_score: float = 1.0,
    ) -> None: ...

    def save_evidence(self, evidence: EvidenceRef) -> EvidenceRef: ...
    def list_evidence(self, owner_type: str, owner_id: str) -> list[EvidenceRef]: ...
```

### 9.3 `InsightStoreProtocol`

```python
class InsightStoreProtocol(Protocol):
    def save_claim(self, claim: InsightClaim) -> InsightClaim: ...
    def get_claim(self, claim_id: str) -> InsightClaim | None: ...
    def list_claims(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InsightClaim]: ...
    def update_claim_status(self, claim_id: str, status: str) -> InsightClaim: ...
    def delete_claim(self, claim_id: str) -> None: ...
    def attach_evidence(self, claim_id: str, evidence: EvidenceRef) -> EvidenceRef: ...
```

### 9.4 现有 Protocol 调整

| Protocol | 调整 |
|---|---|
| `CompetitorStoreProtocol` | 删除文档级 `get_intel_ids_for_competitor`，新增 fact 聚合查询或改由 `IntelStoreProtocol` 完成 |
| `ReportStoreProtocol` | Phase 2 不继续扩展旧 `source_refs` 形态；Phase 3 重写为 claim/evidence 驱动接口 |
| `DocumentStoreProtocol` | 增加按 `parent_chunk_id` 获取单个父块的便利方法，可选 |

---

## 10. Infrastructure 实现计划

### 10.1 `infrastructure/intel_store.py`

实现 `PostgresIntelStore`：

- 不在初始化时执行 DDL。
- 所有 JSONB 字段统一 `json.dumps(..., ensure_ascii=False)`。
- `list_facts(filters)` 支持以下过滤：
  - `competitor_id`
  - `product_id`
  - `fact_type`
  - `dimension`
  - `status`
  - `event_date_from`
  - `event_date_to`
  - `source_document_id`
  - `keyword`
- `save_fact()` 支持 insert/update。
- `save_fact()` 不自动创建 evidence；evidence 由服务层校验并保存。
- 删除 fact 时级联删除 fact 关联和其 evidence。

### 10.2 `infrastructure/insight_store.py`

实现 `PostgresInsightStore`：

- `list_claims(filters)` 支持 `competitor_id`、`claim_type`、`dimension`、`status`、`fact_id`。
- `save_claim()` 支持 insert/update。
- `active` claim 的强校验放在服务层，Store 只保证基础持久化。

---

## 11. 服务层重构计划

服务层是业务功能实现的位置。Agent 工具、Delivery API、Scheduler 任务都必须调用服务层，不直接操作 Store 完成业务逻辑。

### 11.1 `IntelService`

新增 `services/intel_service.py`。

职责：

1. 从 `SourceDocument` 和父块抽取结构化事实。
2. 基于规则和 `StructuredExtractionClientProtocol` 归因竞品/产品。
3. 保存 fact、fact links、evidence。
4. 提供结构化查询。
5. 处理幂等、缓存、状态转换和审计事件。

建议接口：

```python
class IntelService:
    def extract_facts_from_document(
        self,
        document_id: str,
        *,
        extraction_version: str = "intel_fact_v1",
        force: bool = False,
    ) -> dict: ...

    def create_fact(
        self,
        data: dict,
        *,
        created_by: str = "user",
    ) -> IntelFact: ...

    def update_fact(
        self,
        fact_id: str,
        data: dict,
        *,
        updated_by: str = "user",
    ) -> IntelFact | None: ...

    def get_fact_detail(self, fact_id: str) -> dict | None: ...

    def list_facts(
        self,
        filters: dict[str, Any],
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]: ...

    def link_fact_to_competitor(
        self,
        fact_id: str,
        competitor_id: int,
        relation_type: str = "subject",
        confidence_score: float = 1.0,
    ) -> None: ...

    def attach_evidence(
        self,
        owner_type: str,
        owner_id: str,
        evidence_data: dict,
    ) -> EvidenceRef: ...
```

抽取规则：

- 输入应优先使用 `DocumentStore.get_parent_chunks_by_ids()` 或按文档列出父块。
- 结构化抽取客户端输出必须是 JSON；解析失败时记录 `task_events`，不得创建半结构化事实。
- 事实抽取不得直接调用 `LLMClientProtocol`，必须走 `StructuredExtractionClientProtocol`，以便用户配置低价模型。
- 同一 `source_document_id + extraction_version` 可用 Redis 缓存抽取结果。
- `dedupe_key` 由 `source_document_id + fact_type + subject + predicate + object + event_date` 生成。
- 若未找到证据父块，不创建 `active` fact，只允许创建 `draft` fact。

### 11.2 `InsightService`

新增 `services/insight_service.py`。

职责：

1. 从 fact 列表创建 claim。
2. 对 claim 做基础规则校验。
3. 提供 claim 查询、状态变更、证据绑定。
4. 为 Phase 3 `ReportService` 提供 claim 上下文。

建议接口：

```python
class InsightService:
    def create_claim(
        self,
        data: dict,
        *,
        created_by: str = "user",
    ) -> InsightClaim: ...

    def get_claim_detail(self, claim_id: str) -> dict | None: ...

    def list_claims(
        self,
        filters: dict[str, Any],
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]: ...

    def build_claims_from_facts(
        self,
        filters: dict[str, Any],
        *,
        max_claims: int = 10,
    ) -> list[InsightClaim]: ...

    def validate_claim_evidence(self, claim_id: str) -> dict: ...
```

Phase 2 的 `validate_claim_evidence()` 只做规则校验：

- claim 至少有一个 fact 或 evidence。
- claim 中的竞品 ID 必须存在。
- claim 的 evidence 能回查到原文父块或 URL。

LLM-as-Judge 留到 Phase 3。

### 11.3 `CompetitorService` 调整

当前 `CompetitorService` 仍大量通过 `ArticleStore` 获取关联情报。第二阶段直接移除这条依赖：

- 新增 `get_competitor_fact_profile(competitor_id, filters)`，返回竞品、产品线、近期 facts、按 dimension 聚合。
- 新增 `compare_competitor_facts(competitor_ids, dimensions, time_window)`，返回结构化对比数据。
- 删除 `auto_link_articles()`，新增 `auto_link_documents()` 和 `auto_link_facts()`。
- 竞品档案工具只使用 `IntelService` / `IntelStore` 和竞品主数据，不再补查旧 `ArticleStore`。

### 11.4 `PipelineService` 调整

阶段命名从：

```text
summary
```

调整为：

```text
extract_intel_facts
```

执行顺序建议：

```text
collect
-> markdown
-> store_source_documents
-> chunk_and_vectorize
-> extract_intel_facts
-> link_facts
```

说明：

- 事实抽取应依赖父块证据，因此建议在分块后执行。
- 如果为了成本先做文档级抽取，也必须在 fact evidence 中绑定到可回查的父块。
- 原 `summary_service.summarize_pending()` 删除；可复用的批处理、JSON 修复或 prompt 模板代码迁移到 `StructuredExtractionService` 并更名。

### 11.5 `ReportService` 预留

Phase 2 新增轻量 `services/report_service.py` 也可以接受，但只做上下文聚合，不做完整报告质量门禁。

建议接口：

```python
class ReportService:
    def build_report_context(
        self,
        competitor_ids: list[int],
        *,
        dimensions: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        focus: str = "",
    ) -> dict: ...
```

返回：

- competitors
- products
- facts
- claims
- evidence_refs
- limitations

`generate_analysis_report` 工具 Phase 2 调用该接口获取上下文，再调用主 `LLMClientProtocol` 生成报告草稿。旧工具内直接拼接文章摘要的逻辑删除；Phase 3 再切换为 claim -> report -> quality gate。

---

## 12. Agent 工具边界

### 12.1 权限原则

Agent 允许通过白名单工具修改业务数据，但必须满足：

- 只能调用服务层方法。
- 不能传入表名。
- 不能执行 SQL。
- 不能创建、删除、修改表结构。
- 所有写操作必须记录 `created_by='agent'` 或审计事件。
- 危险操作使用软删除或状态变更，避免物理删除。

### 12.2 工具实现方式：注册表 + 工厂类

第二阶段工具实现改为 **工具定义注册表 + 工厂类**，不要继续在 `agent/tools/builtin/__init__.py` 中手写一长串 import、依赖判断和实例构造。

目标结构：

```text
agent/tools/
  builtin/
    definitions.py        # 工具定义注册表
    factory.py            # BuiltinToolFactory
    specs.py              # ToolSpec / dependency metadata
    search_evidence.py
    query_intel_facts.py
    create_intel_fact.py
    ...
```

核心对象：

| 对象 | 职责 |
|---|---|
| `ToolSpec` | 声明工具名、工具类、所需服务依赖、是否默认启用、废弃状态 |
| `ToolDefinitionRegistry` | 保存所有内置工具定义；支持按名称、标签、启用状态枚举 |
| `BuiltinToolFactory` | 从 `ConfigManager` / `ServiceRegistry` 解析依赖并创建 `BaseTool` 实例 |
| `register_builtin_tools()` | 只负责读取定义、调用工厂、注册到运行时 `ToolRegistry` |

建议接口：

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    tool_cls: type[BaseTool]
    dependencies: tuple[str, ...]
    enabled_by_default: bool = True
    tags: tuple[str, ...] = ()
    replacement_for: tuple[str, ...] = ()
    removed: bool = False


class ToolDefinitionRegistry:
    def register(self, spec: ToolSpec) -> None: ...
    def list_specs(self, include_removed: bool = False) -> list[ToolSpec]: ...
    def active_tool_names(self) -> list[str]: ...
    def get(self, name: str) -> ToolSpec | None: ...


class BuiltinToolFactory:
    def __init__(self, service_registry: ServiceRegistry): ...
    def create(self, spec: ToolSpec) -> BaseTool | None: ...
```

依赖解析规则：

- 工具只能声明 service 级依赖，例如 `intel_service`、`insight_service`、`competitor_service`、`report_service`、`evidence_search_service`、`web_search_service`。
- 工具不得声明 Store、数据库连接、Qdrant、Redis、LLM client 等底层依赖。
- 缺少必需依赖时，工厂跳过该工具并记录结构化日志，不在工具类里降级拼装。
- 已删除的旧工具不保留 `ToolSpec` 占位；定义注册表只描述当前 active 工具。

`agent/tools/builtin/__init__.py` 的目标形态：

```python
def register_builtin_tools(config_manager: ConfigManager, *, refresh: bool = True) -> int:
    service_registry = config_manager.service_registry
    definition_registry = get_builtin_tool_definition_registry()
    factory = BuiltinToolFactory(service_registry)
    runtime_registry = get_tool_registry()

    if refresh:
        runtime_registry.unregister_many(definition_registry.active_tool_names())

    registered = 0
    for spec in definition_registry.list_specs():
        tool = factory.create(spec)
        if tool is not None:
            runtime_registry.register(tool)
            registered += 1
    return registered
```

验收要求：

- 所有 active 工具都必须通过工具类 + `ToolSpec` 注册，不修改集中式依赖拼装代码。
- `register_builtin_tools()` 不直接访问 `article_store`、`competitor_store`、`llm_client` 等具体属性。
- 测试可断言旧工具名不存在于定义注册表和运行时 `ToolRegistry`。
- 测试可断言保留名称的 active 工具由 `BuiltinToolFactory` 创建，且构造参数只来自 `ServiceRegistry`。

### 12.3 旧工具删除、更名与复用

| 当前工具 | Phase 2 处理 |
|---|---|
| `query_knowledge_base` | 删除工具定义与实现；使用 `search_evidence` | 旧名仍带“知识库查询”泛义，不足以表达“原文证据检索” |
| `read_article` | 删除工具定义与实现；使用 evidence/source document 语义工具 | 旧名绑定 article，不符合统一 SourceDocument |
| `get_recent_news` | 删除工具定义与实现；使用 `query_intel_facts` | news 列表不再是分析主入口 |
| `get_news_stats` | 删除工具定义与实现；后续如需统计以 fact/dashboard service 重建 | 旧统计口径基于 article |
| `generate_brief` | 删除工具定义与实现；使用 `generate_analysis_report` | brief 是旧命名 |
| `web_search` | 重构为 `ToolSpec(name="web_search", dependencies=("web_search_service",))` | 名称准确，不更名；实现必须改为工厂创建和 service 依赖 |
| `list_competitors` | 重构为 `ToolSpec(name="list_competitors", dependencies=("competitor_service",))` | 名称准确，仍是竞品主数据原子查询 |
| `get_competitor_profile` | 重构为 `ToolSpec(name="get_competitor_profile", dependencies=("competitor_service",))`，输出 facts/events 聚合 | 名称准确，输出语义升级 |
| `compare_competitors` | 重构为 `ToolSpec(name="compare_competitors", dependencies=("competitor_service",))`，基于 facts/events 对比 | 名称准确，业务能力仍是竞品对比 |
| `generate_analysis_report` | 重构为 `ToolSpec(name="generate_analysis_report", dependencies=("report_service",))` | 名称准确；删除工具内旧文章摘要拼接逻辑 |

保留名称不代表保留实现。以上工具必须删除旧构造方式，统一改为注册表声明、工厂类实例化、服务层实现业务逻辑。

### 12.4 新增原子工具

#### `search_evidence`

用途：走父子分块 RAG 检索原文证据。

参数：

- `query: string`
- `top_k: integer = 5`
- `competitor_ids: array = []`
- `document_type: string = ""`
- `date_from/date_to: string = ""`

返回：

- `source_document_id`
- `parent_chunk_id`
- `title`
- `url`
- `snippet/content`
- `score`

#### `query_intel_facts`

用途：查结构化事实，不做语义 RAG。

参数：

- `competitor_ids`
- `product_ids`
- `fact_type`
- `dimension`
- `date_from`
- `date_to`
- `status`
- `limit`

返回：

- fact ID
- fact_text
- fact_type
- dimension
- competitors
- products
- event_date
- importance/confidence
- evidence count

#### `get_intel_fact`

用途：获取单条事实详情。

参数：

- `fact_id`

返回：

- fact 全字段
- competitors/products
- evidence_refs
- source document metadata

#### `create_intel_fact`

用途：Agent 创建人工或推理得到的 draft fact。

参数：

- `source_document_id`
- `parent_chunk_id`
- `fact_kind`
- `fact_type`
- `dimension`
- `subject`
- `predicate`
- `object`
- `fact_text`
- `attributes`
- `event_date`
- `competitor_ids`
- `product_ids`
- `evidence_snippet`
- `confidence_score`

规则：

- 默认 `status='draft'`。
- 必须提供 evidence。
- 不能直接创建 `active` fact。

#### `update_intel_fact`

用途：修改 draft fact 或补充属性。

参数：

- `fact_id`
- 允许更新字段白名单：`fact_type`、`dimension`、`subject`、`predicate`、`object`、`fact_text`、`attributes`、`event_date`、`importance_score`、`confidence_score`、`status`

规则：

- `status` 只能在 `draft/rejected/archived` 之间变更；`active` 需要人工或质量流程，Phase 2 不给 Agent 自动激活权限。

#### `link_fact_to_competitor`

用途：事实归因到竞品。

参数：

- `fact_id`
- `competitor_id`
- `relation_type`
- `confidence_score`

#### `link_fact_to_product`

用途：事实归因到产品线。

参数：

- `fact_id`
- `product_id`
- `relation_type`
- `confidence_score`

#### `create_insight_claim`

用途：Agent 基于 facts 创建 draft claim。

参数：

- `claim_text`
- `claim_type`
- `dimension`
- `competitor_ids`
- `product_ids`
- `fact_ids`
- `limitations`
- `confidence_score`

规则：

- 默认 `status='draft'`。
- 至少一个 `fact_id`。

#### `query_insight_claims`

用途：按竞品、维度、类型查询 claims。

参数：

- `competitor_ids`
- `claim_type`
- `dimension`
- `status`
- `limit`

### 12.5 不提供的工具

明确禁止：

- `run_sql`
- `alter_table`
- `create_table`
- `drop_table`
- `migrate_database`
- 通用 `crud_table(table_name, data)`
- 任何可传入任意表名和任意字段的工具

如果后续需要“表格数据编辑”体验，应做成有限领域工具，例如 `create_competitor`、`update_product`、`create_intel_fact`，而不是通用表工具。

---

## 13. API 路由计划

Phase 2 可新增后端 API，前端是否接入可分步。

### 13.1 `/api/intel/facts`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/intel/facts` | GET | 查询 facts |
| `/api/intel/facts` | POST | 创建 fact |
| `/api/intel/facts/{fact_id}` | GET | 获取 fact 详情 |
| `/api/intel/facts/{fact_id}` | PUT | 更新 fact |
| `/api/intel/facts/{fact_id}/status` | PATCH | 更新状态 |
| `/api/intel/facts/{fact_id}/competitors` | POST | 关联竞品 |
| `/api/intel/facts/{fact_id}/products` | POST | 关联产品 |
| `/api/intel/facts/{fact_id}/evidence` | GET/POST | 查看/新增证据 |

### 13.2 `/api/insights/claims`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/insights/claims` | GET | 查询 claims |
| `/api/insights/claims` | POST | 创建 claim |
| `/api/insights/claims/{claim_id}` | GET | 获取 claim 详情 |
| `/api/insights/claims/{claim_id}` | PUT | 更新 claim |
| `/api/insights/claims/{claim_id}/validate` | POST | 基础证据校验 |

### 13.3 现有 `/api/competitors`

新增：

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/competitors/{id}/facts` | GET | 竞品结构化事实 |
| `/api/competitors/{id}/timeline` | GET | 竞品事件时间线 |
| `/api/competitors/compare/facts` | POST | 基于 facts 的对比 |

删除旧 `/api/competitors/{id}/intel` 文章口径端点，使用 `/api/competitors/{id}/facts` 和 `/api/competitors/{id}/timeline`。

---

## 14. Pipeline 改造细节

### 14.1 旧流程

```text
collect
-> markdown
-> store_articles
-> summary
-> competitor_link
-> vectorize
```

### 14.2 新流程

```text
collect
-> markdown
-> store_source_documents
-> chunk_and_vectorize
-> extract_intel_facts
-> link_facts
```

### 14.3 阶段行为

#### `chunk_and_vectorize`

保持第一阶段逻辑：

- `SourceDocument`
- `ParentDocumentChunk`
- `ChildChunkPoint`
- Qdrant upsert
- `document_vector_points` 状态

#### `extract_intel_facts`

新增：

- 读取文档父块。
- 按父块或文档窗口调用结构化抽取 AI 接口抽取 JSON facts。
- 为每条 fact 绑定 `parent_chunk_id` 和 snippet。
- 保存 `intel_facts` 和 `evidence_refs`。
- 生成 `dedupe_key` 并去重。

#### `link_facts`

新增：

- 基于竞品名称、aliases、产品名称规则匹配。
- 对高价值事实可调用结构化抽取 AI 接口二次确认；复杂判断留给 Phase 3 Judge。
- 写入 `intel_fact_competitors`、`intel_fact_products`。
- 同步更新 `source_documents.competitor_ids/product_ids` 作为文档级粗索引。

### 14.4 旧摘要链路删除策略

旧 `SummaryService` 不保留为运行路径：

- 如果其中有可复用的批处理、速率控制、JSON 清洗或 prompt 模板代码，迁移到 `StructuredExtractionService` 并更名。
- 如果只服务 `articles.summary`，直接删除。
- 旧 `summary` 阶段不再作为 Celery/Pipeline 阶段出现。

前端如仍需要列表展示摘要，应读取 `intel_facts.fact_text` 或由 facts 聚合服务生成展示 DTO，不恢复 `articles.summary`。

---

## 15. Factory 与 ConfigManager

### 15.1 新增工厂函数

`core/factory.py` 新增：

- `create_structured_extraction_client(config)`
- `create_intel_store(config)`
- `create_insight_store(config)`
- `create_intel_service(config, mgr)`
- `create_insight_service(config, mgr)`
- `create_report_service(config, mgr)` 可选
- `create_service_registry(config, mgr)`
- `create_builtin_tool_definition_registry()`
- `create_builtin_tool_factory(service_registry)`

### 15.2 ServiceRegistry

新增轻量 `ServiceRegistry`，用于工具工厂按名称解析服务依赖。它不是通用 DI 容器，只暴露 Phase 2 工具允许使用的服务白名单。

建议接口：

```python
class ServiceRegistry:
    def get(self, name: str) -> Any | None: ...
    def require(self, name: str) -> Any: ...
    def has(self, name: str) -> bool: ...
```

白名单服务：

- `intel_service`
- `insight_service`
- `competitor_service`
- `report_service`
- `evidence_search_service`
- `web_search_service`

禁止把以下对象放入工具可解析白名单：

- PostgreSQL Store
- Qdrant VectorIndex
- RedisStateStore
- LLMClient
- StructuredExtractionClient
- 原始 Config 对象

这些底层对象只能由 service 层持有，工具不能直接访问。

### 15.3 ConfigManager 属性

新增缓存属性：

- `structured_extraction_client`
- `intel_store`
- `insight_store`
- `intel_service`
- `insight_service`
- `report_service`
- `service_registry`
- `builtin_tool_definition_registry`
- `builtin_tool_factory`

reload 规则：

- PostgreSQL DSN 变化，清空 intel/insight store 和相关 service。
- 结构化抽取模型、base URL 或 API key 变化，清空 `structured_extraction_client` 和 `intel_service`。
- 主 LLM 配置变化，清空 `insight_service`、`report_service` 和 Agent 相关工具；不影响 `structured_extraction_client`，除非用户显式把结构化抽取配置指向同一服务。
- Redis 配置变化，只清空 service 中的缓存能力，不影响 Store。
- 任何 service 缓存失效时，同步清空 `service_registry` 和 `builtin_tool_factory`。

### 15.4 Tool 注册

工具注册改为使用定义注册表和工厂类，不再从 ConfigManager 逐个取 service 手写构造：

```text
ToolDefinitionRegistry
  -> ToolSpec(name="search_evidence", tool_cls=SearchEvidenceTool, dependencies=("evidence_search_service",))
  -> ToolSpec(name="query_intel_facts", tool_cls=QueryIntelFactsTool, dependencies=("intel_service",))
  -> ToolSpec(name="create_intel_fact", tool_cls=CreateIntelFactTool, dependencies=("intel_service",))

BuiltinToolFactory(ServiceRegistry)
  -> create(spec)
  -> BaseTool instance

ToolRegistry
  -> register(tool)
```

`register_builtin_tools()` 不再知道每个工具的构造参数；它只遍历 `ToolDefinitionRegistry` 的 active specs，并委托 `BuiltinToolFactory` 创建实例。

---

## 16. 审计与状态

### 16.1 写操作审计

每个 Agent 写操作至少记录：

- `actor = agent`
- `tool_name`
- `operation`
- `target_type`
- `target_id`
- `before` 可选
- `after` 或变更摘要
- `session_id` / `run_id` 可用时写入

短期可写入 `analysis_audit_log`，长期建议 Phase 3 或 Phase 4 抽成通用 `audit_log`。

### 16.2 状态策略

| 对象 | Agent 可创建状态 | Agent 可直接激活 |
|---|---|---|
| `IntelFact` | `draft` | 否 |
| `InsightClaim` | `draft` | 否 |
| `Competitor` | `active` | 是，因属于主数据 CRUD |
| `Product` | active implicit | 是 |

原因：

- 竞品/产品主数据的错误容易人工修正。
- fact/claim 会影响报告可信度，Agent 创建后应等待质量流程或人工确认。

---

## 17. 测试计划

### 17.1 Migration 测试

- 空库执行 migration 成功。
- 新表、外键、索引存在。
- `confidence_score` 范围约束有效。
- 删除 `source_documents` 后相关 facts/evidence 行为符合设计。

### 17.2 Store 测试

- `PostgresIntelStore.save_fact/get_fact/list_facts/update_fact_status/delete_fact`
- fact 与 competitor/product link 增删。
- evidence 保存和按 owner 查询。
- `PostgresInsightStore.save_claim/list_claims/update_claim_status`
- filters 覆盖 competitor、dimension、fact_type、date window、status。

### 17.3 Service 测试

- `IntelService.create_fact()` 缺 evidence 时只能创建 draft 或返回校验错误。
- `IntelService.extract_facts_from_document()` 对结构化抽取 JSON 解析失败不写半成品。
- `IntelService.extract_facts_from_document()` 调用 `StructuredExtractionClientProtocol`，不得调用主 `LLMClientProtocol`。
- 相同 `source_document_id + extraction_version` 重跑不会重复创建事实。
- `InsightService.create_claim()` 无 fact/evidence 时拒绝 active claim。
- `CompetitorService.get_competitor_fact_profile()` 返回聚合事实而不是旧文章摘要。

### 17.4 Tool 测试

- 每个工具只调用对应 service。
- 工具参数 schema 不包含 `table_name`、`sql`、`ddl` 等字段。
- Agent 创建 fact 默认 `status=draft`。
- `query_intel_facts` 不调用 Qdrant。
- `search_evidence` 调用 RAG 检索，不查询 facts 表作为主路径。
- `ToolDefinitionRegistry` 包含所有 active 工具和 removed 旧工具定义。
- `BuiltinToolFactory` 只从 `ServiceRegistry` 解析 service 依赖，不直接读取 Store、LLM、Qdrant 或 Redis。
- 缺少必需 service 时，工厂跳过工具并记录日志。
- `register_builtin_tools()` 不包含工具级 if/else 依赖拼装逻辑。
- `web_search`、`list_competitors`、`get_competitor_profile`、`compare_competitors`、`generate_analysis_report` 这些保留名称的旧工具也必须有 active `ToolSpec`，并由工厂创建。
- 保留名称的旧工具构造函数不得再接收 Store、LLM client、ConfigManager 或底层基础设施对象。

### 17.5 Pipeline 回归

- 新文章仍可进入 SourceDocument、父子分块、Qdrant。
- `extract_intel_facts` 能为文档生成 facts 和 evidence。
- 结构化抽取模型配置为低价模型时，Pipeline 事实抽取使用该配置。
- Redis 缓存不可用时，抽取仍可执行并写 PostgreSQL。
- 删除旧 `articles.summary` 后不影响 fact 抽取。

---

## 18. 实施步骤

### Step 1：落定命名和文档

产物：

- 本计划文档。
- 更新 `enterprise-ai-competitor-analysis-plan.md` 中 Phase 2 摘要，将 `IntelItem` 解释为 `IntelFact/IntelEvent`。
- 更新 `docs/design-docs/protocol-contracts.md`，加入 Intel/Insight Store 契约。

验收：

- 文档明确 RAG 与 fact 层不重复。
- 文档明确 Agent 禁止 DDL 和任意 SQL。

### Step 2：新增 migration

产物：

- `migrations/004_intel_fact_schema.sql`

验收：

- 空库可执行。
- 所有新表、索引、约束存在。
- 不修改 Qdrant collection 设计。

### Step 3：新增模型

产物：

- `models/intel.py`
- `models/evidence.py`
- `models/insight.py`
- `models/report.py` 删除旧 `SourceRef.intel_id = articles.id` 语义

验收：

- dataclass 无 I/O 依赖。
- 枚举值覆盖计划中的 fact_type、dimension、claim_type。

### Step 4：新增结构化抽取接口、Protocol 和 Store

产物：

- `core/protocols.py`
- `infrastructure/structured_extraction_client.py` 或复用现有 LLM client 适配代码后更名为结构化抽取客户端
- `infrastructure/intel_store.py`
- `infrastructure/insight_store.py`

验收：

- 结构化抽取客户端可独立配置 provider/model/base_url/api_key。
- Store 不执行 DDL。
- JSONB 编解码稳定。
- 单元测试覆盖 CRUD 和 filters。

### Step 5：新增服务层

产物：

- `services/service_registry.py` 或 `core/service_registry.py`
- `services/intel_service.py`
- `services/insight_service.py`
- `services/report_service.py` 可选轻量版
- `services/competitor_service.py` 增加 fact 聚合接口

验收：

- 业务校验在 service，不在 tool。
- Service 可被 Delivery、Scheduler、Agent 工具复用。
- `ServiceRegistry` 只暴露工具允许依赖的 service 白名单。

### Step 6：改造 Pipeline

产物：

- `services/pipeline_service.py`
- `scheduler/tasks.py` 如有必要

验收：

- 任务阶段包含 `extract_intel_facts` 和 `link_facts`。
- 旧 summary 阶段被删除。
- 事实抽取使用结构化抽取客户端。

### Step 7：新增 Agent 原子工具

产物：

- `agent/tools/builtin/specs.py`
- `agent/tools/builtin/definitions.py`
- `agent/tools/builtin/factory.py`
- `agent/tools/builtin/__init__.py` 简化为注册表遍历入口
- `agent/tools/builtin/search_evidence.py`
- `agent/tools/builtin/query_intel_facts.py`
- `agent/tools/builtin/get_intel_fact.py`
- `agent/tools/builtin/create_intel_fact.py`
- `agent/tools/builtin/update_intel_fact.py`
- `agent/tools/builtin/link_fact_to_competitor.py`
- `agent/tools/builtin/link_fact_to_product.py`
- `agent/tools/builtin/create_insight_claim.py`
- `agent/tools/builtin/query_insight_claims.py`

验收：

- 工具原子化。
- 工具调用 service。
- 工具无任意 SQL/DDL 能力。
- 工具通过 `ToolSpec` 注册到 `ToolDefinitionRegistry`。
- 工具实例由 `BuiltinToolFactory` 创建。
- `agent/tools/builtin/__init__.py` 只负责遍历注册表并注册运行时工具。
- 旧 `query_knowledge_base`、`get_recent_news`、`get_news_stats`、`read_article`、`generate_brief` 的工具定义和实现均删除，不再注册。

### Step 8：按注册表和工厂类重构保留名称的旧工具

产物：

- `web_search` 改为 `WebSearchTool(web_search_service)`，通过 active `ToolSpec` 注册。
- `list_competitors` 改为 `ListCompetitorsTool(competitor_service)`，通过 active `ToolSpec` 注册。
- `get_competitor_profile` 改为 `GetCompetitorProfileTool(competitor_service)`，内部调用 `CompetitorService.get_competitor_fact_profile()`。
- `compare_competitors` 改为 `CompareCompetitorsTool(competitor_service)`，内部调用 fact 聚合接口。
- `generate_analysis_report` 改为 `GenerateAnalysisReportTool(report_service)`，内部调用 `ReportService.build_report_context()`。

验收：

- 所有保留名称的旧工具都由 `BuiltinToolFactory` 创建。
- 所有保留名称的旧工具都只接收 service 依赖。
- 输出中引用 fact/evidence，而不是只引用 article summary。
- 旧文章摘要拼接逻辑删除。

### Step 9：新增 API

产物：

- `delivery/api/intel_router.py`
- `delivery/api/insight_router.py`
- `delivery/api/competitor_router.py` 扩展 facts/timeline。

验收：

- API 可查询和创建 draft facts/claims。
- 旧 article/news 口径的 intel 端点被删除或重建为 fact 口径端点。

### Step 10：测试与文档收尾

产物：

- 新增 tests。
- 更新 `ARCHITECTURE.md`、`docs/flows/query-flow.md`、`docs/flows/pipeline-flow.md`。

验收：

- `pytest tests/` 通过，或至少核心新增测试通过。
- 文档中的 Agent 工具列表与注册实现一致。

---

## 19. 验收标准

第二阶段完成的硬性标准：

1. PostgreSQL 有 `intel_facts`、`evidence_refs`、`insight_claims` 及关联表。
2. 新文章或新文档可以生成结构化事实，并且每条事实能回链父块证据。
3. RAG 检索仍走 Qdrant 子块 + PostgreSQL 父块，不被 fact 表替代。
4. Agent 可以查询 evidence、查询 facts、创建 draft fact、创建 draft claim、维护事实关联。
5. Agent 没有任何表结构修改能力。
6. 竞品档案和对比工具优先使用 facts/events 聚合，而不是旧文章摘要。
7. `generate_analysis_report` 的上下文准备逻辑迁出 Tool，至少由服务层提供接口。
8. 旧 `articles.summary`、旧 news 工具、旧 brief 工具从 Phase 2 运行路径删除。
9. 结构化事实抽取使用独立 AI 接口，并能配置低价模型。

---

## 20. 风险与取舍

| 风险 | 说明 | 处理 |
|---|---|---|
| Fact schema 过细 | 字段过多会拖慢实现 | 先实现通用 `subject/predicate/object/attributes`，细分表后续再加 |
| 结构化抽取不稳定 | JSON 解析失败、事实重复、归因错误 | Prompt 版本化、dedupe_key、draft 状态、证据强约束 |
| 低价模型质量不足 | 便宜模型可能漏抽或错抽事实 | 默认 draft、抽取版本化、重要事实可二次确认 |
| 与 RAG 边界再次混淆 | 团队可能继续把 fact 当摘要索引 | 文档和工具命名使用 `fact/event/evidence`，避免 `summary search` |
| Agent 写入污染数据 | Agent 可能创建错误事实 | 默认 draft、审计、禁止自动 active |
| 删除旧 article summary 影响 UI | 一次性迁移会暴露前端旧依赖 | 前端同步改为读取 facts/timeline DTO，不恢复旧 summary |
| ReportService 范围膨胀 | Phase 2 可能滑向 Phase 3 | Phase 2 只做上下文聚合，不做质量门禁 |

---

## 21. 推荐优先级

P0：

1. 新增 fact/evidence/claim schema。
2. 新增独立结构化抽取客户端及低价模型配置。
3. 新增 IntelStore、InsightStore。
4. 新增 IntelService、InsightService。
5. Pipeline 生成 facts 并绑定 evidence。
6. Agent 新增 `search_evidence`、`query_intel_facts`、`get_intel_fact`。

P1：

1. Agent 写工具：`create_intel_fact`、`update_intel_fact`、`link_fact_to_competitor`、`create_insight_claim`。
2. 竞品档案和对比工具改为 fact 聚合。
3. API 新增 `/api/intel/facts` 和 `/api/insights/claims`。

P2：

1. ReportService 上下文聚合。
2. 自动 fact 去重和多来源合并。
3. 前端 Intel facts 列表、事件时间线和人工复核入口。

---

## 22. 最小可行版本

如果第二阶段只做一轮，最小闭环建议：

1. 建 `intel_facts`、`evidence_refs`、`intel_fact_competitors`。
2. 实现 `StructuredExtractionClientProtocol`，支持独立低价模型配置。
3. 实现 `IntelStoreProtocol` 和 `PostgresIntelStore`。
4. 实现 `IntelService.create_fact/list_facts/get_fact_detail/extract_facts_from_document`。
5. Pipeline 在向量化后生成 facts。
6. Agent 增加 `search_evidence`、`query_intel_facts`、`get_intel_fact`。
7. `get_competitor_profile` 返回最近 facts，而不是旧 articles。

这 6 项完成后，系统就具备了区别于 RAG 的结构化业务事实层：RAG 继续找原文，Fact 层负责业务事实、过滤、聚合和后续报告 claim。
