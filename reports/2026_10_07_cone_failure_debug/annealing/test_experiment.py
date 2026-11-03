import unittest
import numpy as np
from experiment import schedule, choose_basins, inside_seed


class ProtocolTests(unittest.TestCase):
    def test_matched_budgets_and_same_final_model(self):
        for option in ("control", "anneal"):
            stages = schedule(option)
            self.assertEqual(sum(r[1] for r in stages), 40.)
            self.assertEqual(sum(r[2] for r in stages), 800)
            self.assertEqual(stages[-1][0], 125.)

    def test_basin_selection_ignores_truth_error(self):
        pool = [dict(arm="fitted-c", basin="a", selection_score=10, horizontal_error_m=1),
                dict(arm="fitted-c", basin="b", selection_score=9, horizontal_error_m=1000),
                dict(arm="zero-c", basin="c", selection_score=8, horizontal_error_m=1000)]
        self.assertEqual(choose_basins(pool), ["b", "c"])

    def test_only_roundoff_spatial_repair(self):
        v = np.array([2.+1e-12, 0., 33., 4., 5., 6., 0., 8.])
        repaired = inside_seed(v, np.zeros(2), 2., 3.)
        self.assertLess(np.linalg.norm(repaired[:2]), 2.)
        np.testing.assert_array_equal(repaired[2:], v[2:])
        with self.assertRaises(ValueError):
            inside_seed(np.r_[2.1, np.zeros(7)], np.zeros(2), 2., 3.)


if __name__ == "__main__":
    unittest.main()
