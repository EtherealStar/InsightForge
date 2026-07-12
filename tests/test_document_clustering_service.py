from models.document_governance import (
    DedupCommitResult,
    DedupDecision,
    SimHashFingerprint,
    SourceOccurrence,
)
from services.document_clustering_service import DocumentClusteringService


def _occurrence() -> SourceOccurrence:
    return SourceOccurrence(
        document_id="",
        url="https://example.com/a",
        normalized_url="https://example.com/a",
        title="A",
        content_hash="hash-a",
        simhash=SimHashFingerprint(1, (1, 2, 3, 4), (1, 2, 3, 4, 5, 6, 7, 8)),
    )


class AuthoritativeStore:
    def __init__(self):
        self.calls = 0

    def commit_occurrence(self, occurrence):
        self.calls += 1
        occurrence.document_id = "cluster-from-postgres"
        return DedupCommitResult(occurrence, DedupDecision.NEW_CLUSTER, True)


class LyingCache:
    def __init__(self):
        self.indexed = None

    def find_url(self, normalized_url):
        return "wrong-cluster"

    def find_exact(self, content_hash):
        return ["wrong-cluster"]

    def index_occurrence(self, occurrence):
        self.indexed = occurrence
        return False


def test_postgres_decision_wins_over_cache_hint_and_cache_is_updated_after_commit():
    store = AuthoritativeStore()
    cache = LyingCache()

    result = DocumentClusteringService(store, cache).commit(_occurrence())

    assert store.calls == 1
    assert result.occurrence.document_id == "cluster-from-postgres"
    assert cache.indexed == result.occurrence


def test_cache_exception_does_not_undo_postgres_commit():
    store = AuthoritativeStore()
    cache = LyingCache()
    cache.index_occurrence = lambda occurrence: (_ for _ in ()).throw(RuntimeError("down"))

    result = DocumentClusteringService(store, cache).commit(_occurrence())

    assert result.occurrence.document_id == "cluster-from-postgres"
