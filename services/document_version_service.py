"""文档版本构建与生效状态机。"""
from core.protocols import DocumentDedupStoreProtocol
from models.document_governance import DocumentVersion


class DocumentVersionService:
    def __init__(self, store: DocumentDedupStoreProtocol):
        self.store = store

    def begin(self, document_id: str, content: str, content_hash: str) -> DocumentVersion:
        return self.store.create_version(document_id, content, content_hash)

    def activate(self, version: DocumentVersion) -> DocumentVersion:
        if version.status != "building":
            raise ValueError("only a building document version can be activated")
        return self.store.activate_version(version.document_id, version.id)

    def fail(self, version: DocumentVersion) -> DocumentVersion:
        if version.status != "building":
            raise ValueError("only a building document version can fail")
        return self.store.fail_version(version.document_id, version.id)
