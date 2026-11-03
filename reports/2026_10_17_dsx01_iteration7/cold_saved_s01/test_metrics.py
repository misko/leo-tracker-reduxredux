import unittest
import numpy as np
from metrics import compare, zero_c


class ReplayMetricsTests(unittest.TestCase):
    def test_new_lost_intersection_and_same_identity_are_distinct(self):
        original = dict(associated=np.array([True, True, False, True]),
            satellite_number=np.array([10, 20, 30, 40]), residual_hz=np.array([3., 4., 99., 12.]))
        saved = dict(associated=np.array([True, False, True, True]),
            satellite_number=np.array([10, 20, 30, 99]), residual_hz=np.array([4., 99., 6., 5.]))
        r = compare(original, saved, np.ones(4, bool))
        self.assertEqual((r['new'], r['lost'], r['retained']), (1, 1, 2))
        self.assertEqual((r['retained_identity_changes'], r['retained_same_identity']), (1, 1))
        self.assertAlmostEqual(r['intersection_original_rms_hz'], np.sqrt((3**2+12**2)/2))
        self.assertEqual(r['same_identity_original_rms_hz'], 3.)
        self.assertEqual(r['same_identity_saved_rms_hz'], 4.)
        subset = compare(original, saved, np.array([False, True, True, False]))
        self.assertEqual(subset['denominator'], 2)
        self.assertEqual((subset['new'], subset['lost']), (1, 1))

    def test_zeroing_is_deterministic_and_preserves_both_frozen_endpoints(self):
        v, n = np.arange(12.), np.arange(4.)
        a, b = zero_c(v, n)
        self.assertEqual(a[6], 0.)
        np.testing.assert_array_equal(v, np.arange(12.))
        np.testing.assert_array_equal(n, np.arange(4.))
        np.testing.assert_array_equal(np.delete(a, 6), np.delete(v, 6))
        b[0] = 99.
        self.assertEqual(n[0], 0.)


if __name__ == '__main__':
    unittest.main()
