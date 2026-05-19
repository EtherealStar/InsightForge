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
    "EvidenceRef", "EvidenceOwnerType", "EvidenceType",
    "InsightClaim", "ClaimType", "ClaimStatus",
    "IntelFact", "IntelFactCompetitorLink", "IntelFactProductLink",
    "FactKind", "FactType", "IntelDimension", "FactStatus",
    "AnalysisReport", "ReportClaimRef", "ReportEvidenceRef",
    "ReportQualityIssue", "ReportQualityReview", "ReportReviewStatus",
    "ReportType", "ReportStatus",
]
