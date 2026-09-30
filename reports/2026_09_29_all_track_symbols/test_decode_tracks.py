import numpy as np
from decode_tracks import word_candidate
from tcodes import slots


def test_fixed_window_recovers_arbitrary_word_without_codebook_forcing():
    bins = np.r_[476:488, 496:508]
    rng = np.random.default_rng(717)
    code = rng.choice([-1, 1], 60)
    z = code[slots(bins, np.arange(2, 302))].astype(complex)
    result = word_candidate(z, bins, 0)
    assert result["accepted"]
    assert result["word"] == "".join("1" if c > 0 else "0" for c in code)
    assert result["known_phase"] is None


def test_missing_slots_cannot_be_complete_word():
    bins = np.array([496])
    z = np.ones((300, 1), complex)
    result = word_candidate(z, bins, 0)
    assert not result["full_coverage"]
    assert not result["accepted"]
    assert "?" in result["word"]


def test_odd_symbol_disagreement_rejects():
    bins = np.r_[476:488, 496:508]
    rng = np.random.default_rng(717)
    code = rng.choice([-1, 1], 60)
    z = code[slots(bins, np.arange(2, 302))].astype(complex)
    z[1::2] *= -1
    assert not word_candidate(z, bins, 0)["accepted"]
