from services.document_fingerprint_service import fingerprint, hamming_distance, normalize_content


def test_normalization_removes_markup_and_link_target():
    assert normalize_content("# Hello [world](https://example.com)  ") == "hello world"


def test_fingerprint_is_stable_and_bands_cover_small_distances():
    _, fp, _ = fingerprint("Cursor adds an agent mode for coding teams")
    assert fp.value == fingerprint("Cursor adds an agent mode for coding teams")[1].value
    for bit in range(7):
        changed = fp.value ^ (1 << bit)
        high = tuple((changed >> (16 * i)) & 0xFFFF for i in range(4))
        gray = tuple((changed >> (8 * i)) & 0xFF for i in range(8))
        assert any(a == b for a, b in zip(fp.high_bands, high))
        assert sum(a == b for a, b in zip(fp.gray_bands, gray)) >= 2
        assert hamming_distance(fp.value, changed) == 1
