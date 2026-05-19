"""QdrantVectorIndex unit tests with a fake qdrant-client module."""

import sys
import types

import pytest

from core.exceptions import InfrastructureError
from models.document import ChildChunkPoint


class _Collections:
    def __init__(self, names=None):
        self.collections = [
            types.SimpleNamespace(name=name) for name in (names or [])
        ]


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.collections = set()
        self.upserts = []
        self.search_calls = []
        self.deleted = []

    def get_collections(self):
        return _Collections(self.collections)

    def create_collection(self, collection_name, vectors_config):
        self.collections.add(collection_name)
        self.vectors_config = vectors_config

    def recreate_collection(self, collection_name, vectors_config):
        self.collections = {collection_name}
        self.vectors_config = vectors_config

    def upsert(self, collection_name, points, wait=True):
        self.upserts.append((collection_name, points, wait))

    def search(self, collection_name, query_vector, query_filter, limit, with_payload):
        self.search_calls.append((collection_name, query_filter))
        return [
            types.SimpleNamespace(
                id="doc:c:0",
                score=0.91,
                payload={
                    "document_id": "doc",
                    "parent_chunk_id": "doc:p0",
                    "chunk_index": 0,
                    "content": "child text",
                    "token_count": 2,
                    "heading_path": ["Doc"],
                    "document_type": "article",
                    "competitor_ids": [1],
                },
            )
        ]

    def delete(self, collection_name, points_selector, wait=True):
        self.deleted.append((collection_name, points_selector, wait))


@pytest.fixture
def fake_qdrant(monkeypatch):
    fake_module = types.ModuleType("qdrant_client")
    fake_models = types.ModuleType("qdrant_client.models")

    class Distance:
        COSINE = "Cosine"

    class VectorParams:
        def __init__(self, size, distance):
            self.size = size
            self.distance = distance

    class PointStruct:
        def __init__(self, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload

    class MatchValue:
        def __init__(self, value):
            self.value = value

    class MatchAny:
        def __init__(self, any):
            self.any = any

    class FieldCondition:
        def __init__(self, key, match=None, range=None):
            self.key = key
            self.match = match
            self.range = range

    class Filter:
        def __init__(self, must=None, should=None):
            self.must = must or []
            self.should = should or []

    class DatetimeRange:
        def __init__(self, gte=None, lte=None):
            self.gte = gte
            self.lte = lte

    class PointIdsList:
        def __init__(self, points):
            self.points = points

    fake_module.QdrantClient = _FakeClient
    fake_models.Distance = Distance
    fake_models.VectorParams = VectorParams
    fake_models.PointStruct = PointStruct
    fake_models.MatchValue = MatchValue
    fake_models.MatchAny = MatchAny
    fake_models.FieldCondition = FieldCondition
    fake_models.Filter = Filter
    fake_models.DatetimeRange = DatetimeRange
    fake_models.PointIdsList = PointIdsList

    monkeypatch.setitem(sys.modules, "qdrant_client", fake_module)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", fake_models)


def _chunk() -> ChildChunkPoint:
    return ChildChunkPoint(
        point_id="doc:c:0",
        document_id="doc",
        parent_chunk_id="doc:p0",
        content="child text",
        token_count=2,
        chunk_index=0,
        heading_path=["Doc"],
        competitor_ids=[1],
    )


def test_qdrant_index_upsert_search_delete(fake_qdrant):
    from infrastructure.qdrant.vector_index import QdrantVectorIndex

    index = QdrantVectorIndex(url="http://localhost:6333", vector_size=3)
    index.ensure_collection()

    assert index.upsert_child_chunks([_chunk()], [[0.1, 0.2, 0.3]]) == 1
    results = index.search_child_chunks(
        [0.1, 0.2, 0.3],
        filters={
            "document_id": "doc",
            "competitor_ids": [1],
            "document_type": "article",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        },
    )
    index.delete_by_point_ids(["doc:c:0"])

    assert results[0].chunk.parent_chunk_id == "doc:p0"
    assert results[0].chunk.content == "child text"
    assert index.client.upserts[0][1][0].payload["content"] == "child text"
    q_filter = index.client.search_calls[0][1]
    assert {condition.key for condition in q_filter.must} == {
        "document_id",
        "competitor_ids",
        "document_type",
    }
    assert {condition.key for condition in q_filter.should} == {"published_at", "created_at"}
    assert index.client.deleted


def test_qdrant_index_rejects_dimension_mismatch(fake_qdrant):
    from infrastructure.qdrant.vector_index import QdrantVectorIndex

    index = QdrantVectorIndex(url="http://localhost:6333", vector_size=3)

    with pytest.raises(InfrastructureError):
        index.upsert_child_chunks([_chunk()], [[0.1, 0.2]])
