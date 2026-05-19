"""竞品分析报告数据模型

定义分析报告实体，替代原 DailyBrief 承载竞品分析输出。
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class ReportType(str, Enum):
    """分析报告类型"""
    OVERVIEW = "overview"              # 竞品概览报告（单竞品全景）
    COMPARISON = "comparison"          # 竞品对比报告（多竞品横向对比）
    BRIEFING = "briefing"              # 市场动态简报
    DEEP_RESEARCH = "deep_research"    # 深度研究报告


class ReportStatus(str, Enum):
    """报告状态"""
    DRAFT = "draft"
    QUALITY_REVIEWING = "quality_reviewing"
    REVISION_REQUIRED = "revision_required"
    WAITING_REVIEW = "waiting_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ReportReviewStatus(str, Enum):
    """报告质量审查状态"""
    NOT_REVIEWED = "not_reviewed"
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_HUMAN = "needs_human"


@dataclass
class SourceRef:
    """溯源引用——每条分析结论的证据来源"""

    url: str = ""                      # 原始来源 URL
    title: str = ""                    # 来源标题
    snippet: str = ""                  # 原文片段
    retrieved_at: str = ""             # 检索时间


@dataclass
class ReportClaimRef:
    """报告与 insight claim 的关系引用"""

    report_id: int
    claim_id: str
    section_key: str = ""
    position: int = 0
    usage_type: str = "supporting"
    created_at: datetime | None = None


@dataclass
class ReportEvidenceRef:
    """报告与 evidence/fact/claim 的引用快照"""

    report_id: int
    evidence_ref_id: str | None = None
    claim_id: str | None = None
    fact_id: str | None = None
    section_key: str = ""
    citation_label: str = ""
    url: str = ""
    title: str = ""
    snippet: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime | None = None


@dataclass
class ReportQualityIssue:
    """结构化质量问题"""

    severity: str
    category: str
    message: str
    section_key: str = ""
    claim_id: str | None = None
    evidence_ref_ids: list[str] = field(default_factory=list)


@dataclass
class ReportQualityReview:
    """报告质量审查结果"""

    report_id: int
    review_type: str
    status: ReportReviewStatus | str
    overall_score: float = 0.0
    dimension_scores: dict = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)
    revision_suggestions: list[dict] = field(default_factory=list)
    model_provider: str = ""
    model_name: str = ""
    prompt_version: str = ""
    reviewed_by: str = "system"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime | None = None


@dataclass
class AnalysisReport:
    """竞品分析报告"""

    title: str
    report_type: ReportType = ReportType.OVERVIEW
    competitor_ids: list[int] = field(default_factory=list)   # 涉及的竞品
    content: str = ""                  # Markdown 报告正文
    source_refs: list[dict] = field(default_factory=list)     # 溯源引用列表
    audit_trail: list[dict] = field(default_factory=list)     # 生成链路审计
    status: ReportStatus = ReportStatus.DRAFT
    review_status: ReportReviewStatus = ReportReviewStatus.NOT_REVIEWED
    quality_score: float | None = None
    quality_summary: str = ""
    generation_context_hash: str = ""
    version: int = 1

    # 关联
    session_id: str | None = None      # 生成此报告的 Agent 会话 ID
    report_filename: str | None = None  # 输出文件名（兼容深度研究）
    approved_by: str | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None

    # 数据库相关
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
