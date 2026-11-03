"""Hardware-free tests for descriptive decomposition accounting."""
import unittest
import numpy as np
from diagnose import partition, projection_fraction


class DiagnosisTests(unittest.TestCase):
    def test_missing_ids_and_present_candidate_losses_remain_separate(self):
        p = partition(np.array([True, True, True, False]), np.array([1, 2, 3, 4]),
            np.array([False, False, True, True]), [1, 3], np.ones(4, bool))
        self.assertEqual(p['original_assigned'], 3)
        self.assertEqual(p['original_winner_present'], 2)
        self.assertEqual(p['original_winner_absent'], 1)
        self.assertEqual(p['lost_original_winner_present'], 1)
        self.assertEqual(p['lost_original_winner_absent'], 1)

    def test_mask_partition_never_double_counts(self):
        assigned = np.array([True, True, False, True])
        kwargs = (assigned, np.array([1, 2, 3, 4]), ~assigned, [1, 4])
        early = np.array([True, True, False, False])
        a, b, allrows = (partition(*kwargs, m) for m in [early, ~early, np.ones(4, bool)])
        for key in a:
            self.assertEqual(a[key]+b[key], allrows[key])

    def test_linear_dependence_is_not_a_correlation_after_offset_removal(self):
        x = np.arange(10.)
        design = np.column_stack([np.ones(10), x])
        self.assertAlmostEqual(projection_fraction(4.+2*x, design), 1.)
        self.assertIsNone(projection_fraction(np.zeros(10), design))


if __name__ == '__main__':
    unittest.main()
