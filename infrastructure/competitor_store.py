"""竞品数据存储 — CompetitorStoreProtocol 的 PostgreSQL 实现"""
from __future__ import annotations

import json
from datetime import datetime

import psycopg2
import psycopg2.extras
import structlog

from models.competitor import Competitor, CompetitorProduct

logger = structlog.get_logger(__name__)


class PostgresCompetitorStore:
    """竞品与产品线的 PostgreSQL CRUD + 情报关联。"""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn)

    # ================================================================
    # Competitor CRUD
    # ================================================================

    def save_competitor(self, competitor: Competitor) -> Competitor:
        """创建或更新（按 name upsert）。"""
        sql = """
            INSERT INTO competitors (name, aliases, website, industry, description,
                                     logo_url, tags, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (name)
            DO UPDATE SET
                aliases     = EXCLUDED.aliases,
                website     = EXCLUDED.website,
                industry    = EXCLUDED.industry,
                description = EXCLUDED.description,
                logo_url    = EXCLUDED.logo_url,
                tags        = EXCLUDED.tags,
                status      = EXCLUDED.status,
                updated_at  = EXCLUDED.updated_at
            RETURNING id, created_at, updated_at
        """
        now = datetime.now()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    competitor.name,
                    json.dumps(competitor.aliases, ensure_ascii=False),
                    competitor.website,
                    competitor.industry,
                    competitor.description,
                    competitor.logo_url,
                    json.dumps(competitor.tags, ensure_ascii=False),
                    competitor.status,
                    competitor.created_at or now,
                    now,
                ))
                row = cur.fetchone()
                competitor.id = row[0]
                competitor.created_at = row[1]
                competitor.updated_at = row[2]
            conn.commit()
        logger.info("competitor.saved", name=competitor.name, id=competitor.id)
        return competitor

    def get_competitor(self, competitor_id: int) -> Competitor | None:
        sql = "SELECT * FROM competitors WHERE id = %s"
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (competitor_id,))
                row = cur.fetchone()
        return self._row_to_competitor(row) if row else None

    def list_competitors(
        self, status: str = "active", limit: int = 100
    ) -> list[Competitor]:
        sql = "SELECT * FROM competitors WHERE status = %s ORDER BY name LIMIT %s"
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (status, limit))
                rows = cur.fetchall()
        return [self._row_to_competitor(r) for r in rows]

    def search_competitors(self, query: str) -> list[Competitor]:
        """按名称/别名模糊搜索。"""
        sql = """
            SELECT * FROM competitors
            WHERE name ILIKE %s
               OR aliases::text ILIKE %s
            ORDER BY name
            LIMIT 20
        """
        pattern = f"%{query}%"
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (pattern, pattern))
                rows = cur.fetchall()
        return [self._row_to_competitor(r) for r in rows]

    def delete_competitor(self, competitor_id: int) -> None:
        sql = "DELETE FROM competitors WHERE id = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (competitor_id,))
            conn.commit()
        logger.info("competitor.deleted", id=competitor_id)

    # ================================================================
    # CompetitorProduct CRUD
    # ================================================================

    def save_product(self, product: CompetitorProduct) -> CompetitorProduct:
        sql = """
            INSERT INTO competitor_products
                (competitor_id, name, description, category, url, pricing_info,
                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING id, created_at, updated_at
        """
        now = datetime.now()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    product.competitor_id,
                    product.name,
                    product.description,
                    product.category,
                    product.url,
                    product.pricing_info,
                    product.created_at or now,
                    now,
                ))
                row = cur.fetchone()
                if row:
                    product.id = row[0]
                    product.created_at = row[1]
                    product.updated_at = row[2]
            conn.commit()
        return product

    def list_products(self, competitor_id: int) -> list[CompetitorProduct]:
        sql = """
            SELECT * FROM competitor_products
            WHERE competitor_id = %s ORDER BY name
        """
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (competitor_id,))
                rows = cur.fetchall()
        return [self._row_to_product(r) for r in rows]

    def delete_product(self, product_id: int) -> None:
        sql = "DELETE FROM competitor_products WHERE id = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (product_id,))
            conn.commit()

    # ================================================================
    # 情报关联
    # ================================================================

    def link_intel_to_competitor(
        self, document_id: str, competitor_id: int
    ) -> None:
        sql = """
            INSERT INTO intel_competitors (document_id, competitor_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (document_id, competitor_id))
            conn.commit()

    def unlink_intel_from_competitor(
        self, document_id: str, competitor_id: int
    ) -> None:
        sql = """
            DELETE FROM intel_competitors
            WHERE document_id = %s AND competitor_id = %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (document_id, competitor_id))
            conn.commit()

    def get_competitor_ids_for_intel(self, document_id: str) -> list[int]:
        sql = "SELECT competitor_id FROM intel_competitors WHERE document_id = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (document_id,))
                return [row[0] for row in cur.fetchall()]

    def get_intel_ids_for_competitor(
        self,
        competitor_id: int,
        intel_type: str | None = None,
        limit: int = 50,
    ) -> list[str]:
        if intel_type:
            sql = """
                SELECT ic.document_id FROM intel_competitors ic
                JOIN source_documents d ON d.id = ic.document_id
                WHERE ic.competitor_id = %s AND d.intel_type = %s
                ORDER BY d.created_at DESC LIMIT %s
            """
            params = (competitor_id, intel_type, limit)
        else:
            sql = """
                SELECT ic.document_id FROM intel_competitors ic
                JOIN source_documents d ON d.id = ic.document_id
                WHERE ic.competitor_id = %s
                ORDER BY d.created_at DESC LIMIT %s
            """
            params = (competitor_id, limit)

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [row[0] for row in cur.fetchall()]

    # ================================================================
    # 批量关联（Pipeline 使用）
    # ================================================================

    def bulk_link_intel_to_competitors(
        self, links: list[tuple[str, int]]
    ) -> int:
        """批量关联情报与竞品。links = [(document_id, competitor_id), ...]"""
        if not links:
            return 0
        sql = """
            INSERT INTO intel_competitors (document_id, competitor_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, links)
                count = cur.rowcount
            conn.commit()
        logger.info("intel_competitors.bulk_linked", count=count)
        return count

    # ================================================================
    # Row Mappers
    # ================================================================

    @staticmethod
    def _row_to_competitor(row: dict) -> Competitor:
        aliases = row.get("aliases", [])
        if isinstance(aliases, str):
            aliases = json.loads(aliases)
        tags = row.get("tags", [])
        if isinstance(tags, str):
            tags = json.loads(tags)
        return Competitor(
            id=row["id"],
            name=row["name"],
            aliases=aliases or [],
            website=row.get("website", ""),
            industry=row.get("industry", ""),
            description=row.get("description", ""),
            logo_url=row.get("logo_url", ""),
            tags=tags or [],
            status=row.get("status", "active"),
            created_at=row.get("created_at", datetime.now()),
            updated_at=row.get("updated_at", datetime.now()),
        )

    @staticmethod
    def _row_to_product(row: dict) -> CompetitorProduct:
        return CompetitorProduct(
            id=row["id"],
            competitor_id=row["competitor_id"],
            name=row["name"],
            description=row.get("description", ""),
            category=row.get("category", ""),
            url=row.get("url", ""),
            pricing_info=row.get("pricing_info", ""),
            created_at=row.get("created_at", datetime.now()),
            updated_at=row.get("updated_at", datetime.now()),
        )
