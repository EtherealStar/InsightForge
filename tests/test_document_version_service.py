from models.document_governance import DocumentVersion
from services.document_version_service import DocumentVersionService


class VersionStore:
    def __init__(self):
        self.versions = []
        self.active = None

    def create_version(self, document_id, content, content_hash):
        current = max((item.version for item in self.versions), default=0)
        if self.active:
            current = max(current, self.active.version)
        version = DocumentVersion(document_id, current + 1, content, content_hash)
        self.versions.append(version)
        return version

    def get_active_version(self, document_id):
        return self.active

    def activate_version(self, document_id, version_id):
        version = next(item for item in self.versions if item.id == version_id)
        version.status = "active"
        self.active = version
        return version

    def fail_version(self, document_id, version_id):
        version = next(item for item in self.versions if item.id == version_id)
        version.status = "failed"
        return version


def test_building_version_does_not_replace_active_until_activation():
    store = VersionStore()
    old = DocumentVersion("cluster-1", 1, "old", "old-hash", status="active")
    store.active = old
    service = DocumentVersionService(store)

    building = service.begin("cluster-1", "new", "new-hash")

    assert building.status == "building"
    assert building.version == 2
    assert store.get_active_version("cluster-1") == old
    assert service.activate(building).id == building.id


def test_failed_build_keeps_previous_active_version():
    store = VersionStore()
    old = DocumentVersion("cluster-1", 1, "old", "old-hash", status="active")
    store.active = old
    service = DocumentVersionService(store)

    failed = service.fail(service.begin("cluster-1", "new", "new-hash"))

    assert failed.status == "failed"
    assert store.get_active_version("cluster-1") == old
