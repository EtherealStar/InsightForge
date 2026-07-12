from infrastructure.document_dedup_store import advisory_lock_keys
from models.document_governance import SimHashFingerprint


def test_advisory_lock_keys_are_stable_sorted_and_algorithm_scoped():
    fingerprint = SimHashFingerprint(42, (9, 1, 9, 3), (8, 7, 6, 5, 4, 3, 2, 1))

    keys = advisory_lock_keys(fingerprint)

    assert keys == sorted(set(keys))
    assert keys == advisory_lock_keys(fingerprint)
    assert keys != advisory_lock_keys(
        SimHashFingerprint(42, (9, 1, 9, 3), fingerprint.gray_bands, "simhash-v2")
    )
