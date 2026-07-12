# Protocol 接口契约详细设计

> 来源：从 [ARCHITECTURE.md](../../ARCHITECTURE.md) §5 迁出的 Protocol 设计文档。

系统通过 `typing.Protocol` 定义接口契约。基础设施实现必须在 `infrastructure/` 内部消化具体 SDK 类型，不向 Services、Agent 或 Delivery 层泄露。

---

## 1. DocumentStoreProtocol

`DocumentStoreProtocol` 是 PostgreSQL 权威文档层，负责 `source_documents`、`document_parent_chunks` 和 `document_vector_points`。

```python
class DocumentStoreProtocol(Protocol):
    def save_document(self, document: SourceDocument) -> SourceDocument: ...
    def get_document(self, document_id: str) -> SourceDocument | None: ...
    def list_documents(self, filters: dict[str, Any] | None = None,
                       limit: int = 50, offset: int = 0) -> list[SourceDocument]: ...
    def update_parse_status(self, document_id: str, status: str,
                            error: dict[str, Any] | None = None) -> None: ...
    def save_parent_chunks(self, parent_chunks: list[ParentDocumentChunk]) -> int: ...
    def get_parent_chunks_by_ids(self, parent_chunk_ids: list[str]) -> list[ParentDocumentChunk]: ...
    def search_parent_chunks_by_keyword(self, query: str,
                                        top_k: int = 20,
                                        filters: dict[str, Any] | None = None) -> list[tuple[ParentDocumentChunk, float]]: ...
    def mark_points_vectorized(self, points: list[ChildChunkPoint]) -> None: ...
    def mark_points_vector_failed(self, point_ids: list[str],
                                  error: dict[str, Any] | str) -> None: ...
    def delete_document(self, document_id: str) -> None: ...
```

当前实现：`PostgresDocumentStore`。

存储边界：

- `source_documents` 保存统一来源文档 metadata 和标准化正文。
- `document_parent_chunks` 保存父块权威内容、`child_point_ids`、metadata 和 `search_vector`。
- `document_vector_points` 保存 Qdrant point 状态，不保存 embedding，不保存子块正文。

---

## 2. VectorIndexProtocol

`VectorIndexProtocol` 是 Qdrant-only 子块向量索引契约。

```python
class VectorIndexProtocol(Protocol):
    def healthcheck(self) -> bool: ...
    def ensure_collection(self) -> None: ...
    def recreate_collection(self) -> None: ...
    def upsert_child_chunks(self, chunks: list[ChildChunkPoint],
                            embeddings: list[list[float]]) -> int: ...
    def search_child_chunks(self, query_embedding: list[float],
                            top_k: int = 10,
                            filters: dict[str, Any] | None = None) -> list[ChildChunkSearchResult]: ...
    def delete_by_document_ids(self, document_ids: list[str]) -> None: ...
    def delete_by_point_ids(self, point_ids: list[str]) -> None: ...
```

当前实现：`QdrantVectorIndex`。

契约要求：

- collection 名称由配置 `qdrant_documents_collection` 决定，默认 `insightforge_documents_v1`。
- point id 使用 `{document_id}:c:{chunk_index}`。
- upsert 前校验 embedding 数量和维度。
- search 返回子块命中；调用方必须按 `parent_chunk_id` 召回 PostgreSQL 父块。
- Qdrant SDK 异常统一映射为项目基础设施异常。

---

## 3. 文档模型

当前文档 RAG 只使用 `models/document.py` 中的文档语义模型：

| 模型 | 说明 |
|---|---|
| `SourceDocument` | RSS、网页、上传、手工、API 输入的统一文档 |
| `ParentDocumentChunk` | PostgreSQL 父块，LLM 上下文和全文搜索单位 |
| `ChildChunkPoint` | Qdrant 子块 point payload 与 embedding 对应对象 |
| `ChildChunkSearchResult` | Qdrant 子块检索结果 |
| `HybridDocumentSearchResult` | RRF 后的父块检索结果 |

旧 article-only 的 `Chunk.article_id` / `ParentChunk.article_id` 不再作为新接口字段。

---

## 4. UploadStoreProtocol

`UploadStoreProtocol` 是 PostgreSQL 上传元数据权威层，负责 `upload_batches` 和 `document_blobs`。它只记录批次、文件对象、hash、状态和错误，不保存文件字节。

```python
class UploadStoreProtocol(Protocol):
    def create_batch(self, batch: UploadBatch) -> UploadBatch: ...
    def finish_batch(self, batch_id: str, status: str,
                     error: dict[str, Any] | None = None) -> UploadBatch: ...
    def save_blob(self, blob: DocumentBlob) -> DocumentBlob: ...
    def get_blob(self, blob_id: str) -> DocumentBlob | None: ...
    def list_blobs(self, batch_id: str) -> list[DocumentBlob]: ...
    def find_blobs_by_sha256(self, sha256: str) -> list[DocumentBlob]: ...
    def update_blob_status(self, blob_id: str, status: str,
                           error: dict[str, Any] | None = None) -> None: ...
```

当前实现：`PostgresUploadStore`。

契约要求：

- Store 不在初始化时创建 DDL，只操作 migration 已创建的表。
- `sha256` 用于重复文件识别，但不强制全局唯一；是否复用由上层摄入策略决定。
- 批次可进入 `succeeded`、`partial_failed` 或 `failed`，单个文件失败不得吞掉错误原因。

---

## 5. FileBlobStoreProtocol

`FileBlobStoreProtocol` 是文件字节存储抽象。当前实现为本地磁盘，后续可替换为 MinIO/S3。

```python
class FileBlobStoreProtocol(Protocol):
    def put(self, stream: BinaryIO,
            metadata: dict[str, Any] | None = None) -> StoredBlobResult: ...
    def open(self, blob_path: str) -> BinaryIO: ...
    def delete(self, blob_path: str) -> bool: ...
    def exists(self, blob_path: str) -> bool: ...
    def quarantine(self, blob_path: str, reason: str) -> str: ...
```

当前实现：`LocalFileBlobStore`。

契约要求：

- 文件按内容 hash 保存，原始文件名只作为 metadata。
- `open/delete/exists/quarantine` 必须校验路径在存储根目录内。
- 空文件、超限文件和路径逃逸必须拒绝。

---

## 6. ArchiveExtractorProtocol 与 FileTypeDetectorProtocol

```python
class ArchiveExtractorProtocol(Protocol):
    def can_extract(self, filename: str, content_type: str = "") -> bool: ...
    def extract(self, archive_path: str, output_dir: str,
                limits: dict[str, Any] | None = None) -> list[ExtractedFile]: ...

class FileTypeDetectorProtocol(Protocol):
    def detect(self, filename: str, content_type: str = "") -> FileTypeDetection: ...
```

当前实现：`ArchiveExtractor`、`FileTypeDetector`。

契约要求：

- 第一阶段只要求 zip 解包。
- 解包必须拒绝 zip slip、绝对路径、空文件、超文件数、超单文件大小和超总大小。
- PDF/DOCX 可被识别，但在解析器接入前返回 unsupported。

---

## 7. DocumentParserProtocol

`DocumentParserProtocol` 将已保存的 `DocumentBlob` 解析为标准化 Markdown/text，不直接写数据库。

```python
class DocumentParserProtocol(Protocol):
    def detect(self, blob: DocumentBlob) -> FileTypeDetection: ...
    def parse(self, blob: DocumentBlob) -> ParsedDocument: ...
```

当前实现：`DocumentParser`。

支持范围：

- TXT：转为带标题的文本 Markdown。
- MD/Markdown：保留 Markdown 正文。
- HTML/HTM：复用 HTML -> Markdown 语义转换能力。
- CSV/TSV：转为 Markdown 表格。
- ZIP：由 `ArchiveExtractor` 处理，不作为文档正文解析。
- PDF/DOCX：当前返回 unsupported，不伪装解析成功。

---

## 8. StructuredExtractionClientProtocol

`StructuredExtractionClientProtocol` 是结构化事实抽取专用 AI 接口。它与 Agent 问答和报告撰写使用的 `LLMClientProtocol` 分离，必须通过独立配置显式选择 provider、model、base URL 和 API key；系统不隐式回退到主 LLM。

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

当前实现：`infrastructure.structured_extraction_client` 中的各 provider 适配器。

---

## 10. IntelStoreProtocol

`IntelStoreProtocol` 是结构化事实、事实归因和证据引用的 PostgreSQL 契约。Store 不执行 DDL，不做业务状态强校验；active 状态、证据完整性和 Agent 权限由 Service 层负责。

> **目标差异**：以下签名描述当前实现。ADR-0002 的目标契约将删除关联 `confidence_score`，以独立 fact-evidence 关系替代 `owner_type/owner_id`，并增加不可变激活、显式取代和保守事实解析能力。迁移目标见 [structured-intelligence-model.md](structured-intelligence-model.md)。

```python
class IntelStoreProtocol(Protocol):
    def save_fact(self, fact: IntelFact) -> IntelFact: ...
    def get_fact(self, fact_id: str) -> IntelFact | None: ...
    def list_facts(self, filters: dict[str, Any] | None = None,
                   limit: int = 50, offset: int = 0) -> list[IntelFact]: ...
    def update_fact_status(self, fact_id: str, status: str) -> IntelFact: ...
    def delete_fact(self, fact_id: str) -> None: ...
    def link_fact_to_competitor(self, fact_id: str, competitor_id: int,
                                relation_type: str = "subject",
                                confidence_score: float = 1.0) -> None: ...
    def unlink_fact_from_competitor(self, fact_id: str, competitor_id: int,
                                    relation_type: str | None = None) -> None: ...
    def link_fact_to_product(self, fact_id: str, product_id: int,
                             relation_type: str = "subject",
                             confidence_score: float = 1.0) -> None: ...
    def save_evidence(self, evidence: EvidenceRef) -> EvidenceRef: ...
    def list_evidence(self, owner_type: str, owner_id: str) -> list[EvidenceRef]: ...
```

当前实现：`PostgresIntelStore`。

`list_facts(filters)` 当前支持 `fact_type`、`dimension`、`status`、`source_document_id`、`competitor_id(s)`、`product_id(s)`、日期窗口和 keyword。

---

## 11. InsightStoreProtocol

`InsightStoreProtocol` 是分析结论 `InsightClaim` 的 PostgreSQL 契约。Phase 2 只提供基础 claim 持久化、查询、状态更新和证据绑定；LLM-as-Judge 与报告质量门禁属于 Phase 3。

> **目标差异**：以下签名描述当前实现。目标模型不再提供 `attach_evidence`，claim 通过带真实外键的 claim-fact 关系间接溯源；supported claim 需要人工批准且语义不可原地更新。详见 [structured-intelligence-model.md](structured-intelligence-model.md)。

```python
class InsightStoreProtocol(Protocol):
    def save_claim(self, claim: InsightClaim) -> InsightClaim: ...
    def get_claim(self, claim_id: str) -> InsightClaim | None: ...
    def list_claims(self, filters: dict[str, Any] | None = None,
                    limit: int = 50, offset: int = 0) -> list[InsightClaim]: ...
    def update_claim_status(self, claim_id: str, status: str) -> InsightClaim: ...
    def delete_claim(self, claim_id: str) -> None: ...
    def attach_evidence(self, claim_id: str, evidence: EvidenceRef) -> EvidenceRef: ...
```

当前实现：`PostgresInsightStore`。

---

## 12. LLMClientProtocol

```python
class LLMClientProtocol(Protocol):
    def generate(self, system_prompt: str, user_message: str) -> str: ...
    def generate_stream(self, system_prompt: str, user_message: str) -> Iterator[str]: ...
    def generate_with_history(self, messages: list[dict]) -> str: ...
    def generate_with_history_stream(self, messages: list[dict]) -> Iterator[str]: ...
```

当前实现包括 OpenAI Compatible、OpenAI、Gemini 和 Anthropic 客户端。

---

## 13. EmbeddingClientProtocol

```python
class EmbeddingClientProtocol(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

当前实现：`OpenAICompatibleEmbeddingClient`。`embedding_vector_size` 决定 Qdrant collection vector size，也会传给支持 `dimensions` 参数的 Embedding API。

---

## 14. RerankClientProtocol

```python
class RerankClientProtocol(Protocol):
    def rerank(self, query: str, documents: list[str],
               top_n: int | None = None) -> list[dict]: ...
```

当前实现：`OpenAICompatibleRerankClient`。用于 RRF 候选父块后的可选精排。

---

## 15. TaskRunStoreProtocol

`TaskRunStoreProtocol` 是 PostgreSQL 权威任务历史层，负责所有异步任务的 run、stage 和 event 审计记录。Redis 可以保存执行期热状态，但不能替代该 Store 的长期记录。

```python
class TaskRunStoreProtocol(Protocol):
    def create_run(self, task_type: str, input: dict,
                   idempotency_key: str | None = None) -> TaskRun: ...
    def start_run(self, run_id: str) -> TaskRun: ...
    def finish_run(self, run_id: str, status: str,
                   result: dict | None = None,
                   error: dict | None = None) -> TaskRun: ...
    def create_stage(self, run_id: str, name: str) -> TaskStage: ...
    def finish_stage(self, stage_id: str, status: str,
                     result: dict | None = None,
                     error: dict | None = None) -> TaskStage: ...
    def append_event(self, run_id: str, event_type: str,
                     payload: dict | None = None,
                     stage_id: str | None = None) -> TaskEvent: ...
    def get_run(self, run_id: str) -> TaskRun | None: ...
    def list_stages(self, run_id: str) -> list[TaskStage]: ...
    def list_events(self, run_id: str, limit: int = 200) -> list[TaskEvent]: ...
```

当前实现：`PostgresTaskRunStore`。

契约要求：

- Store 只操作 migration 已创建的 `task_runs`、`task_stages`、`task_events`，不在初始化时创建生产 DDL。
- `task_runs` 记录任务整体输入、结果、错误、状态和时间戳。
- `task_stages` 记录阶段级状态和阶段结果。
- `task_events` 为 append-only 事件流，按 `created_at` 顺序用于审计和后续实时状态回放。
- 手动 Collection API 创建 Collection Run，再为各来源创建独立 Source Fetch Task；`/api/tasks/{task_id}` 仍可返回通用 PostgreSQL task run/stage/event 历史，但不得假设一次采集只对应一个 Celery task。

---

## 16. RedisStateStoreProtocol

`RedisStateStoreProtocol` 统一 Redis 执行期状态能力：锁、JSON cache、任务热状态、任务事件 stream 和幂等键。Redis 不保存长期事实；不可用时应降级为 `False`/`None`，由 PostgreSQL Store 保持权威记录。

```python
class RedisStateStoreProtocol(Protocol):
    def healthcheck(self) -> bool: ...
    def acquire_lock(self, key: str, owner: str, ttl_seconds: int) -> bool: ...
    def release_lock(self, key: str, owner: str) -> bool: ...
    def set_json(self, key: str, value: Any,
                 ttl_seconds: int | None = None) -> bool: ...
    def get_json(self, key: str) -> Any | None: ...
    def delete(self, key: str) -> bool: ...
    def set_task_status(self, run_id: str, status: str,
                        payload: dict | None = None,
                        ttl_seconds: int | None = None) -> bool: ...
    def get_task_status(self, run_id: str) -> dict | None: ...
    def append_task_event(self, run_id: str, event: dict) -> bool: ...
    def set_idempotency_key(self, key: str, value: str,
                            ttl_seconds: int) -> bool: ...
    def get_idempotency_key(self, key: str) -> str | None: ...
```

当前实现：`RedisStateStore`。

契约要求：

- 锁获取使用 Redis `SET key owner NX EX ttl`。
- 锁释放必须校验 owner，避免误删其他 worker 的锁。
- 任务热状态使用 `logos:task:{run_id}`，任务事件 stream 使用 `logos:task_events:{run_id}`。
- Redis SDK 类型不向 Services、Agent 或 Delivery 层泄露。

---

## 17. AgentSessionStoreProtocol 与 MemoryStoreProtocol

这两个协议继续以 PostgreSQL 为权威存储，Redis 可作为热缓存：

- `AgentSessionStoreProtocol`：普通问答和深度研究会话、事件、消息、摘要。
- `MemoryStoreProtocol`：核心记忆 revision、持久记忆、MEMORY 索引。

---

## 18. CompetitorStoreProtocol、ReportStoreProtocol 与治理协议

竞品和报告仍是独立业务 Store：

- `CompetitorStoreProtocol`：竞品档案、产品线、情报关联。
- `ReportStoreProtocol`：结构化报告、状态流转字段、report-claim/report-evidence 关系、质量审查结果和审计日志。
- `JudgeClientProtocol`：报告质量审查使用的独立结构化 JSON Judge 客户端，不复用主 LLM 或结构化抽取配置。
- `AuthStoreProtocol`：应用 API Key 哈希查询和最近使用时间更新。
- `ConfigAuditStoreProtocol`：配置变更审计查询与追加。

报告引用应优先通过 `report_evidence_refs` 记录 `evidence_ref_id`、`document_id`、`parent_chunk_id` 和原始 URL 快照，避免依赖旧子块表。`analysis_reports.source_refs` 保留为旧报告兼容字段，新写入路径应优先使用关系表。

最终契约口径：

```python
class ReportStoreProtocol(Protocol):
    def save_report(self, report: AnalysisReport) -> AnalysisReport: ...
    def get_report(self, report_id: int) -> AnalysisReport | None: ...
    def list_reports(self, report_type: str | None = None,
                     status: str | None = None,
                     limit: int = 30, offset: int = 0) -> list[AnalysisReport]: ...
    def update_report_status(self, report_id: int, status: str,
                             review_status: str | None = None,
                             quality_score: float | None = None,
                             quality_summary: str | None = None,
                             actor: str = "system") -> AnalysisReport: ...
    def delete_report(self, report_id: int) -> None: ...
    def attach_claims(self, report_id: int, claim_refs: list[ReportClaimRef]) -> None: ...
    def list_report_claims(self, report_id: int) -> list[ReportClaimRef]: ...
    def attach_evidence_refs(self, report_id: int,
                             evidence_refs: list[ReportEvidenceRef]) -> None: ...
    def list_report_evidence_refs(self, report_id: int) -> list[ReportEvidenceRef]: ...
    def save_quality_review(self, review: ReportQualityReview) -> ReportQualityReview: ...
    def list_quality_reviews(self, report_id: int) -> list[ReportQualityReview]: ...
    def append_audit_log(self, report_id: int | None, session_id: str | None,
                         action: str, detail: dict,
                         source_refs: list[dict] | None = None) -> None: ...
    def get_audit_trail(self, report_id: int) -> list[dict]: ...

class JudgeClientProtocol(Protocol):
    def judge_json(self, system_prompt: str, user_message: str,
                   *, schema_name: str, temperature: float = 0.0) -> dict[str, Any]: ...

class AuthStoreProtocol(Protocol):
    def create_api_key(self, record: ApiKeyRecord) -> ApiKeyRecord: ...
    def get_api_key_by_hash(self, key_hash: str) -> ApiKeyRecord | None: ...
    def update_last_used(self, key_id: str) -> None: ...

class ConfigAuditStoreProtocol(Protocol):
    def append_config_audit(self, log: ConfigAuditLog) -> ConfigAuditLog: ...
    def list_config_audit(self, target: str | None = None,
                          limit: int = 50, offset: int = 0) -> list[ConfigAuditLog]: ...
```

`ReportStoreProtocol` 只持久化状态和审计，不决定质量是否通过；发布前状态校验由 `ReportService` 统一执行。`AuthStoreProtocol` 不保存明文 API Key，`ConfigAuditStoreProtocol` 只保存脱敏 diff。

---

## 19. 采集与清洗协议

目标采集链路使用窄 Protocol 分离发现、获取、artifact、清洗和状态汇合：

- `SourceConnectorProtocol`：根据 Source Profile 与持久化 cursor 增量发现 Fetch Candidate，不下载正文。
- `FetchEngineProtocol`：用 HTTP 或 browser 获取单个候选并返回 FetchResult，不执行正文清洗。
- `CollectionRunStoreProtocol`：Collection Run、Source Fetch Task、状态推进与 fan-in 查询的 PostgreSQL 契约。
- `FetchArtifactStoreProtocol`：artifact metadata、HTTP 条件请求信息、生命周期和查询。
- `FetchBlobStoreProtocol`：原始 body 的保存、读取、晋升和 24 小时清理。
- `NormalizedDocumentStoreProtocol`：Normalized Document、Content Block 和规范化版本的权威存储。
- `SourceRateLimiterProtocol`：来源级 token bucket、冷却和短期租约；Redis 实现必须可降级。

Connector 与 Fetch Engine 属于 Infrastructure；Collection Orchestrator、Normalize 和 artifact 生命周期编排属于 Services。Celery task 只接受稳定 ID、调用 Service 并记录状态，不能承载 URL 规则、正文提取、归簇或保留决策。

完整接口草案、状态与故障语义见 [collection-and-normalization.md](collection-and-normalization.md)。实现时新增协议必须进入 `core/protocols.py`，不得创建平行的兼容协议文件。

---

## 20. 已移除契约

以下内容已从当前基础设施契约中移除：

- 旧向量 Store 协议
- 旧 PostgreSQL 向量 Store 实现
- 旧向量 Store 工厂函数
- `models.chunk.Chunk`
- `models.chunk.ParentChunk`
- PostgreSQL 子块 embedding 列语义

后续改造不得重新引入这些接口作为兼容层。
