"""PostgreSQL pgvector 向量存储 — chunk 级别，实现 VectorStoreProtocol."""

from __future__ import annotations

import json
from typing import Any

import psycopg2
import structlog
from psycopg2.extras import DictCursor

from models.chunk import Chunk
from models.search import ChunkSearchResult

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 50


class PgVectorStore:
    """使用 PostgreSQL + pgvector 存储和检索子 chunk 向量。"""

    def __init__(self, dsn: str, vector_size: int = 1536):
        self.dsn = dsn
        self.vector_size = vector_size
        self._init_db()

    def _get_conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    def _init_db(self) -> None:
        create_sql = f"""
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE IF NOT EXISTS child_chunks (
            chunk_id        TEXT PRIMARY KEY,
            article_id      INTEGER NOT NULL,
            parent_chunk_id TEXT NOT NULL,
            content         TEXT NOT NULL,
            token_count     INTEGER NOT NULL DEFAULT 0,
            doc_name        TEXT NOT NULL DEFAULT '',
            heading_path    JSONB NOT NULL DEFAULT '[]'::jsonb,
            chunk_index     INTEGER NOT NULL DEFAULT 0,
            source          TEXT DEFAULT '',
            url             TEXT DEFAULT '',
            embedding       vector({self.vector_size}) NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_child_chunks_article_id
            ON child_chunks(article_id);
        CREATE INDEX IF NOT EXISTS idx_child_chunks_parent_chunk_id
            ON child_chunks(parent_chunk_id);
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_sql)
                    try:
                        cur.execute(
                            """CREATE INDEX IF NOT EXISTS idx_child_chunks_embedding_hnsw
                               ON child_chunks
                               USING hnsw (embedding vector_cosine_ops)"""
                        )
                    except Exception as e:
                        logger.warning(f"pgvector HNSW 索引创建失败，将使用顺序/普通扫描: {e}")
            logger.info("pgvector: child_chunks 表初始化完成")
        except Exception as e:
            logger.error(f"pgvector 初始化失败: {e}")

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(str(float(v)) for v in vector) + "]"

    @staticmethod
    def _row_to_chunk(row: Any) -> Chunk:
        heading_path = row["heading_path"] or []
        if isinstance(heading_path, str):
            try:
                heading_path = json.loads(heading_path)
            except (json.JSONDecodeError, TypeError):
                heading_path = []

        return Chunk(
            chunk_id=row["chunk_id"],
            article_id=row["article_id"],
            parent_chunk_id=row["parent_chunk_id"],
            content=row["content"] or "",
            token_count=row["token_count"] or 0,
            doc_name=row["doc_name"] or "",
            heading_path=heading_path,
            chunk_index=row["chunk_index"] or 0,
            source=row["source"] or "",
            url=row["url"] or "",
        )

    def add_chunks(
        self, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> int:
        """将子 chunks 及其向量写入 PostgreSQL。"""
        if not chunks or not embeddings:
            return 0
        if len(chunks) != len(embeddings):
            logger.error(
                f"子 chunk 数 ({len(chunks)}) 与向量数 ({len(embeddings)}) 不匹配"
            )
            return 0

        total_added = 0
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for i in range(0, len(chunks), _BATCH_SIZE):
                    batch_chunks = chunks[i: i + _BATCH_SIZE]
                    batch_embeddings = embeddings[i: i + _BATCH_SIZE]

                    for chunk, embedding in zip(batch_chunks, batch_embeddings):
                        if len(embedding) != self.vector_size:
                            logger.error(
                                f"chunk {chunk.chunk_id} 向量维度 {len(embedding)} "
                                f"与配置 {self.vector_size} 不匹配"
                            )
                            continue

                        try:
                            cur.execute(
                                """INSERT INTO child_chunks
                                   (chunk_id, article_id, parent_chunk_id, content,
                                    token_count, doc_name, heading_path, chunk_index,
                                    source, url, embedding)
                                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                           %s::vector)
                                   ON CONFLICT (chunk_id) DO UPDATE SET
                                       article_id = EXCLUDED.article_id,
                                       parent_chunk_id = EXCLUDED.parent_chunk_id,
                                       content = EXCLUDED.content,
                                       token_count = EXCLUDED.token_count,
                                       doc_name = EXCLUDED.doc_name,
                                       heading_path = EXCLUDED.heading_path,
                                       chunk_index = EXCLUDED.chunk_index,
                                       source = EXCLUDED.source,
                                       url = EXCLUDED.url,
                                       embedding = EXCLUDED.embedding""",
                                (
                                    chunk.chunk_id,
                                    chunk.article_id,
                                    chunk.parent_chunk_id,
                                    chunk.content,
                                    chunk.token_count,
                                    chunk.doc_name,
                                    json.dumps(chunk.heading_path, ensure_ascii=False),
                                    chunk.chunk_index,
                                    chunk.source,
                                    chunk.url,
                                    self._vector_literal(embedding),
                                ),
                            )
                            total_added += 1
                        except Exception as e:
                            logger.error(
                                f"pgvector chunk 写入失败 ({chunk.chunk_id}): {e}"
                            )

        logger.info(f"pgvector: 写入 {total_added} 个子 chunks")
        return total_added

    def search_chunks(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[ChunkSearchResult]:
        """搜索子 chunks，返回匹配的子 chunk 信息。"""
        if not query_embedding:
            return []
        if len(query_embedding) != self.vector_size:
            logger.error(
                f"查询向量维度 {len(query_embedding)} 与配置 {self.vector_size} 不匹配"
            )
            return []

        where_parts = []
        query_vector = self._vector_literal(query_embedding)
        filter_params: list[Any] = []

        if filters:
            allowed_filters = {"article_id", "parent_chunk_id", "source", "url"}
            for key, value in filters.items():
                if key not in allowed_filters:
                    logger.warning(f"pgvector: 忽略不支持的过滤字段 {key}")
                    continue
                where_parts.append(f"{key} = %s")
                filter_params.append(value)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        sql = f"""SELECT *,
                         (embedding <=> %s::vector) AS distance
                  FROM child_chunks
                  {where_sql}
                  ORDER BY embedding <=> %s::vector
                  LIMIT %s"""
        params = [query_vector, *filter_params, query_vector, top_k]

        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(params))
                    rows = cur.fetchall()
        except Exception as e:
            logger.error(f"pgvector chunk 检索失败: {e}")
            return []

        results: list[ChunkSearchResult] = []
        for row in rows:
            distance = float(row["distance"])
            results.append(
                ChunkSearchResult(
                    chunk=self._row_to_chunk(row),
                    parent_chunk=None,
                    relevance_score=1.0 - distance,
                    match_type="semantic",
                )
            )
        return results

    def delete_by_article_ids(self, article_ids: list[int]) -> None:
        """删除指定文章 ID 关联的所有 chunk 向量。"""
        if not article_ids:
            return

        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM child_chunks WHERE article_id = ANY(%s)",
                        (article_ids,),
                    )
                    deleted = cur.rowcount
            logger.info(f"pgvector: 删除 {deleted} 个子 chunks")
        except Exception as e:
            logger.error(f"pgvector 删除 chunks 失败: {e}")
