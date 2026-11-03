import unittest
from harness import distance, percentile, qualify


class HarnessTests(unittest.TestCase):
    def test_fixed_dimension_is_not_boundary_but_free_dimension_is(self):
        bounds = [(-12, 12), (-12, 12), (0, 0)]
        self.assertTrue(qualify(True, [1, 1, 0], [0, 0, 0], 0, bounds)[0])
        self.assertFalse(qualify(True, [12, 1, 0], [0, 0, 0], 0, bounds)[0])

    def test_failure_or_nonfinite_cannot_qualify(self):
        bounds = [(-12, 12), (-12, 12), (-5, 5)]
        self.assertFalse(qualify(False, [0, 0, 0], [0, 0, 0], 0, bounds)[0])
        self.assertFalse(qualify(True, [0, 0, 0], [float('nan'), 0, 0], 0, bounds)[0])

    def test_metric_conventions(self):
        self.assertEqual(distance((37.849056280893684, -122.48575489722863)), 0)
        self.assertEqual(percentile([0, 100], .9), 90)


if __name__ == '__main__':
    unittest.main()
