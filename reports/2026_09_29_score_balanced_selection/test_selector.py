import unittest

import numpy as np
from score_selector import choose


class Tests(unittest.TestCase):
    def test_balances_opposite_scores_and_batch_independence(self):
        information = np.array([np.eye(2) * 2, np.eye(2) * 2, np.eye(2)])
        gradients = np.array([[10.0, 0.0], [-10.0, 0.0], [0.0, 0.0]])
        for size in (1, 2, 100):
            r = choose(information, information, gradients, 2, size)
            self.assertEqual(r["indices"], [0, 1])
            self.assertEqual(r["examined"], 3)
            self.assertAlmostEqual(r["penalty"], 0.0)

    def test_rejects_nonpositive_curvature(self):
        with self.assertRaises(ValueError):
            choose(np.array([np.eye(2)]), np.array([-np.eye(2)]), np.zeros((1, 2)), 1)


if __name__ == "__main__":
    unittest.main()
