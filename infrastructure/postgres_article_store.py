"""PostgreSQL 文章存储，实现 ArticleStoreProtocol"""
import hashlib
import json
import structlog
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import DictCursor

import jieba

from models.article import Article, Language, ArticleStatus
from models.chunk import ParentChunk

logger = structlog.get_logger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id           SERIAL PRIMARY KEY,
    url_hash     TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    content      TEXT,
    html_content TEXT,
    summary      TEXT,
    source       TEXT,
    author       TEXT DEFAULT '',
    language     TEXT,
    published_at TIMESTAMP,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status       TEXT DEFAULT 'stored',
    tags         JSONB DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at);
CREATE INDEX IF NOT EXISTS idx_source ON articles(source);

CREATE TABLE IF NOT EXISTS parent_chunks (
    parent_chunk_id TEXT PRIMARY KEY,
    article_id      INTEGER NOT NULL,
    content         TEXT NOT NULL,
    token_count     INTEGER NOT NULL DEFAULT 0,
    child_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    doc_name        TEXT NOT NULL DEFAULT '',
    source          TEXT DEFAULT '',
    url             TEXT DEFAULT '',
    search_vector   tsvector,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parent_chunks_article_id ON parent_chunks(article_id);
CREATE INDEX IF NOT EXISTS idx_parent_chunks_fts ON parent_chunks USING GIN(search_vector);
"""


class PostgresArticleStore:
    """实现 ArticleStoreProtocol"""

    def __init__(self, dsn: str):
        """初始化时自动创建数据库和表"""
        self.dsn = dsn
        self._init_db()

    def _get_conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    def _init_db(self):
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_TABLE_SQL)
        except Exception as e:
            logger.error(f"PostgreSQL 初始化失败: {e}")

    @staticmethod
    def _hash_url(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_article(row) -> Article:
        """将数据库行转为 Article 对象"""
        keys = row.keys()

        published_at = row["published_at"]
        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at)
            except (ValueError, TypeError):
                published_at = None

        created_at = row["created_at"] or datetime.now()
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except (ValueError, TypeError):
                pass

        # tags 在 Postgres 中是 JSONB
        tags = row.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []

        return Article(
            id=row["id"],
            url_hash=row["url_hash"],
            title=row["title"],
            url=row["url"],
            content=row["content"] or "",
            html_content=row["html_content"] if "html_content" in keys and row["html_content"] else "",
            summary=row["summary"] or "",
            source=row["source"] or "",
            author=row["author"] if "author" in keys and row["author"] else "",
            language=Language(row["language"]) if row["language"] else Language.UNKNOWN,
            published_at=published_at,
            created_at=created_at,
            tags=tags,
            status=ArticleStatus(row["status"]) if row["status"] else ArticleStatus.STORED,
        )

    def save_articles(self, articles: list[Article]) -> int:
        """
        去重后写入数据库。
        去重：SHA256(url) → url_hash，存在则跳过。
        content 字段存储 Markdown 格式的正文。
        返回实际新增数量。
        """
        new_count = 0
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for article in articles:
                    url_hash = self._hash_url(article.url)
                    try:
                        cur.execute(
                            """INSERT INTO articles 
                               (url_hash, title, url, content, html_content, summary, source,
                                author, language, published_at, created_at, status, tags)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT (url_hash) DO NOTHING""",
                            (
                                url_hash,
                                article.title,
                                article.url,
                                article.content,
                                article.html_content,
                                article.summary,
                                article.source,
                                article.author or "",
                                article.language.value,
                                article.published_at,
                                datetime.now(),
                                ArticleStatus.PENDING_SUMMARY.value,
                                json.dumps(article.tags or [], ensure_ascii=False),
                            ),
                        )
                        if cur.rowcount > 0:
                            new_count += 1
                    except Exception as e:
                        logger.error(f"保存文章失败: {e}")
        logger.info(f"保存文章: {new_count}/{len(articles)} 篇为新文章")
        return new_count

    def get_unembedded(self, limit: int = 100) -> list[Article]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM articles WHERE status = %s ORDER BY created_at DESC LIMIT %s",
                    (ArticleStatus.SUMMARIZED.value, limit),
                )
                rows = cur.fetchall()
        return [self._row_to_article(row) for row in rows]

    def mark_embedded(self, article_ids: list[int]) -> None:
        if not article_ids:
            return
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE articles SET status = %s WHERE id = ANY(%s)",
                    (ArticleStatus.EMBEDDED.value, article_ids),
                )
        logger.info(f"标记 {len(article_ids)} 篇文章为已向量化")

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Article]:
        pattern = f"%{keyword}%"
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM articles 
                       WHERE title ILIKE %s OR content ILIKE %s
                       ORDER BY created_at DESC LIMIT %s""",
                    (pattern, pattern, limit),
                )
                rows = cur.fetchall()
        return [self._row_to_article(row) for row in rows]

    def get_recent(self, hours: int = 24, limit: int = 50) -> list[Article]:
        cutoff = datetime.now() - timedelta(hours=hours)
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM articles 
                       WHERE created_at >= %s
                       ORDER BY created_at DESC LIMIT %s""",
                    (cutoff, limit),
                )
                rows = cur.fetchall()
        return [self._row_to_article(row) for row in rows]

    def get_stats(self) -> dict:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM articles")
                total = cur.fetchone()[0]

                cur.execute(
                    "SELECT COUNT(*) FROM articles WHERE status = %s",
                    (ArticleStatus.EMBEDDED.value,),
                )
                embedded = cur.fetchone()[0]

                today_start = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                cur.execute(
                    "SELECT COUNT(*) FROM articles WHERE created_at >= %s",
                    (today_start,),
                )
                today_new = cur.fetchone()[0]

                cur.execute("SELECT MIN(created_at) FROM articles")
                oldest_row = cur.fetchone()
                oldest_date = oldest_row[0].isoformat() if oldest_row and oldest_row[0] else "无数据"

                cur.execute("SELECT DISTINCT source FROM articles WHERE source IS NOT NULL")
                source_rows = cur.fetchall()
                sources = [row[0] for row in source_rows if row[0]]

        return {
            "total": total,
            "embedded": embedded,
            "today_new": today_new,
            "oldest_date": oldest_date,
            "sources": sources,
        }

    def cleanup_old_articles(self, retention_days: int = 90) -> int:
        cutoff = datetime.now() - timedelta(days=retention_days)
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM articles WHERE created_at < %s", (cutoff,))
                deleted = cur.rowcount
        logger.info(f"清理旧文章: 删除 {deleted} 篇（保留 {retention_days} 天）")
        return deleted

    def delete_articles(self, article_ids: list[int]) -> int:
        if not article_ids:
            return 0
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM articles WHERE id = ANY(%s)",
                    (article_ids,),
                )
                deleted = cur.rowcount
        logger.info(f"据 ID 成功删除 {deleted} 篇文章记录")
        return deleted

    def get_pending_summary(self, limit: int = 100) -> list[Article]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM articles WHERE status = %s ORDER BY created_at DESC LIMIT %s",
                    (ArticleStatus.PENDING_SUMMARY.value, limit),
                )
                rows = cur.fetchall()
        return [self._row_to_article(row) for row in rows]

    def mark_pending_summary(self, article_ids: list[int]) -> None:
        if not article_ids:
            return
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE articles SET status = %s WHERE id = ANY(%s)",
                    (ArticleStatus.PENDING_SUMMARY.value, article_ids),
                )
        logger.info(f"标记 {len(article_ids)} 篇文章为等待 AI 摘要")

    def mark_summarized(self, article_ids: list[int]) -> None:
        if not article_ids:
            return
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE articles SET status = %s WHERE id = ANY(%s)",
                    (ArticleStatus.SUMMARIZED.value, article_ids),
                )
        logger.info(f"标记 {len(article_ids)} 篇文章为 AI 摘要完成")

    def update_summary(self, article_id: int, summary: str, tags: list[str]) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE articles SET summary = %s, tags = %s WHERE id = %s",
                    (summary, json.dumps(tags, ensure_ascii=False), article_id),
                )

    def get_article_by_id(self, article_id: int) -> Article | None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
                row = cur.fetchone()
        if row:
            return self._row_to_article(row)
        return None

    def get_articles(
        self,
        page: int = 1,
        page_size: int = 20,
        source: str | None = None,
        language: str | None = None,
        keyword: str | None = None,
    ) -> list[Article]:
        conditions = []
        params = []

        if source:
            conditions.append("source = %s")
            params.append(source)
        if language:
            conditions.append("language = %s")
            params.append(language)
        if keyword:
            conditions.append("(title ILIKE %s OR content ILIKE %s)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        offset = (page - 1) * page_size
        params.extend([page_size, offset])

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM articles {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    tuple(params),
                )
                rows = cur.fetchall()
        return [self._row_to_article(row) for row in rows]

    def count_articles(
        self,
        source: str | None = None,
        language: str | None = None,
        keyword: str | None = None,
    ) -> int:
        conditions = []
        params = []

        if source:
            conditions.append("source = %s")
            params.append(source)
        if language:
            conditions.append("language = %s")
            params.append(language)
        if keyword:
            conditions.append("(title ILIKE %s OR content ILIKE %s)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM articles {where}", tuple(params))
                count = cur.fetchone()[0]
        return count

    # ------------------------------------------------------------------
    # 父 chunk 存储方法
    # ------------------------------------------------------------------

    def save_parent_chunks(self, parent_chunks: list[ParentChunk]) -> int:
        """批量保存父 chunks (upsert)。自动生成 jieba 分词的全文索引。返回写入数量。"""
        if not parent_chunks:
            return 0

        count = 0
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for pc in parent_chunks:
                    try:
                        # 使用 jieba 分词生成空格分隔的文本，供 PostgreSQL simple 配置使用
                        segmented_content = self._segment_text(pc.content)
                        cur.execute(
                            """INSERT INTO parent_chunks
                               (parent_chunk_id, article_id, content, token_count,
                                child_chunk_ids, doc_name, source, url, search_vector)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                                       to_tsvector('simple', %s))
                               ON CONFLICT (parent_chunk_id) DO UPDATE SET
                                   content = EXCLUDED.content,
                                   token_count = EXCLUDED.token_count,
                                   child_chunk_ids = EXCLUDED.child_chunk_ids,
                                   search_vector = EXCLUDED.search_vector""",
                            (
                                pc.parent_chunk_id,
                                pc.article_id,
                                pc.content,
                                pc.token_count,
                                json.dumps(pc.child_chunk_ids, ensure_ascii=False),
                                pc.doc_name,
                                pc.source,
                                pc.url,
                                segmented_content,
                            ),
                        )
                        count += 1
                    except Exception as e:
                        logger.error(
                            f"保存父 chunk {pc.parent_chunk_id} 失败: {e}"
                        )

        logger.info(f"保存父 chunks: {count}/{len(parent_chunks)} 个")
        return count

    def get_parent_chunks_by_ids(
        self, parent_chunk_ids: list[str]
    ) -> list[ParentChunk]:
        """根据 parent_chunk_id 列表批量获取父 chunks。"""
        if not parent_chunk_ids:
            return []

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM parent_chunks WHERE parent_chunk_id = ANY(%s)",
                    (parent_chunk_ids,),
                )
                rows = cur.fetchall()

        results = []
        for row in rows:
            child_ids = row["child_chunk_ids"]
            if isinstance(child_ids, str):
                try:
                    child_ids = json.loads(child_ids)
                except (json.JSONDecodeError, TypeError):
                    child_ids = []

            results.append(
                ParentChunk(
                    parent_chunk_id=row["parent_chunk_id"],
                    article_id=row["article_id"],
                    content=row["content"],
                    token_count=row["token_count"],
                    child_chunk_ids=child_ids,
                    doc_name=row["doc_name"] or "",
                    source=row["source"] or "",
                    url=row["url"] or "",
                )
            )
        return results

    def delete_parent_chunks_by_article_ids(
        self, article_ids: list[int]
    ) -> int:
        """删除指定文章 ID 关联的所有父 chunks。"""
        if not article_ids:
            return 0

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM parent_chunks WHERE article_id = ANY(%s)",
                    (article_ids,),
                )
                deleted = cur.rowcount

        logger.info(f"删除 {deleted} 个父 chunks (文章 IDs: {article_ids})")
        return deleted

    def search_parent_chunks_by_keyword(
        self, query: str, top_k: int = 20
    ) -> list[tuple[ParentChunk, float]]:
        """使用 PostgreSQL 全文搜索在父 chunks 中检索。

        Args:
            query: 查询文本（会在内部使用 jieba 分词）。
            top_k: 返回结果数量。

        Returns:
            [(ParentChunk, ts_rank_score), ...] 按分数降序。
        """
        # 使用 jieba 分词并构建 tsquery
        segmented = self._segment_text(query)
        if not segmented.strip():
            return []

        # 将分词结果转为 & 连接的 tsquery 格式
        terms = [t.strip() for t in segmented.split() if t.strip()]
        if not terms:
            return []
        tsquery_str = " | ".join(terms)  # 用 OR 连接，扩大召回

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """SELECT *, ts_rank(search_vector, query) AS rank
                           FROM parent_chunks,
                                to_tsquery('simple', %s) AS query
                           WHERE search_vector @@ query
                           ORDER BY rank DESC
                           LIMIT %s""",
                        (tsquery_str, top_k),
                    )
                    rows = cur.fetchall()
                except Exception as e:
                    logger.error(f"全文搜索父 chunks 失败: {e}")
                    return []

        results = []
        for row in rows:
            child_ids = row["child_chunk_ids"]
            if isinstance(child_ids, str):
                try:
                    child_ids = json.loads(child_ids)
                except (json.JSONDecodeError, TypeError):
                    child_ids = []

            pc = ParentChunk(
                parent_chunk_id=row["parent_chunk_id"],
                article_id=row["article_id"],
                content=row["content"],
                token_count=row["token_count"],
                child_chunk_ids=child_ids,
                doc_name=row["doc_name"] or "",
                source=row["source"] or "",
                url=row["url"] or "",
            )
            results.append((pc, float(row["rank"])))

        logger.info(f"关键词搜索父 chunks: 查询='{query}' → {len(results)} 条结果")
        return results

    def backfill_search_vectors(self) -> int:
        """为缺失 search_vector 的已有父 chunks 回填全文索引。

        使用 jieba 分词处理每个父 chunk 的 content，
        生成 tsvector 并写回数据库。

        Returns:
            更新的记录数。
        """
        # 先查出所有缺失 search_vector 的记录
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT parent_chunk_id, content FROM parent_chunks WHERE search_vector IS NULL"
                )
                rows = cur.fetchall()

        if not rows:
            logger.info("backfill: 无需回填，所有父 chunks 已有 search_vector")
            return 0

        updated = 0
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    try:
                        segmented = self._segment_text(row["content"])
                        cur.execute(
                            """UPDATE parent_chunks
                               SET search_vector = to_tsvector('simple', %s)
                               WHERE parent_chunk_id = %s""",
                            (segmented, row["parent_chunk_id"]),
                        )
                        updated += 1
                    except Exception as e:
                        logger.error(
                            f"回填 search_vector 失败 ({row['parent_chunk_id']}): {e}"
                        )

        logger.info(f"backfill 完成: 更新 {updated}/{len(rows)} 个父 chunks 的 search_vector")
        return updated

    # ------------------------------------------------------------------
    # 文本分词工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _segment_text(text: str) -> str:
        """使用 jieba 对文本分词，返回空格分隔的分词结果。

        同时处理中文和英文：jieba 会保留英文单词，
        中文按词语切分后用空格连接，供 PostgreSQL simple 分词器使用。
        """
        if not text:
            return ""
        words = jieba.cut(text)
        return " ".join(w.strip() for w in words if w.strip())
