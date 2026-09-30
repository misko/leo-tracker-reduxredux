import numpy as np
from decode_windows import KNOWN, recover_window
from tcodes import score_code, slots


def test_fixed_window_and_vectorized_score():
    bins = np.r_[476:488, 496:508]
    mapping = slots(bins, np.arange(34, 66))
    code = np.random.default_rng(44).choice([-1, 1], 60)
    values = code[mapping].astype(complex)
    r = recover_window(values, mapping, 7)
    assert r["accepted"]
    assert np.isclose(r["score"], score_code(values[1::2], mapping[1::2], code))
    rng = np.random.default_rng(7)
    controls = [score_code(values[1::2], mapping[1::2], rng.permutation(code)) for _ in range(99)]
    assert np.isclose(r["shuffled_max"], max(controls))


def test_constant_word_does_not_beat_its_shuffle():
    bins = np.r_[476:488, 496:508]
    mapping = slots(bins, np.arange(34, 66))
    assert not recover_window(np.ones(mapping.shape, complex), mapping, 8)["accepted"]


def test_polarity_ambiguity_is_reported_without_rewriting_observed_bits():
    word = next(w for w, phase in KNOWN.items() if phase == 52)
    inverted = word.translate(str.maketrans("01", "10"))
    code = np.array([1 if bit == "1" else -1 for bit in inverted])
    mapping = slots(np.r_[476:488, 496:508], np.arange(34, 66))
    result = recover_window(code[mapping].astype(complex), mapping, 8)
    assert result["accepted"]
    assert result["word"] == inverted
    assert result["known_phase"] is None
    assert result["complement_known_phase"] == 52
    assert result["nearest_known_hamming_allowing_inversion"] == 0
