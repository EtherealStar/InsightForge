"""Verification service for the v2 three-layer model (Milestone 3).

Reads from:
  * ``fact_evidence`` (stance)
  * ``evidence_refs.document_version_id`` → ``source_document_versions.document_id``
  * ``source_occurrences`` × ``document_clusters`` to determine Document Cluster
  * ``source_profiles`` + ``source_profile_competitors`` + ``intel_fact_competitors``
    to detect self_reported facts

Produces one of ``single_source``, ``self_reported``, ``corroborated`` or
``disputed``. Source tier only decides whether an evidence anchor is
admissible; it is never written to the fact as a score.

A fact with no supporting anchor always reports ``single_source`` with
``status_reason`` describing the missing support; it cannot become active.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor

from models.target_intel import (
    FactEntityRole,
    LinkReviewStatus,
    VerificationStatus,
)


@dataclass
class VerificationResult:
    status: VerificationStatus | None
    reason: str
    supporting_clusters: list[str]
    contradicting_clusters: list[str]


class EvidenceVerificationServiceV2:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    def derive_status(self, fact_id: str) -> VerificationResult:
        """Compute verification_status + status_reason for a fact.

        Rules (applied in order):
          1. Any ``stance='contradicts'`` anchor from a qualified cluster
             ⇒ disputed.
          2. All supporting anchors come from clusters whose Source Profile
             is controlled by a confirmed subject competitor of the fact
             ⇒ self_reported.
          3. ≥ 2 distinct, admitted, independent Document Clusters carry
             supports ⇒ corroborated.
          4. 1 distinct admitted cluster ⇒ single_source.
          5. Otherwise single_source with status_reason explaining what is
             missing.
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT i.lifecycle_status
                      FROM intel_facts i
                     WHERE i.id = %s
                    """,
                    (fact_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return VerificationResult(
                        status=None, reason="fact not found",
                        supporting_clusters=[], contradicting_clusters=[],
                    )
                if row["lifecycle_status"] is None:
                    return VerificationResult(
                        status=None, reason="legacy fact",
                        supporting_clusters=[], contradicting_clusters=[],
                    )

                # Resolve per-anchor cluster + stance + tier + controlled-by-subject.
                cur.execute(
                    """
                    SELECT fe.stance,
                           v.document_id AS cluster_id,
                           o.source_tier,
                           p.id AS profile_id
                      FROM fact_evidence fe
                      JOIN evidence_refs e ON e.id = fe.evidence_ref_id
                      JOIN source_document_versions v
                        ON v.id = e.document_version_id
                      JOIN source_occurrences o
                        ON o.id = e.source_occurrence_id
                      LEFT JOIN source_profile_revisions spr
                        ON spr.id = o.source_profile_revision_id
                      LEFT JOIN source_profiles p
                        ON p.id = spr.profile_id
                     WHERE fe.fact_id = %s
                       AND e.quoted_text IS NOT NULL
                    """,
                    (fact_id,),
                )
                anchors = cur.fetchall()

                # Find confirmed subject competitor ids for the fact.
                cur.execute(
                    """
                    SELECT competitor_id FROM intel_fact_competitors
                     WHERE fact_id = %s AND role = 'subject' AND review_status = 'confirmed'
                    """,
                    (fact_id,),
                )
                subject_competitors = [r["competitor_id"] for r in cur.fetchall()]

                # Find profile ids controlled by those competitors.
                controlled_profiles: set[str] = set()
                if subject_competitors:
                    cur.execute(
                        """
                        SELECT profile_id FROM source_profile_competitors
                         WHERE competitor_id = ANY(%s)
                        """,
                        (subject_competitors,),
                    )
                    controlled_profiles = {r["profile_id"] for r in cur.fetchall()}

        if not anchors:
            return VerificationResult(
                status=VerificationStatus.SINGLE_SOURCE,
                reason="no formal anchor; cannot confirm",
                supporting_clusters=[],
                contradicting_clusters=[],
            )

        # Admitted clusters = tier A/B/C with profile.
        def admitted(r) -> bool:
            return r["source_tier"] in ("A", "B", "C")

        supports = [a for a in anchors if a["stance"] == "supports" and admitted(a)]
        contradicts = [a for a in anchors if a["stance"] == "contradicts" and admitted(a)]
        sup_clusters = {a["cluster_id"] for a in supports}
        contra_clusters = {a["cluster_id"] for a in contradicts}

        if contra_clusters:
            return VerificationResult(
                status=VerificationStatus.DISPUTED,
                reason=f"{len(contra_clusters)} qualified cluster(s) provide contradicting evidence",
                supporting_clusters=sorted(sup_clusters),
                contradicting_clusters=sorted(contra_clusters),
            )

        if not supports:
            return VerificationResult(
                status=VerificationStatus.SINGLE_SOURCE,
                reason="no admitted supporting anchor",
                supporting_clusters=[],
                contradicting_clusters=[],
            )

        # self_reported: every supporting anchor is from a profile controlled
        # by a confirmed subject competitor of the fact.
        if controlled_profiles and all(
            a["profile_id"] in controlled_profiles for a in supports
        ):
            return VerificationResult(
                status=VerificationStatus.SELF_REPORTED,
                reason="all supports come from profiles controlled by confirmed subject",
                supporting_clusters=sorted(sup_clusters),
                contradicting_clusters=sorted(contra_clusters),
            )

        if len(sup_clusters) >= 2:
            return VerificationResult(
                status=VerificationStatus.CORROBORATED,
                reason=f"{len(sup_clusters)} independent qualified clusters",
                supporting_clusters=sorted(sup_clusters),
                contradicting_clusters=sorted(contra_clusters),
            )

        return VerificationResult(
            status=VerificationStatus.SINGLE_SOURCE,
            reason=f"{len(sup_clusters)} qualified cluster supports",
            supporting_clusters=sorted(sup_clusters),
            contradicting_clusters=sorted(contra_clusters),
        )