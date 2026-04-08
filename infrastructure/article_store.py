"""SQLite 文章存储，实现 ArticleStoreProtocol"""
import hashlib
import logging
import os
import sqlite3
from datetime import datetime, timedelta

from models.article import Article, Language, ArticleStatus

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash     TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    content      TEXT,
    html_content TEXT,
    summary      TEXT,
    source       TEXT,
    language     TEXT,
    published_at TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    status       TEXT DEFAULT 'stored'
);

CREATE INDEX IF NOT EXISTS idx_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at);
CREATE INDEX IF NOT EXISTS idx_source ON articles(source);
"""


class SQLiteArticleStore:
    """实现 ArticleStoreProtocol"""

    def __init__(self, db_path: str):
        """初始化时自动创建数据库和表"""
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript(_CREATE_TABLE_SQL)
            try:
                conn.execute("ALTER TABLE articles ADD COLUMN html_content TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # already exists

    @staticmethod
    def _hash_url(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_article(row: sqlite3.Row) -> Article:
        """将数据库行转为 Article 对象"""
        published_at = None
        if row["published_at"]:
            try:
                published_at = datetime.fromisoformat(row["published_at"])
            except (ValueError, TypeError):
                pass

        created_at = datetime.now()
        if row["created_at"]:
            try:
                created_at = datetime.fromisoformat(row["created_at"])
            except (ValueError, TypeError):
                pass

        return Article(
            id=row["id"],
            url_hash=row["url_hash"],
            title=row["title"],
            url=row["url"],
            content=row["content"] or "",
            html_content=row["html_content"] if "html_content" in row.keys() and row["html_content"] else "",
            summary=row["summary"] or "",
            source=row["source"] or "",
            language=Language(row["language"]) if row["language"] else Language.UNKNOWN,
            published_at=published_at,
            created_at=created_at,
            status=ArticleStatus(row["status"]) if row["status"] else ArticleStatus.STORED,
        )

    def save_articles(self, articles: list[Article]) -> int:
        """
        去重后写入数据库。
        去重：SHA256(url) → url_hash，存在则跳过。
        返回实际新增数量。
        """
        new_count = 0
        with self._get_conn() as conn:
            for article in articles:
                url_hash = self._hash_url(article.url)
                try:
                    conn.execute(
                        """INSERT INTO articles
                           (url_hash, title, url, content, html_content, summary, source,
                            language, published_at, created_at, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            url_hash,
                            article.title,
                            article.url,
                            article.content,
                            article.html_content,
                            article.summary,
                            article.source,
                            article.language.value,
                            article.published_at.isoformat()
                            if article.published_at
                            else None,
                            datetime.now().isoformat(),
                            ArticleStatus.STORED.value,
                        ),
                    )
                    new_count += 1
                except sqlite3.IntegrityError:
                    # url_hash 重复，跳过
                    pass
        logger.info(f"保存文章: {new_count}/{len(articles)} 篇为新文章")
        return new_count

    def get_unembedded(self, limit: int = 100) -> list[Article]:
        """返回 status != 'embedded' 的文章"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM articles WHERE status != ? ORDER BY created_at DESC LIMIT ?",
                (ArticleStatus.EMBEDDED.value, limit),
            ).fetchall()
        return [self._row_to_article(row) for row in rows]

    def mark_embedded(self, article_ids: list[int]) -> None:
        """将指定 id 的文章 status 设为 'embedded'"""
        if not article_ids:
            return
        with self._get_conn() as conn:
            placeholders = ",".join("?" for _ in article_ids)
            conn.execute(
                f"UPDATE articles SET status = ? WHERE id IN ({placeholders})",
                [ArticleStatus.EMBEDDED.value] + list(article_ids),
            )
        logger.info(f"标记 {len(article_ids)} 篇文章为已向量化")

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Article]:
        """LIKE 关键词搜索 title + content"""
        pattern = f"%{keyword}%"
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM articles
                   WHERE title LIKE ? OR content LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (pattern, pattern, limit),
            ).fetchall()
        return [self._row_to_article(row) for row in rows]

    def get_recent(self, hours: int = 24, limit: int = 50) -> list[Article]:
        """返回最近 N 小时内的文章"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM articles
                   WHERE created_at >= ?
                   ORDER BY created_at DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [self._row_to_article(row) for row in rows]

    def get_stats(self) -> dict:
        """
        返回统计信息：
        {"total": int, "embedded": int, "today_new": int,
         "oldest_date": str, "sources": list[str]}
        """
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            embedded = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE status = ?",
                (ArticleStatus.EMBEDDED.value,),
            ).fetchone()[0]

            today_start = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            today_new = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE created_at >= ?",
                (today_start,),
            ).fetchone()[0]

            oldest_row = conn.execute(
                "SELECT MIN(created_at) FROM articles"
            ).fetchone()
            oldest_date = oldest_row[0] if oldest_row and oldest_row[0] else "无数据"

            source_rows = conn.execute(
                "SELECT DISTINCT source FROM articles WHERE source IS NOT NULL"
            ).fetchall()
            sources = [row[0] for row in source_rows if row[0]]

        return {
            "total": total,
            "embedded": embedded,
            "today_new": today_new,
            "oldest_date": oldest_date,
            "sources": sources,
        }

    def cleanup_old_articles(self, retention_days: int = 90) -> int:
        """删除超过 retention_days 天的文章，返回删除数量"""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM articles WHERE created_at < ?", (cutoff,)
            )
            deleted = cursor.rowcount
        logger.info(f"清理旧文章: 删除 {deleted} 篇（保留 {retention_days} 天）")
        return deleted

    def delete_articles(self, article_ids: list[int]) -> int:
        """依据 ID 进行批量精准删除"""
        if not article_ids:
            return 0
        with self._get_conn() as conn:
            placeholders = ",".join("?" for _ in article_ids)
            cursor = conn.execute(
                f"DELETE FROM articles WHERE id IN ({placeholders})",
                article_ids,
            )
            deleted = cursor.rowcount
        logger.info(f"据 ID 成功删除 {deleted} 篇文章记录")
        return deleted

    def get_article_by_id(self, article_id: int) -> Article | None:
        """按 ID 获取单篇文章"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM articles WHERE id = ?", (article_id,)
            ).fetchone()
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
        """分页查询文章，支持来源/语言/关键词筛选"""
        conditions = []
        params: list = []

        if source:
            conditions.append("source = ?")
            params.append(source)
        if language:
            conditions.append("language = ?")
            params.append(language)
        if keyword:
            conditions.append("(title LIKE ? OR content LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        offset = (page - 1) * page_size
        params.extend([page_size, offset])

        with self._get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM articles {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [self._row_to_article(row) for row in rows]

    def count_articles(
        self,
        source: str | None = None,
        language: str | None = None,
        keyword: str | None = None,
    ) -> int:
        """统计符合筛选条件的文章数量"""
        conditions = []
        params: list = []

        if source:
            conditions.append("source = ?")
            params.append(source)
        if language:
            conditions.append("language = ?")
            params.append(language)
        if keyword:
            conditions.append("(title LIKE ? OR content LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with self._get_conn() as conn:
            count = conn.execute(
                f"SELECT COUNT(*) FROM articles {where}", params
            ).fetchone()[0]
        return count
