from services.document_dedup_service import DocumentDedupService
from services.document_fingerprint_service import fingerprint
from models.document_governance import DedupDecision


def test_exact_duplicate_is_deduped():
    content = "Windsurf shipped a new editor workflow with team controls."
    digest, fp, shingles = fingerprint(content)
    result = DocumentDedupService().assess(content, [("one", digest, fp, shingles)])
    assert result.decision is DedupDecision.DUPLICATE
    assert result.reason == "sha256_exact"


def test_unrelated_content_creates_new_cluster():
    _, fp, shingles = fingerprint("A quarterly market report discusses hiring trends.")
    result = DocumentDedupService().assess("Cursor released a compiler integration.", [("one", "x", fp, shingles)])
    assert result.decision is DedupDecision.NEW_CLUSTER
