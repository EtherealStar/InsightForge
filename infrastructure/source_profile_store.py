"""来源档案的 PostgreSQL 权威存储。"""
from __future__ import annotations

from uuid import uuid4

import psycopg2
import psycopg2.extras

from models.source_governance import SourceKind, SourceProfile, SourceProfileRevision, SourceTier


class PostgresSourceProfileStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn)

    def resolve_domain(self, domain: str) -> SourceProfile | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT profile.*, revision.id AS revision_id
                   FROM source_profiles profile
                   LEFT JOIN LATERAL (
                       SELECT id FROM source_profile_revisions
                       WHERE profile_id = profile.id ORDER BY created_at DESC LIMIT 1
                   ) revision ON TRUE
                   WHERE profile.domain = %s""",
                (domain,),
            )
            row = cur.fetchone()
        return self._profile(row) if row else None

    def list_profiles(self, *, tier: str | None = None) -> list[SourceProfile]:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if tier:
                cur.execute(self._list_sql("WHERE profile.tier=%s"), (tier,))
            else:
                cur.execute(self._list_sql())
            return [self._profile(row) for row in cur.fetchall()]

    def save_profile(self, profile: SourceProfile, *, actor: str, reason: str) -> SourceProfile:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO source_profiles (id, domain, tier, source_kind, inherit_to_subdomains)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (domain) DO UPDATE SET tier=EXCLUDED.tier, source_kind=EXCLUDED.source_kind,
                   inherit_to_subdomains=EXCLUDED.inherit_to_subdomains, updated_at=NOW()
                   RETURNING id""",
                (profile.id, profile.domain, profile.tier.value, profile.source_kind.value, profile.inherit_to_subdomains),
            )
            profile.id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO source_profile_revisions (id, profile_id, tier, source_kind, actor, reason) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, created_at",
                (profile.revision_id or str(uuid4()), profile.id, profile.tier.value, profile.source_kind.value, actor, reason),
            )
            profile.revision_id, _ = cur.fetchone()
            conn.commit()
        return profile

    def list_revisions(self, profile_id: str) -> list[SourceProfileRevision]:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM source_profile_revisions WHERE profile_id=%s ORDER BY created_at DESC", (profile_id,))
            return [SourceProfileRevision(profile_id=row["profile_id"], tier=SourceTier(row["tier"]), source_kind=SourceKind(row["source_kind"]), reason=row["reason"], actor=row["actor"], id=row["id"], created_at=row["created_at"]) for row in cur.fetchall()]

    @staticmethod
    def _list_sql(where: str = "") -> str:
        return f"""SELECT profile.*, revision.id AS revision_id
                    FROM source_profiles profile
                    LEFT JOIN LATERAL (
                        SELECT id FROM source_profile_revisions
                        WHERE profile_id = profile.id ORDER BY created_at DESC LIMIT 1
                    ) revision ON TRUE
                    {where} ORDER BY profile.domain"""

    @staticmethod
    def _profile(row):
        return SourceProfile(domain=row["domain"], tier=SourceTier(row["tier"]), source_kind=SourceKind(row["source_kind"]), inherit_to_subdomains=row["inherit_to_subdomains"], id=row["id"], revision_id=row.get("revision_id"), created_at=row.get("created_at"), updated_at=row.get("updated_at"))
