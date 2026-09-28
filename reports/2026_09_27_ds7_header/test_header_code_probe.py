"""Known convolutional code and independent noise controls for the parity search."""

import unittest

import numpy as np
from header_code_probe import best_check, check_score, pair_windows, walsh


def encoded(seed):
    bits = np.random.default_rng(seed).integers(0, 2, 2000)
    rows = np.lib.stride_tricks.sliding_window_view(bits, 7)
    generators = np.array([[(g >> i) & 1 for i in range(7)] for g in (0o171, 0o133, 0o165)])
    return ((rows @ generators.T) % 2).reshape(1, -1)


class ProbeTests(unittest.TestCase):
    def test_known_code_predicts_independent_bits(self):
        train = pair_windows(encoded(17), 0, (0, 1))
        mask, score = best_check(train)
        self.assertAlmostEqual(abs(score), 1)
        self.assertAlmostEqual(abs(check_score(pair_windows(encoded(18), 0, (0, 1)), mask)), 1)

    def test_noise_selected_check_does_not_generalize(self):
        rng = np.random.default_rng(813)
        a, b = rng.integers(0, 2, (2, 3000, 14))
        mask, _ = best_check(a)
        self.assertLess(abs(check_score(b, mask)), 0.08)

    def test_walsh_matches_explicit_small_transform(self):
        a = np.arange(8)
        expected = [sum(a[x] * (-1) ** ((x & m).bit_count()) for x in range(8)) for m in range(8)]
        np.testing.assert_array_equal(walsh(a), expected)


if __name__ == "__main__":
    unittest.main()
