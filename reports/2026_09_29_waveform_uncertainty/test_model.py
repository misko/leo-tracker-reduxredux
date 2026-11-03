import unittest

import numpy as np
from model import jackknife_sigma, line_predict
from prepare import select_visits


class ModelTests(unittest.TestCase):
    def test_exact_line_and_offset_invariance(self):
        y, slope = line_predict([0, 1, 2, 3], [10, 8, 6, 4], [4, 5])
        np.testing.assert_allclose(y, [2, 0], atol=1e-12)
        self.assertAlmostEqual(slope, -2)
        z, _ = line_predict([0, 1, 2, 3], [1010, 1008, 1006, 1004], [4, 5])
        np.testing.assert_allclose(z - 1000, y, atol=1e-12)

    def test_uncertain_outlier_has_less_influence(self):
        ordinary, _ = line_predict([0, 1, 2, 3], [0, 1, 2, 100], [4])
        weighted, _ = line_predict([0, 1, 2, 3], [0, 1, 2, 100], [4], [25, 25, 25, 1000])
        self.assertLess(abs(weighted[0] - 4), abs(ordinary[0] - 4))

    def test_jackknife_offset_invariance(self):
        self.assertEqual(jackknife_sigma([12] * 8), 0)
        self.assertAlmostEqual(jackknife_sigma(np.arange(8)), jackknife_sigma(np.arange(8) + 999))

    def test_short_held_coverage_is_retained(self):
        track = dict(
            times_s=[0, 0.5, 1, 2, 3, 4], training_mask=[True, True, True, True, True, False]
        )
        self.assertEqual(select_visits(track), ([0, 2, 3, 4], [5]))


if __name__ == "__main__":
    unittest.main()
