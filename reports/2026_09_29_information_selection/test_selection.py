import unittest

import numpy as np
from selection import greedy, profile


class SelectionTests(unittest.TestCase):
    def test_complementary_directions_and_ties(self):
        matrices = [np.diag([10.0, 1.0]), np.diag([10.0, 1.0]), np.diag([1.0, 10.0])]
        self.assertEqual(greedy(matrices, 2)["indices"], [0, 2])

    def test_timing_confounded_direction_is_removed(self):
        design = np.array([[1.0, 0.0, 1.0], [0.0, 2.0, 0.0], [-1.0, 0.0, -1.0]])
        np.testing.assert_allclose(profile(design.T @ design), np.diag([0.0, 4.0]))


if __name__ == "__main__":
    unittest.main()
