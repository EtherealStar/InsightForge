"""接口契约：Demo 和 Full 都实现这些 Protocol"""
from typing import Any, BinaryIO, Protocol, Iterator, runtime_checkable

from models.agent_session import AgentSession, ResearchTodo, SessionStatus
from models.auth import ApiKeyRecord
from models.config_audit import ConfigAuditLog
from models.competitor import Competitor, CompetitorProduct
from models.document import (
    ChildChunkPoint,
    ChildChunkSearchResult,
    ParentDocumentChunk,
    SourceDocument,
)
from models.evidence import EvidenceRef
from models.file_asset import (
    DocumentBlob,
    ExtractedFile,
    FileTypeDetection,
    ParsedDocument,
    StoredBlobResult,
    UploadBatch,
)
from models.insight import InsightClaim
from models.intel import IntelFact
from models.document_governance import (
    DedupCommitResult,
    DocumentVersion,
    SimHashFingerprint,
    SourceOccurrence,
    DuplicateCandidate,
)
from models.source_governance import SourceProfile, SourceProfileRevision
from models.memory import CoreMemoryRevision, MemoryIndexItem, MemoryStatus, MemoryType, PersistentMemory
from models.report import AnalysisReport, ReportClaimRef, ReportEvidenceRef, ReportQualityReview
from models.task_run import TaskEvent, TaskRun, TaskStage


@runtime_checkable
class DocumentStoreProtocol(Protocol):
    """PostgreSQL authoritative document and parent chunk store."""

    def save_document(self, document: SourceDocument) -> SourceDocument: ...

    def get_document(self, document_id: str) -> SourceDocument | None: ...

    def list_documents(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SourceDocument]: ...

    def update_parse_status(
        self, document_id: str, status: str, error: dict[str, Any] | None = None
    ) -> None: ...

    def save_parent_chunks(
        self, parent_chunks: list[ParentDocumentChunk]
    ) -> int: ...

    def get_parent_chunks_by_ids(
        self, parent_chunk_ids: list[str]
    ) -> list[ParentDocumentChunk]: ...

    def list_parent_chunks(self, document_id: str) -> list[ParentDocumentChunk]: ...

    def search_parent_chunks_by_keyword(
        self,
        query: str,
        top_k: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[ParentDocumentChunk, float]]: ...

    def mark_points_vectorized(
        self, points: list[ChildChunkPoint]
    ) -> None: ...

    def mark_points_vector_failed(
        self, point_ids: list[str], error: dict[str, Any] | str
    ) -> None: ...

    def delete_document(self, document_id: str) -> None: ...


@runtime_checkable
class SourceProfileStoreProtocol(Protocol):
    def resolve_domain(self, domain: str) -> SourceProfile | None: ...
    def save_profile(self, profile: SourceProfile, *, actor: str, reason: str) -> SourceProfile: ...
    def list_revisions(self, profile_id: str) -> list[SourceProfileRevision]: ...


@runtime_checkable
class DocumentDedupStoreProtocol(Protocol):
    def find_exact(self, content_hash: str) -> list[SourceOccurrence]: ...
    def find_by_bands(self, fingerprint: SimHashFingerprint) -> list[SourceOccurrence]: ...
    def commit_occurrence(self, occurrence: SourceOccurrence) -> DedupCommitResult: ...
    def commit_decision(self, decision: DuplicateCandidate) -> DuplicateCandidate: ...
    def create_version(self, document_id: str, content: str, content_hash: str) -> DocumentVersion: ...
    def get_active_version(self, document_id: str) -> DocumentVersion | None: ...
    def activate_version(self, document_id: str, version_id: str) -> DocumentVersion: ...
    def fail_version(self, document_id: str, version_id: str) -> DocumentVersion: ...


@runtime_checkable
class DedupCacheProtocol(Protocol):
    """可重建的去重热点索引，不参与权威归簇决策。"""

    def find_url(self, normalized_url: str) -> str | None: ...
    def find_exact(self, content_hash: str) -> list[str]: ...
    def find_by_bands(self, fingerprint: SimHashFingerprint) -> list[str]: ...
    def index_occurrence(self, occurrence: SourceOccurrence) -> bool: ...
    def clear(self) -> int: ...


@runtime_checkable
class VectorIndexProtocol(Protocol):
    """Qdrant-only vector index for child chunk points."""

    def healthcheck(self) -> bool: ...

    def ensure_collection(self) -> None: ...

    def recreate_collection(self) -> None: ...

    def upsert_child_chunks(
        self, chunks: list[ChildChunkPoint], embeddings: list[list[float]]
    ) -> int: ...

    def search_child_chunks(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[ChildChunkSearchResult]: ...

    def delete_by_document_ids(self, document_ids: list[str]) -> None: ...

    def delete_by_point_ids(self, point_ids: list[str]) -> None: ...


@runtime_checkable
class UploadStoreProtocol(Protocol):
    """PostgreSQL authoritative upload batch and blob metadata store."""

    def create_batch(self, batch: UploadBatch) -> UploadBatch: ...

    def finish_batch(
        self, batch_id: str, status: str, error: dict[str, Any] | None = None
    ) -> UploadBatch: ...

    def save_blob(self, blob: DocumentBlob) -> DocumentBlob: ...

    def get_blob(self, blob_id: str) -> DocumentBlob | None: ...

    def list_blobs(self, batch_id: str) -> list[DocumentBlob]: ...

    def find_blobs_by_sha256(self, sha256: str) -> list[DocumentBlob]: ...

    def update_blob_status(
        self, blob_id: str, status: str, error: dict[str, Any] | None = None
    ) -> None: ...


@runtime_checkable
class FileBlobStoreProtocol(Protocol):
    """File object store abstraction for uploaded and extracted bytes."""

    def put(
        self, stream: BinaryIO, metadata: dict[str, Any] | None = None
    ) -> StoredBlobResult: ...

    def open(self, blob_path: str) -> BinaryIO: ...

    def delete(self, blob_path: str) -> bool: ...

    def exists(self, blob_path: str) -> bool: ...

    def quarantine(self, blob_path: str, reason: str) -> str: ...


@runtime_checkable
class ArchiveExtractorProtocol(Protocol):
    """Safe archive extraction interface."""

    def can_extract(self, filename: str, content_type: str = "") -> bool: ...

    def extract(
        self,
        archive_path: str,
        output_dir: str,
        limits: dict[str, Any] | None = None,
    ) -> list[ExtractedFile]: ...


@runtime_checkable
class FileTypeDetectorProtocol(Protocol):
    """Conservative file type detector."""

    def detect(self, filename: str, content_type: str = "") -> FileTypeDetection: ...


@runtime_checkable
class DocumentParserProtocol(Protocol):
    """Parse stored blobs into normalized Markdown/text documents."""

    def detect(self, blob: DocumentBlob) -> FileTypeDetection: ...

    def parse(self, blob: DocumentBlob) -> ParsedDocument: ...


@runtime_checkable
class TaskRunStoreProtocol(Protocol):
    """PostgreSQL authoritative task run history store."""

    def create_run(
        self,
        task_type: str,
        input: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> TaskRun: ...

    def start_run(self, run_id: str) -> TaskRun: ...

    def finish_run(
        self,
        run_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> TaskRun: ...

    def create_stage(self, run_id: str, name: str) -> TaskStage: ...

    def finish_stage(
        self,
        stage_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> TaskStage: ...

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        stage_id: str | None = None,
    ) -> TaskEvent: ...

    def get_run(self, run_id: str) -> TaskRun | None: ...

    def list_runs(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TaskRun], int]: ...

    def list_stages(self, run_id: str) -> list[TaskStage]: ...

    def list_events(self, run_id: str, limit: int = 200) -> list[TaskEvent]: ...


@runtime_checkable
class RedisStateStoreProtocol(Protocol):
    """Redis execution-time state, lock, cache, and event stream store."""

    def healthcheck(self) -> bool: ...

    def acquire_lock(self, key: str, owner: str, ttl_seconds: int) -> bool: ...

    def release_lock(self, key: str, owner: str) -> bool: ...

    def set_json(
        self,
        key: str,
        value: dict[str, Any] | list[Any] | str | int | float | bool | None,
        ttl_seconds: int | None = None,
    ) -> bool: ...

    def get_json(
        self, key: str
    ) -> dict[str, Any] | list[Any] | str | int | float | bool | None: ...

    def delete(self, key: str) -> bool: ...

    def set_task_status(
        self,
        run_id: str,
        status: str,
        payload: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> bool: ...

    def get_task_status(self, run_id: str) -> dict[str, Any] | None: ...

    def append_task_event(self, run_id: str, event: dict[str, Any]) -> bool: ...

    def set_idempotency_key(
        self, key: str, value: str, ttl_seconds: int
    ) -> bool: ...

    def get_idempotency_key(self, key: str) -> str | None: ...


@runtime_checkable
class LLMClientProtocol(Protocol):
    """LLM 调用（OpenAI 兼容 / GPT / Gemini / Claude）"""

    def generate(self, system_prompt: str, user_message: str) -> str: ...

    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]: ...

    def generate_with_history(self, messages: list[dict]) -> str:
        """多轮对话：接受完整消息历史生成回复。

        Args:
            messages: OpenAI 格式消息列表，每条消息包含:
                - role: "system" | "user" | "assistant"
                - content: 消息内容

        Returns:
            LLM 生成的回复文本。
        """
        ...

    def generate_with_history_stream(
        self, messages: list[dict]
    ) -> Iterator[str]:
        """多轮对话流式版本。"""
        ...


@runtime_checkable
class StructuredExtractionClientProtocol(Protocol):
    """Structured JSON extraction client for fact extraction workloads."""

    def extract_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]: ...


@runtime_checkable
class JudgeClientProtocol(Protocol):
    """Structured JSON judge client for report quality reviews."""

    def judge_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]: ...


@runtime_checkable
class EmbeddingClientProtocol(Protocol):
    """Embedding 调用（OpenAI 格式自定义 API）"""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class RerankClientProtocol(Protocol):
    """Rerank 重排序（Jina / Cohere / SiliconFlow 等 Cross-Encoder API）"""

    def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[dict]:
        """对文档列表按与 query 的相关性重新排序。

        Args:
            query: 查询文本。
            documents: 待排序的文档文本列表。
            top_n: 返回前 N 条结果，None 则返回全部。

        Returns:
            [{"index": int, "relevance_score": float}, ...]
            按 relevance_score 降序排列。
        """
        ...


@runtime_checkable
class AgentSessionStoreProtocol(Protocol):
    """Agent 会话存储（PostgreSQL + Redis 缓存）。"""

    def create_general_session(
        self,
        topic: str,
        messages: list[dict[str, Any]] | None = None,
    ) -> AgentSession: ...

    def create_session(
        self,
        topic: str,
        plan: dict[str, Any] | str | None,
        todos: list[ResearchTodo],
        messages: list[dict[str, Any]] | None = None,
    ) -> AgentSession: ...

    def get_session(self, session_id: str) -> AgentSession | None: ...

    def list_sessions(
        self,
        session_type: str = "general_query",
        limit: int = 30,
        offset: int = 0,
    ) -> list[AgentSession]: ...

    def save_plan(
        self,
        session_id: str,
        plan: dict[str, Any] | str,
        todos: list[ResearchTodo],
    ) -> AgentSession: ...

    def update_status(
        self,
        session_id: str,
        status: SessionStatus,
        error: str | None = None,
    ) -> AgentSession: ...

    def append_event(self, session_id: str, event: dict[str, Any]) -> None: ...

    def append_message(self, session_id: str, message: dict[str, Any]) -> None: ...

    def update_summary(
        self,
        session_id: str,
        summary: str,
        token_count: int,
        last_compacted_tokens: int,
        compact_failures: int = 0,
    ) -> AgentSession: ...

    def update_todos(
        self,
        session_id: str,
        todos: list[ResearchTodo],
    ) -> AgentSession: ...

    def complete_session(
        self,
        session_id: str,
        final_answer: str,
        report_filename: str | None,
    ) -> AgentSession: ...

    def fail_session(self, session_id: str, error: str) -> AgentSession: ...

    def flush_session(self, session_id: str) -> None: ...


@runtime_checkable
class MemoryStoreProtocol(Protocol):
    """三层记忆存储（PostgreSQL 为准，Redis 可缓存索引）。"""

    def get_active_core_memories(
        self,
        kind: str | None = None,
    ) -> list[CoreMemoryRevision]: ...

    def create_core_memory_revision(
        self,
        kind: str,
        title: str,
        content: str,
    ) -> CoreMemoryRevision: ...

    def list_memory_index(
        self,
        memory_types: list[MemoryType] | None = None,
    ) -> list[MemoryIndexItem]: ...

    def list_persistent_memories(
        self,
        status: MemoryStatus | None = None,
        memory_type: MemoryType | None = None,
    ) -> list[PersistentMemory]: ...

    def get_persistent_memory(self, memory_id: str) -> PersistentMemory | None: ...

    def create_persistent_memory(
        self,
        memory_type: MemoryType,
        title: str,
        summary: str,
        content: str,
        source_session_id: str | None = None,
        confidence: float | None = None,
        status: MemoryStatus = MemoryStatus.PENDING,
    ) -> PersistentMemory: ...

    def update_persistent_memory_status(
        self,
        memory_id: str,
        status: MemoryStatus,
    ) -> PersistentMemory: ...

    def delete_persistent_memory(self, memory_id: str) -> None: ...


@runtime_checkable
class WebhookServiceProtocol(Protocol):
    """Webhook 推送服务协议 — 仅定义推送核心能力。

    CRUD 方法（add_channel/update_channel/delete_channel/test_channel）
    仅在 webhook_router 中使用，属于 Delivery 层细节，不纳入 Protocol。
    """

    def broadcast(self, content: str) -> list[dict]: ...

    def send_to_channel(self, channel: Any, content: str) -> dict: ...

    def load_channels(self) -> list: ...

    def get_auto_push(self) -> bool: ...


@runtime_checkable
class CompetitorStoreProtocol(Protocol):
    """竞品数据存储（PostgreSQL）"""

    def save_competitor(self, competitor: Competitor) -> Competitor:
        """创建或更新竞品档案。返回带 id 的实例。"""
        ...

    def get_competitor(self, competitor_id: int) -> Competitor | None: ...

    def list_competitors(
        self, status: str = "active", limit: int = 100
    ) -> list[Competitor]: ...

    def search_competitors(self, query: str) -> list[Competitor]:
        """按名称/别名模糊搜索竞品。"""
        ...

    def delete_competitor(self, competitor_id: int) -> None: ...

    def save_product(self, product: CompetitorProduct) -> CompetitorProduct: ...

    def list_products(self, competitor_id: int) -> list[CompetitorProduct]: ...

    def delete_product(self, product_id: int) -> None: ...

    # --- 情报关联 ---

    def link_intel_to_competitor(
        self, document_id: str, competitor_id: int
    ) -> None: ...

    def unlink_intel_from_competitor(
        self, document_id: str, competitor_id: int
    ) -> None: ...

    def get_competitor_ids_for_intel(self, document_id: str) -> list[int]: ...

    def get_intel_ids_for_competitor(
        self,
        competitor_id: int,
        intel_type: str | None = None,
        limit: int = 50,
    ) -> list[str]: ...


@runtime_checkable
class IntelStoreProtocol(Protocol):
    """Structured intel fact store."""

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


@runtime_checkable
class InsightStoreProtocol(Protocol):
    """Insight claim store."""

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


@runtime_checkable
class ReportStoreProtocol(Protocol):
    """分析报告存储（PostgreSQL）"""

    def save_report(self, report: AnalysisReport) -> AnalysisReport:
        """创建或更新报告。返回带 id 的实例。"""
        ...

    def get_report(self, report_id: int) -> AnalysisReport | None: ...

    def list_reports(
        self,
        report_type: str | None = None,
        status: str | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> list[AnalysisReport]: ...

    def delete_report(self, report_id: int) -> None: ...

    def update_report_status(
        self,
        report_id: int,
        status: str,
        *,
        review_status: str | None = None,
        quality_score: float | None = None,
        quality_summary: str | None = None,
        actor: str = "system",
    ) -> AnalysisReport: ...

    def attach_claims(
        self, report_id: int, claim_refs: list[ReportClaimRef]
    ) -> None: ...

    def list_report_claims(self, report_id: int) -> list[ReportClaimRef]: ...

    def attach_evidence_refs(
        self, report_id: int, evidence_refs: list[ReportEvidenceRef]
    ) -> None: ...

    def list_report_evidence_refs(
        self, report_id: int
    ) -> list[ReportEvidenceRef]: ...

    def save_quality_review(
        self, review: ReportQualityReview
    ) -> ReportQualityReview: ...

    def list_quality_reviews(
        self, report_id: int
    ) -> list[ReportQualityReview]: ...

    def append_audit_log(
        self,
        report_id: int | None,
        session_id: str | None,
        action: str,
        detail: dict,
        source_refs: list[dict] | None = None,
    ) -> None:
        """追加审计日志条目。"""
        ...

    def get_audit_trail(
        self, report_id: int
    ) -> list[dict]:
        """获取报告完整审计链路。"""
        ...


@runtime_checkable
class AuthStoreProtocol(Protocol):
    """Application API key persistence."""

    def create_api_key(self, record: ApiKeyRecord) -> ApiKeyRecord: ...

    def get_api_key_by_hash(self, key_hash: str) -> ApiKeyRecord | None: ...

    def update_last_used(self, key_id: str) -> None: ...


@runtime_checkable
class ConfigAuditStoreProtocol(Protocol):
    """Configuration audit persistence."""

    def append_config_audit(self, log: ConfigAuditLog) -> ConfigAuditLog: ...

    def list_config_audit(
        self,
        *,
        target: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConfigAuditLog]: ...
