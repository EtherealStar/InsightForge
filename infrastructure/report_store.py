"""分析报告存储 — ReportStoreProtocol 的 PostgreSQL 实现"""
from __future__ import annotations

import json
from datetime import datetime

import psycopg2
import psycopg2.extras
import structlog

from models.report import (
    AnalysisReport,
    ReportClaimRef,
    ReportEvidenceRef,
    ReportQualityReview,
    ReportReviewStatus,
    ReportType,
    ReportStatus,
)

logger = structlog.get_logger(__name__)


class PostgresReportStore:
    """分析报告 + 审计日志的 PostgreSQL 实现。"""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn)

    # ================================================================
    # Report CRUD
    # ================================================================

    def save_report(self, report: AnalysisReport) -> AnalysisReport:
        """创建或更新报告。"""
        if report.id:
            return self._update_report(report)
        return self._create_report(report)

    def _create_report(self, report: AnalysisReport) -> AnalysisReport:
        sql = """
            INSERT INTO analysis_reports
                (title, report_type, competitor_ids, content, source_refs,
                 audit_trail, status, session_id, report_filename,
                 version, review_status, quality_score, quality_summary,
                 generation_context_hash, published_at, approved_by, approved_at,
                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at, updated_at
        """
        now = datetime.now()
        report_type = _enum_value(report.report_type)
        status = _enum_value(report.status)
        review_status = _enum_value(report.review_status)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    report.title,
                    report_type,
                    json.dumps(report.competitor_ids),
                    report.content,
                    json.dumps(report.source_refs, ensure_ascii=False),
                    json.dumps(report.audit_trail, ensure_ascii=False),
                    status,
                    report.session_id,
                    report.report_filename,
                    report.version,
                    review_status,
                    report.quality_score,
                    report.quality_summary,
                    report.generation_context_hash,
                    report.published_at,
                    report.approved_by,
                    report.approved_at,
                    report.created_at or now,
                    now,
                ))
                row = cur.fetchone()
                report.id = row[0]
                report.created_at = row[1]
                report.updated_at = row[2]
            conn.commit()
        logger.info("report.created", id=report.id, title=report.title)
        return report

    def _update_report(self, report: AnalysisReport) -> AnalysisReport:
        sql = """
            UPDATE analysis_reports SET
                title = %s,
                report_type = %s,
                competitor_ids = %s,
                content = %s,
                source_refs = %s,
                audit_trail = %s,
                status = %s,
                session_id = %s,
                report_filename = %s,
                version = %s,
                review_status = %s,
                quality_score = %s,
                quality_summary = %s,
                generation_context_hash = %s,
                published_at = %s,
                approved_by = %s,
                approved_at = %s,
                updated_at = %s
            WHERE id = %s
            RETURNING updated_at
        """
        now = datetime.now()
        report_type = _enum_value(report.report_type)
        status = _enum_value(report.status)
        review_status = _enum_value(report.review_status)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    report.title,
                    report_type,
                    json.dumps(report.competitor_ids),
                    report.content,
                    json.dumps(report.source_refs, ensure_ascii=False),
                    json.dumps(report.audit_trail, ensure_ascii=False),
                    status,
                    report.session_id,
                    report.report_filename,
                    report.version,
                    review_status,
                    report.quality_score,
                    report.quality_summary,
                    report.generation_context_hash,
                    report.published_at,
                    report.approved_by,
                    report.approved_at,
                    now,
                    report.id,
                ))
                row = cur.fetchone()
                if row:
                    report.updated_at = row[0]
            conn.commit()
        logger.info("report.updated", id=report.id)
        return report

    def get_report(self, report_id: int) -> AnalysisReport | None:
        sql = "SELECT * FROM analysis_reports WHERE id = %s"
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (report_id,))
                row = cur.fetchone()
        return self._row_to_report(row) if row else None

    def list_reports(
        self,
        report_type: str | None = None,
        status: str | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> list[AnalysisReport]:
        conditions = []
        params: list = []
        if report_type:
            conditions.append("report_type = %s")
            params.append(report_type)
        if status:
            conditions.append("status = %s")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT * FROM analysis_reports {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [self._row_to_report(r) for r in rows]

    def delete_report(self, report_id: int) -> None:
        sql = "DELETE FROM analysis_reports WHERE id = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (report_id,))
            conn.commit()
        logger.info("report.deleted", id=report_id)

    def update_report_status(
        self,
        report_id: int,
        status: str,
        *,
        review_status: str | None = None,
        quality_score: float | None = None,
        quality_summary: str | None = None,
        actor: str = "system",
    ) -> AnalysisReport:
        """Update report workflow status and optional latest review summary."""
        status = _enum_value(status)
        assignments = ["status = %s", "updated_at = %s"]
        params: list = [status, datetime.now()]
        if review_status is not None:
            assignments.append("review_status = %s")
            params.append(_enum_value(review_status))
        if quality_score is not None:
            assignments.append("quality_score = %s")
            params.append(quality_score)
        if quality_summary is not None:
            assignments.append("quality_summary = %s")
            params.append(quality_summary)
        if status == ReportStatus.APPROVED.value:
            assignments.append("approved_by = %s")
            assignments.append("approved_at = %s")
            params.extend([actor, datetime.now()])
        if status == ReportStatus.PUBLISHED.value:
            assignments.append("published_at = %s")
            params.append(datetime.now())
        params.append(report_id)
        sql = f"""
            UPDATE analysis_reports
            SET {', '.join(assignments)}
            WHERE id = %s
            RETURNING *
        """
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise ValueError(f"Report not found: {report_id}")
        return self._row_to_report(row)

    # ================================================================
    # Report relationships and quality reviews
    # ================================================================

    def attach_claims(
        self, report_id: int, claim_refs: list[ReportClaimRef]
    ) -> None:
        sql = """
            INSERT INTO report_claims
                (report_id, claim_id, section_key, position, usage_type, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (report_id, claim_id, section_key, usage_type)
            DO UPDATE SET position = EXCLUDED.position
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                for ref in claim_refs:
                    cur.execute(
                        sql,
                        (
                            report_id,
                            ref.claim_id,
                            ref.section_key,
                            ref.position,
                            ref.usage_type,
                            ref.created_at or datetime.now(),
                        ),
                    )
            conn.commit()

    def list_report_claims(self, report_id: int) -> list[ReportClaimRef]:
        sql = """
            SELECT report_id, claim_id, section_key, position, usage_type, created_at
            FROM report_claims
            WHERE report_id = %s
            ORDER BY section_key ASC, position ASC, created_at ASC
        """
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (report_id,))
                rows = cur.fetchall()
        return [
            ReportClaimRef(
                report_id=row["report_id"],
                claim_id=row["claim_id"],
                section_key=row["section_key"],
                position=row["position"],
                usage_type=row["usage_type"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def attach_evidence_refs(
        self, report_id: int, evidence_refs: list[ReportEvidenceRef]
    ) -> None:
        sql = """
            INSERT INTO report_evidence_refs
                (id, report_id, evidence_ref_id, claim_id, fact_id, section_key,
                 citation_label, url, title, snippet, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id)
            DO UPDATE SET
                evidence_ref_id = EXCLUDED.evidence_ref_id,
                claim_id = EXCLUDED.claim_id,
                fact_id = EXCLUDED.fact_id,
                section_key = EXCLUDED.section_key,
                citation_label = EXCLUDED.citation_label,
                url = EXCLUDED.url,
                title = EXCLUDED.title,
                snippet = EXCLUDED.snippet
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                for ref in evidence_refs:
                    cur.execute(
                        sql,
                        (
                            ref.id,
                            report_id,
                            ref.evidence_ref_id,
                            ref.claim_id,
                            ref.fact_id,
                            ref.section_key,
                            ref.citation_label,
                            ref.url,
                            ref.title,
                            ref.snippet,
                            ref.created_at or datetime.now(),
                        ),
                    )
            conn.commit()

    def list_report_evidence_refs(
        self, report_id: int
    ) -> list[ReportEvidenceRef]:
        sql = """
            SELECT *
            FROM report_evidence_refs
            WHERE report_id = %s
            ORDER BY section_key ASC, citation_label ASC, created_at ASC
        """
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (report_id,))
                rows = cur.fetchall()
        return [
            ReportEvidenceRef(
                id=row["id"],
                report_id=row["report_id"],
                evidence_ref_id=row["evidence_ref_id"],
                claim_id=row["claim_id"],
                fact_id=row["fact_id"],
                section_key=row["section_key"],
                citation_label=row["citation_label"],
                url=row["url"],
                title=row["title"],
                snippet=row["snippet"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_quality_review(
        self, review: ReportQualityReview
    ) -> ReportQualityReview:
        sql = """
            INSERT INTO report_quality_reviews
                (id, report_id, review_type, status, overall_score,
                 dimension_scores, issues, revision_suggestions,
                 model_provider, model_name, prompt_version, reviewed_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id)
            DO UPDATE SET
                review_type = EXCLUDED.review_type,
                status = EXCLUDED.status,
                overall_score = EXCLUDED.overall_score,
                dimension_scores = EXCLUDED.dimension_scores,
                issues = EXCLUDED.issues,
                revision_suggestions = EXCLUDED.revision_suggestions,
                model_provider = EXCLUDED.model_provider,
                model_name = EXCLUDED.model_name,
                prompt_version = EXCLUDED.prompt_version,
                reviewed_by = EXCLUDED.reviewed_by
            RETURNING created_at
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        review.id,
                        review.report_id,
                        review.review_type,
                        _enum_value(review.status),
                        review.overall_score,
                        json.dumps(review.dimension_scores, ensure_ascii=False),
                        json.dumps(review.issues, ensure_ascii=False),
                        json.dumps(review.revision_suggestions, ensure_ascii=False),
                        review.model_provider,
                        review.model_name,
                        review.prompt_version,
                        review.reviewed_by,
                        review.created_at or datetime.now(),
                    ),
                )
                row = cur.fetchone()
                review.created_at = row[0]
            conn.commit()
        return review

    def list_quality_reviews(
        self, report_id: int
    ) -> list[ReportQualityReview]:
        sql = """
            SELECT *
            FROM report_quality_reviews
            WHERE report_id = %s
            ORDER BY created_at DESC
        """
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (report_id,))
                rows = cur.fetchall()
        return [self._row_to_quality_review(row) for row in rows]

    # ================================================================
    # 审计日志
    # ================================================================

    def append_audit_log(
        self,
        report_id: int | None,
        session_id: str | None,
        action: str,
        detail: dict,
        source_refs: list[dict] | None = None,
    ) -> None:
        """追加审计日志条目。"""
        sql = """
            INSERT INTO analysis_audit_log
                (report_id, session_id, action, detail, source_refs, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    report_id,
                    session_id,
                    action,
                    json.dumps(detail, ensure_ascii=False),
                    json.dumps(source_refs or [], ensure_ascii=False),
                    datetime.now(),
                ))
            conn.commit()

    def get_audit_trail(self, report_id: int) -> list[dict]:
        """获取报告的完整审计链路。"""
        sql = """
            SELECT id, session_id, action, detail, source_refs, created_at
            FROM analysis_audit_log
            WHERE report_id = %s
            ORDER BY created_at ASC
        """
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (report_id,))
                rows = cur.fetchall()
        return [
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "action": r["action"],
                "detail": r["detail"] if isinstance(r["detail"], dict) else json.loads(r["detail"] or "{}"),
                "source_refs": r["source_refs"] if isinstance(r["source_refs"], list) else json.loads(r["source_refs"] or "[]"),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    # ================================================================
    # Row Mapper
    # ================================================================

    @staticmethod
    def _row_to_report(row: dict) -> AnalysisReport:
        competitor_ids = _json_loads(row.get("competitor_ids", []), [])
        source_refs = _json_loads(row.get("source_refs", []), [])
        audit_trail = _json_loads(row.get("audit_trail", []), [])

        report_type_val = row.get("report_type", "overview")
        try:
            report_type = ReportType(report_type_val)
        except ValueError:
            report_type = ReportType.OVERVIEW

        status_val = row.get("status", "draft")
        try:
            status = ReportStatus(status_val)
        except ValueError:
            status = ReportStatus.DRAFT

        review_status_val = row.get("review_status", "not_reviewed")
        try:
            review_status = ReportReviewStatus(review_status_val)
        except ValueError:
            review_status = ReportReviewStatus.NOT_REVIEWED

        return AnalysisReport(
            id=row["id"],
            title=row["title"],
            report_type=report_type,
            competitor_ids=competitor_ids or [],
            content=row.get("content", ""),
            source_refs=source_refs or [],
            audit_trail=audit_trail or [],
            status=status,
            review_status=review_status,
            quality_score=row.get("quality_score"),
            quality_summary=row.get("quality_summary", "") or "",
            generation_context_hash=row.get("generation_context_hash", "") or "",
            version=row.get("version", 1) or 1,
            session_id=row.get("session_id"),
            report_filename=row.get("report_filename"),
            approved_by=row.get("approved_by"),
            approved_at=row.get("approved_at"),
            published_at=row.get("published_at"),
            created_at=row.get("created_at", datetime.now()),
            updated_at=row.get("updated_at", datetime.now()),
        )

    @staticmethod
    def _row_to_quality_review(row: dict) -> ReportQualityReview:
        status_val = row.get("status", "failed")
        try:
            status = ReportReviewStatus(status_val)
        except ValueError:
            status = status_val
        return ReportQualityReview(
            id=row["id"],
            report_id=row["report_id"],
            review_type=row["review_type"],
            status=status,
            overall_score=row.get("overall_score", 0.0) or 0.0,
            dimension_scores=_json_loads(row.get("dimension_scores", {}), {}),
            issues=_json_loads(row.get("issues", []), []),
            revision_suggestions=_json_loads(
                row.get("revision_suggestions", []), []
            ),
            model_provider=row.get("model_provider", "") or "",
            model_name=row.get("model_name", "") or "",
            prompt_version=row.get("prompt_version", "") or "",
            reviewed_by=row.get("reviewed_by", "system") or "system",
            created_at=row.get("created_at"),
        )


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _json_loads(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value or json.dumps(default))
    return value
