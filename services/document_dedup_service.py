"""两阶段去重判定：候选召回与正文相似度复核分离。"""
from __future__ import annotations

from dataclasses import dataclass

from models.document_governance import DedupDecision, DuplicateCandidate, SimHashFingerprint
from services.document_fingerprint_service import (
    fingerprint,
    hamming_distance,
    shingle_similarity,
)


@dataclass(frozen=True)
class DedupAssessment:
    content_hash: str
    fingerprint: SimHashFingerprint
    decision: DedupDecision
    hamming_distance: int | None = None
    shingle_jaccard: float = 0.0
    shingle_containment: float = 0.0
    reason: str = ""


class DocumentDedupService:
    """无 I/O 的去重核心，可在影子模式和正式归簇共用。"""

    def assess(self, content: str, candidates: list[tuple[str, str, SimHashFingerprint, set[str]]]) -> DedupAssessment:
        content_hash, current, shingles = fingerprint(content)
        exact = next((item for item in candidates if item[1] == content_hash), None)
        if exact:
            return DedupAssessment(content_hash, current, DedupDecision.DUPLICATE, 0, 1.0, 1.0, "sha256_exact")
        best: tuple[int, float, float] | None = None
        for _, _, candidate_fp, candidate_shingles in candidates:
            high_hit = any(a == b for a, b in zip(current.high_bands, candidate_fp.high_bands))
            gray_hit = sum(a == b for a, b in zip(current.gray_bands, candidate_fp.gray_bands)) >= 2
            if not (high_hit or gray_hit):
                continue
            distance = hamming_distance(current.value, candidate_fp.value)
            if distance > 6 or len(shingles) < 3 or len(candidate_shingles) < 3:
                continue
            jaccard, containment = shingle_similarity(shingles, candidate_shingles)
            item = (distance, jaccard, containment)
            if best is None or (jaccard, containment, -distance) > (best[1], best[2], -best[0]):
                best = item
        if best and (best[1] >= 0.72 or best[2] >= 0.86):
            return DedupAssessment(content_hash, current, DedupDecision.DUPLICATE, *best, "fingerprint_and_shingle_match")
        if best:
            return DedupAssessment(content_hash, current, DedupDecision.REVIEW_REQUIRED, *best, "gray_candidate_requires_review")
        return DedupAssessment(content_hash, current, DedupDecision.NEW_CLUSTER, reason="no_candidate")

    @staticmethod
    def candidate_from_assessment(left: str, right: str, assessment: DedupAssessment) -> DuplicateCandidate:
        return DuplicateCandidate(left, right, assessment.hamming_distance or 0, assessment.shingle_jaccard, assessment.shingle_containment, assessment.decision, assessment.reason)
