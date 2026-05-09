"""Qdrant 向量存储 — chunk 级别，实现 VectorStoreProtocol

子 chunks 的向量存入 Qdrant，检索时搜索子 chunk 向量。
父 chunks 存储在 PostgreSQL 中，通过 parent_chunk_id 关联。
"""
import structlog
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from models.chunk import Chunk
from models.search import ChunkSearchResult

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 50


class QdrantVectorStore:
    """实现 VectorStoreProtocol — chunk 级别"""

    def __init__(
        self,
        url: str,
        api_key: str,
        collection_name: str = "news_chunks",
        vector_size: int = 1536,
    ):
        """初始化 Qdrant Client，获取或创建 collection"""
        self.client = QdrantClient(url=url, api_key=api_key)
        self.collection_name = collection_name

        try:
            if not self.client.collection_exists(self.collection_name):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=vector_size, distance=Distance.COSINE
                    ),
                )
                logger.info(
                    f"Qdrant: 已创建 chunk collection {self.collection_name}"
                )
            else:
                logger.info(
                    f"Qdrant: 已连接到现有的 chunk collection {self.collection_name}"
                )
        except Exception as e:
            logger.error(f"Qdrant 初始化失败: {e}")

    # ------------------------------------------------------------------
    # VectorStoreProtocol 实现
    # ------------------------------------------------------------------

    def add_chunks(
        self, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> int:
        """将子 chunks 及其向量写入 Qdrant。

        每个 point 的 payload 包含子 chunk 元数据和 parent_chunk_id，
        用于检索后定位父 chunk。
        """
        if not chunks or not embeddings:
            return 0
        if len(chunks) != len(embeddings):
            logger.error(
                f"子 chunk 数 ({len(chunks)}) 与向量数 ({len(embeddings)}) 不匹配"
            )
            return 0

        total_added = 0
        for i in range(0, len(chunks), _BATCH_SIZE):
            batch_chunks = chunks[i: i + _BATCH_SIZE]
            batch_embeddings = embeddings[i: i + _BATCH_SIZE]

            points = []
            for j, chunk in enumerate(batch_chunks):
                payload = {
                    "chunk_id": chunk.chunk_id,
                    "article_id": chunk.article_id,
                    "parent_chunk_id": chunk.parent_chunk_id,
                    "doc_name": chunk.doc_name,
                    "heading_path": chunk.heading_path,
                    "content": chunk.content,
                    "chunk_index": chunk.chunk_index,
                    "source": chunk.source,
                    "url": chunk.url,
                }

                # 使用 chunk_id 生成确定性 UUID 作为 point ID
                point_id = str(
                    uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id)
                )

                points.append(
                    PointStruct(
                        id=point_id,
                        vector=batch_embeddings[j],
                        payload=payload,
                    )
                )

            try:
                self.client.upsert(
                    collection_name=self.collection_name, points=points
                )
                total_added += len(batch_chunks)
            except Exception as e:
                logger.error(f"Qdrant chunk 写入失败（批次 {i}）: {e}")

        logger.info(f"Qdrant: 写入 {total_added} 个子 chunks")
        return total_added

    def search_chunks(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[ChunkSearchResult]:
        """搜索子 chunks，返回匹配的子 chunk 信息。

        返回的 ChunkSearchResult 中 parent_chunk 字段为 None，
        需要调用方根据 parent_chunk_id 查询 PostgreSQL 获取父 chunk。
        """
        query_filter = None
        if filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
            query_filter = Filter(must=conditions)

        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=top_k,
            )
        except Exception as e:
            logger.error(f"Qdrant chunk 检索失败: {e}")
            return []

        search_results: list[ChunkSearchResult] = []
        for scored_point in results:
            payload = scored_point.payload or {}
            relevance = scored_point.score

            chunk = Chunk(
                chunk_id=payload.get("chunk_id", ""),
                article_id=payload.get("article_id", 0),
                parent_chunk_id=payload.get("parent_chunk_id", ""),
                content=payload.get("content", ""),
                token_count=0,  # 检索时不需要精确 token 数
                doc_name=payload.get("doc_name", ""),
                heading_path=payload.get("heading_path", []),
                chunk_index=payload.get("chunk_index", 0),
                source=payload.get("source", ""),
                url=payload.get("url", ""),
            )

            search_results.append(
                ChunkSearchResult(
                    chunk=chunk,
                    parent_chunk=None,  # 由调用方填充
                    relevance_score=relevance,
                    match_type="semantic",
                )
            )

        return search_results

    def delete_by_article_ids(self, article_ids: list[int]) -> None:
        """删除指定文章 ID 关联的所有 chunk 向量。"""
        if not article_ids:
            return

        for article_id in article_ids:
            try:
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=Filter(
                        must=[
                            FieldCondition(
                                key="article_id",
                                match=MatchValue(value=article_id),
                            )
                        ]
                    ),
                )
            except Exception as e:
                logger.error(
                    f"Qdrant 删除 article_id={article_id} 的 chunks 失败: {e}"
                )

        logger.info(
            f"Qdrant: 已删除 {len(article_ids)} 篇文章的所有 chunk 向量"
        )
