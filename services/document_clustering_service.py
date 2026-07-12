"""协调权威归簇与可重建缓存。"""
import structlog

from core.protocols import DedupCacheProtocol, DocumentDedupStoreProtocol
from models.document_governance import DedupCommitResult, SourceOccurrence


logger = structlog.get_logger()


class DocumentClusteringService:
    def __init__(
        self,
        store: DocumentDedupStoreProtocol,
        cache: DedupCacheProtocol | None = None,
    ):
        self.store = store
        self.cache = cache

    def commit(self, occurrence: SourceOccurrence) -> DedupCommitResult:
        # 缓存只能缩小候选查询范围，不能替代事务内的 PostgreSQL 复查。
        result = self.store.commit_occurrence(occurrence)
        if self.cache:
            try:
                self.cache.index_occurrence(result.occurrence)
            except Exception as exc:
                logger.warning("document_clustering.cache_update_failed", error=str(exc))
        return result
