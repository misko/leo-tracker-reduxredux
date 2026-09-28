"""Numerical checks for geographic Doppler matching and held-out scoring."""

import unittest

import numpy as np
from annotate import RF, C, geometry, predict, scores


class AnnotationTests(unittest.TestCase):
    def test_cardinal_geometry(self):
        rec, basis = geometry(37.849056280893684, -122.48575489722863)
        for heading, direction in [(90, basis[0]), (270, -basis[0]), (0, basis[1])]:
            pos = rec + direction * 1000 + basis[2] * 1000
            _, az, el, distance = predict(pos, np.zeros(3), rec, basis)
            self.assertAlmostEqual((float(az) - heading + 180) % 360 - 180, 0)
            self.assertAlmostEqual(float(el), 45)
            self.assertAlmostEqual(float(distance), np.sqrt(2) * 1000)

    def test_receding_satellite_has_negative_doppler(self):
        rec, basis = geometry(0, 0)
        doppler, _, _, _ = predict(rec + basis[2] * 550, basis[2] * 2, rec, basis)
        self.assertAlmostEqual(float(doppler), -RF / C * 2)

    def test_constant_offset_and_heldout_separation(self):
        t = np.arange(30, dtype=float)
        predicted = np.array([t * t, t * t + 3 * t])
        mask = np.arange(30) % 3 != 0
        measured = predicted[0] + 12345
        train, held, offset, _ = scores(measured, predicted, mask)
        self.assertAlmostEqual(offset[0], 12345)
        self.assertAlmostEqual(train[0], 0)
        self.assertAlmostEqual(held[0], 0)
        changed = measured.copy()
        changed[~mask] += 500
        _, other, unchanged, _ = scores(changed, predicted, mask)
        np.testing.assert_array_equal(offset, unchanged)
        self.assertAlmostEqual(other[0], 500)
        self.assertGreater(train[1], 20)


if __name__ == "__main__":
    unittest.main()
