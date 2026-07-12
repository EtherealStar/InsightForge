from models.source_governance import SourceKind, SourceProfile, SourceTier
from services.source_governance_service import SourceGovernanceService


class FakeSourceStore:
    def __init__(self, profiles=()):
        self.profiles = {item.domain: item for item in profiles}

    def resolve_domain(self, domain):
        return self.profiles.get(domain)

    def list_profiles(self, *, tier=None):
        return [item for item in self.profiles.values() if tier is None or item.tier.value == tier]


def test_subdomain_inherits_explicit_parent_profile_and_revision():
    parent = SourceProfile(
        domain="example.com",
        tier=SourceTier.A,
        source_kind=SourceKind.NEWS,
        inherit_to_subdomains=True,
        revision_id="revision-1",
    )
    service = SourceGovernanceService(FakeSourceStore([parent]))

    result = service.admit("https://news.example.com/article")

    assert result.decision == "admit"
    assert result.profile.revision_id == "revision-1"


def test_unknown_source_is_pending_review():
    result = SourceGovernanceService(FakeSourceStore()).admit("https://unknown.example/article")

    assert result.decision == "pending_review"
    assert result.profile.tier == SourceTier.UNKNOWN
