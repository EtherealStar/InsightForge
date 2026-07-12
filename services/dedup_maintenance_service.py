"""去重热点索引的可重建维护服务。"""
from core.protocols import DedupCacheProtocol, DocumentDedupStoreProtocol


class DedupMaintenanceService:
    def __init__(self, store: DocumentDedupStoreProtocol, cache: DedupCacheProtocol):
        self.store = store
        self.cache = cache

    def rebuild_cache(self, *, batch_size: int = 1000) -> dict[str, int]:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        deleted_keys = self.cache.clear()
        indexed = failed = offset = 0
        while True:
            occurrences = self.store.list_occurrences(limit=batch_size, offset=offset)
            if not occurrences:
                break
            for occurrence in occurrences:
                if self.cache.index_occurrence(occurrence):
                    indexed += 1
                else:
                    failed += 1
            offset += len(occurrences)
            if len(occurrences) < batch_size:
                break
        return {"deleted_keys": deleted_keys, "indexed": indexed, "failed": failed}
