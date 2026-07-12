"""来源档案解析和准入规则。"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from core.protocols import SourceProfileStoreProtocol
from models.source_governance import SourceKind, SourceProfile, SourceTier


@dataclass(frozen=True)
class AdmissionResult:
    decision: str
    profile: SourceProfile
    normalized_domain: str


class SourceGovernanceService:
    def __init__(self, store: SourceProfileStoreProtocol):
        self.store = store

    @staticmethod
    def normalize_domain(url_or_domain: str) -> str:
        value = url_or_domain.strip().lower()
        parsed = urlparse(value if "://" in value else f"https://{value}")
        return (parsed.hostname or "").strip(".")

    def resolve_profile(self, url: str) -> SourceProfile | None:
        domain = self.normalize_domain(url)
        profile = self.store.resolve_domain(domain)
        if profile:
            return profile
        labels = domain.split(".")
        for index in range(1, len(labels) - 1):
            parent = self.store.resolve_domain(".".join(labels[index:]))
            if parent and parent.inherit_to_subdomains:
                return parent
        return None

    def admit(self, url: str) -> AdmissionResult:
        domain = self.normalize_domain(url)
        profile = self.resolve_profile(url) or SourceProfile(domain=domain)
        return AdmissionResult(profile.admission, profile, domain)

    def save_profile(self, profile: SourceProfile, *, actor: str, reason: str) -> SourceProfile:
        if not profile.domain or "." not in profile.domain:
            raise ValueError("来源档案必须使用规范化域名")
        return self.store.save_profile(profile, actor=actor, reason=reason)

    def list_profiles(self, *, tier: str | None = None) -> list[SourceProfile]:
        return self.store.list_profiles(tier=tier)

    def list_revisions(self, profile_id: str):
        return self.store.list_revisions(profile_id)
