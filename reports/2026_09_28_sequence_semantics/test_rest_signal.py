import numpy as np
from phase_model import codebook, derive_seed
from rest_signal import SEED, relative_bits, split_word, stability


def test_relative_bits_cancel_symbol_polarity_and_preserve_gaps():
    z = np.array([[1, -1, 1, 1], [-1, -1, 1, -1]], complex)
    bins = np.array([2, 3, 6, 7])
    bits, pairs = relative_bits(z, bins)
    assert pairs.tolist() == [0, 2]
    assert bits.tolist() == [[-1, 1], [1, -1]]
    np.testing.assert_array_equal(relative_bits(z * np.array([[-1], [1]]), bins)[0], bits)


def test_stability_does_not_select_on_evaluation_or_accept_missing_discovery():
    bits = np.ones((7, 2), int)
    valid = np.ones_like(bits, bool)
    valid[1, 1] = False
    bits[3:, 0] = -1
    assert stability(bits, valid) == {
        "selected_positions": 1,
        "evaluation_decisions": 4,
        "evaluation_correct": 0,
    }


def test_split_band_recovers_word_without_codebook_fitting_and_retains_polarity():
    bins = np.array(
        [k for k in range(2, 1022) if k not in range(488, 496) and k not in range(528, 536)]
    )
    order = np.argsort(np.fft.fftfreq(1024)[bins])
    compact = np.argsort(order)
    seed = np.array([int(x) for x in SEED])
    book = codebook(seed)
    assert codebook(derive_seed(book[1])) == book
    assert codebook(1 - seed) == book
    for k, polarity in [(0, 1), (31, -1), (52, 1)]:
        word = np.array([1 if x == "1" else -1 for x in book[k]])
        z = polarity * word[(compact - 16 * 301) % 60].astype(complex)
        fit = split_word(z, bins, 301)
        assert fit["exact_band_agreement"]
        assert fit["generator_candidates"] == [dict(phase_index=k, polarity=polarity)]
    z = np.random.default_rng(35).choice([-1, 1], len(bins)).astype(complex)
    assert split_word(z, bins, 301)["generator_candidates"] == []
