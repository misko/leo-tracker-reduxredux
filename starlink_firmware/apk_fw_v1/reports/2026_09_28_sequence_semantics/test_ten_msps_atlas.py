import numpy as np
from ten_msps_atlas import SEED, classify, codebook, slots


def test_repetition_requires_independent_receiver_and_unused_symbols():
    rng = np.random.default_rng(41)
    words = np.array([[1 if bit == "1" else -1 for bit in w]
                      for w in codebook(list(map(int, SEED)))])
    mapping = slots(np.arange(536, 552), np.arange(2, 34))
    clean = words[17, mapping].astype(complex)
    def noise():
        return .05 * (rng.normal(size=clean.shape) + 1j * rng.normal(size=clean.shape))
    assert classify(clean + noise(), clean + noise(), mapping, words, rng)["label"] == 1
    bad = clean.copy()
    bad[1::2] *= -1
    assert classify(bad, clean, mapping, words, rng)["label"] != 1
    assert classify(clean, words[31, mapping], mapping, words, rng)["label"] != 1


def test_partial_slot_coverage_is_not_accepted_as_complete_pattern():
    rng = np.random.default_rng(42)
    words = np.array([[1 if bit == "1" else -1 for bit in w]
                      for w in codebook(list(map(int, SEED)))])
    mapping = slots(np.array([536]), np.arange(2, 34))
    clean = words[17, mapping].astype(complex)
    result = classify(clean, clean, mapping, words, rng)
    assert not result["all_slots_in_discovery"]
    assert result["label"] != 1
