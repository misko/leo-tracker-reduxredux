"""Validate compressed carrier coordinates and noisy repeated-code recovery."""

import unittest

import numpy as np
from recover import BINS, geometry
from tcodes import bit_word, compact_indices, fit_code, score_code, slots


class TcodeTests(unittest.TestCase):
    def test_lower_full_code_is_observable(self):
        mapping = slots(geometry("lower")[0], np.arange(14, 78))
        code, means, counts = fit_code(np.ones(mapping.shape, dtype=complex), mapping)
        self.assertEqual(int(np.sum(counts > 0)), 60)
        self.assertEqual(bit_word(code), "1" * 60)
        self.assertEqual(float(score_code(np.ones(mapping.shape), mapping, code)), 1.0)

    def test_lower_mapping_crosses_period_boundary(self):
        bins = geometry("lower")[0]
        # The lowest retained carrier has compact index 4. The rejected finite
        # vector model instead maps these to 44 and 28 at symbols 4 and 5.
        np.testing.assert_array_equal(slots(bins, np.array([4, 5]))[:, 0], [0, 44])

    def test_upper_mapping_unchanged(self):
        symbols = np.arange(2, 302)
        expected = (compact_indices(BINS)[None, :] - 16 * symbols[:, None]) % 60
        np.testing.assert_array_equal(slots(BINS, symbols), expected)

    def test_compacted_upper_indices_skip_known_pilots(self):
        np.testing.assert_array_equal(compact_indices(BINS), np.arange(976, 1000))

    def test_receiver_independent_noisy_code(self):
        rng = np.random.default_rng(610)
        code = rng.choice([-1, 1], 60)
        mapping = slots(BINS, np.arange(14, 78))
        x = code[mapping] + 0.4 * (
            rng.normal(size=mapping.shape) + 1j * rng.normal(size=mapping.shape)
        )
        y = code[mapping] + 0.5 * (
            rng.normal(size=mapping.shape) + 1j * rng.normal(size=mapping.shape)
        )
        fitted, _, _ = fit_code(x, mapping)
        np.testing.assert_array_equal(fitted, code)
        self.assertGreater(score_code(y, mapping, fitted), 0.7)
        self.assertLess(abs(score_code(y, mapping, np.roll(fitted, 17))), 0.3)

    def test_noise_does_not_validate(self):
        rng = np.random.default_rng(6028)
        mapping = slots(BINS, np.arange(14, 78))
        x = rng.normal(size=mapping.shape) + 1j * rng.normal(size=mapping.shape)
        y = rng.normal(size=mapping.shape) + 1j * rng.normal(size=mapping.shape)
        code, _, _ = fit_code(x, mapping)
        self.assertLess(abs(score_code(y, mapping, code)), 0.1)

    def test_decoder_does_not_impose_even_parity(self):
        mapping = slots(BINS, np.arange(14, 78))
        for ones in (29, 30):
            code = -np.ones(60, dtype=int)
            code[:ones] = 1
            fitted, _, _ = fit_code(code[mapping].astype(complex), mapping)
            np.testing.assert_array_equal(fitted, code)
            self.assertEqual(int(np.sum(fitted > 0)) % 2, ones % 2)


if __name__ == "__main__":
    unittest.main()
