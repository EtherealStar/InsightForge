"""ChromaDB 向量存储，实现 VectorStoreProtocol"""
import logging

import chromadb

from models.article import Article, Language, ArticleStatus
from models.search import SearchResult

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50


class ChromaVectorStore:
    """实现 VectorStoreProtocol"""

    def __init__(self, chroma_path: str):
        """初始化 PersistentClient，获取或创建 'news_articles' collection"""
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.client.get_or_create_collection(
            name="news_articles",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"ChromaDB 已初始化: {chroma_path}, "
            f"现有 {self.collection.count()} 条记录"
        )

    def add_articles(
        self, articles: list[Article], embeddings: list[list[float]]
    ) -> int:
        """
        将文章和对应向量写入 ChromaDB。
        批量大小 50 条。
        返回成功写入的数量。
        """
        if not articles or not embeddings:
            return 0
        if len(articles) != len(embeddings):
            logger.error(
                f"文章数 ({len(articles)}) 与向量数 ({len(embeddings)}) 不匹配"
            )
            return 0

        total_added = 0
        for i in range(0, len(articles), _BATCH_SIZE):
            batch_articles = articles[i : i + _BATCH_SIZE]
            batch_embeddings = embeddings[i : i + _BATCH_SIZE]

            ids = []
            documents = []
            metadatas = []

            for article in batch_articles:
                ids.append(f"article_{article.id}")
                documents.append(article.to_embedding_text())
                metadatas.append(
                    {
                        "article_id": article.id or 0,
                        "title": article.title[:200],
                        "url": article.url,
                        "source": article.source or "",
                        "published_at": (
                            article.published_at.isoformat()
                            if article.published_at
                            else ""
                        ),
                        "language": article.language.value,
                    }
                )

            try:
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=batch_embeddings,
                    metadatas=metadatas,
                )
                total_added += len(batch_articles)
            except Exception as e:
                logger.error(f"ChromaDB 写入失败（批次 {i}）: {e}")

        logger.info(f"ChromaDB: 写入 {total_added}/{len(articles)} 条向量")
        return total_added

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """
        向量相似度检索。
        filters 示例：{"source": "BBC News"}
        返回 SearchResult 列表。
        """
        where = None
        if filters:
            where = {k: {"$eq": v} for k, v in filters.items()}
            # ChromaDB 多条件用 $and
            if len(where) > 1:
                where = {"$and": [{k: v} for k, v in where.items()]}
            elif len(where) == 1:
                key = list(where.keys())[0]
                where = {key: where[key]}

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"ChromaDB 检索失败: {e}")
            return []

        search_results: list[SearchResult] = []
        if not results or not results["metadatas"]:
            return search_results

        for idx, metadata in enumerate(results["metadatas"][0]):
            distance = results["distances"][0][idx] if results["distances"] else 0.0
            # ChromaDB cosine distance → relevance score (1 - distance)
            relevance = 1.0 - distance

            article = Article(
                id=metadata.get("article_id"),
                title=metadata.get("title", ""),
                url=metadata.get("url", ""),
                content=results["documents"][0][idx] if results["documents"] else "",
                source=metadata.get("source", ""),
                language=Language(metadata["language"])
                if metadata.get("language")
                else Language.UNKNOWN,
            )
            search_results.append(
                SearchResult(
                    article=article,
                    relevance_score=relevance,
                    match_type="semantic",
                )
            )

        return search_results

    def delete_articles(self, article_ids: list[int]) -> None:
        """从 ChromaDB 中批量删除文档"""
        if not article_ids:
            return
            
        ids_to_delete = [f"article_{i}" for i in article_ids]
        try:
            self.collection.delete(ids=ids_to_delete)
            logger.info(f"ChromaDB: 删除成功 {len(ids_to_delete)} 条向量记录")
        except Exception as e:
            logger.error(f"ChromaDB 批量删除失败: {e}")
