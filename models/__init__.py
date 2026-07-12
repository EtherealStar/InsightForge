"""领域模型层"""
from models.article import Article, ArticleDTO, ArticleEntity, ArticleMapper, Language, ArticleStatus, IntelType
from models.search import SearchQuery, SearchResult
from models.brief import DailyBrief
from models.competitor import Competitor, CompetitorProduct
from models.auth import ActorRole, ApiKeyRecord, ApiKeyStatus
from models.config_audit import ConfigAuditLog
from models.document import (
    ChildChunkPoint,
    ChildChunkSearchResult,
    ParentDocumentChunk,
    SourceDocument,
)
from models.evidence import EvidenceRef, EvidenceOwnerType, EvidenceType
from models.insight import InsightClaim, ClaimType, ClaimStatus
from models.intel import (
    IntelFact,
    IntelFactCompetitorLink,
    IntelFactProductLink,
    FactKind,
    FactType,
    IntelDimension,
    FactStatus,
)
# 目标 contract: Milestone 2 引入，Milestone 7 后取代旧 dataclass。
from models.target_intel import (
    FactEntityRole,
    FactEvidenceLink,
    FactLifecycleStatus,
    FactResolution,
    FactResolutionOutcome,
    IntelFactCandidate,
    LinkReviewStatus,
    TimePrecision,
)
from models.target_intel import VerificationStatus as TargetVerificationStatus
from models.target_evidence import CharRangeLocator, EvidenceReference, EvidenceStance
from models.target_insight import ClaimFactLink, ClaimMaturity, ClaimStance
from models.report import (
    AnalysisReport,
    ReportClaimRef,
    ReportEvidenceRef,
    ReportQualityIssue,
    ReportQualityReview,
    ReportReviewStatus,
    ReportType,
    ReportStatus,
)

__all__ = [
    "Article", "Language", "ArticleStatus", "IntelType",
    "ArticleDTO", "ArticleEntity", "ArticleMapper",
    "SearchQuery", "SearchResult",
    "DailyBrief",
    "Competitor", "CompetitorProduct",
    "ActorRole", "ApiKeyRecord", "ApiKeyStatus", "ConfigAuditLog",
    "SourceDocument", "ParentDocumentChunk",
    "ChildChunkPoint", "ChildChunkSearchResult",
    # Legacy evidence (kept for Service / Store / API compat until Milestone 7).
    "EvidenceRef", "EvidenceOwnerType", "EvidenceType",
    # Target evidence (Milestone 2+).
    "CharRangeLocator", "EvidenceReference", "EvidenceStance",
    # Legacy claim (kept for Service / Store / API compat until Milestone 7).
    "InsightClaim", "ClaimType", "ClaimStatus",
    # Target claim (Milestone 2+).
    "ClaimFactLink", "ClaimMaturity", "ClaimStance",
    # Legacy Intel Fact (kept for compat).
    "IntelFact", "IntelFactCompetitorLink", "IntelFactProductLink",
    "FactKind", "FactType", "IntelDimension", "FactStatus",
    # Target Intel Fact (Milestone 2+).
    "FactEntityRole", "FactEvidenceLink", "FactLifecycleStatus",
    "FactResolution", "FactResolutionOutcome", "IntelFactCandidate",
    "LinkReviewStatus", "TimePrecision", "TargetVerificationStatus",
    "AnalysisReport", "ReportClaimRef", "ReportEvidenceRef",
    "ReportQualityIssue", "ReportQualityReview", "ReportReviewStatus",
    "ReportType", "ReportStatus",
]