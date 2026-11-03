import unittest
import numpy as np
from calibration_audit import probability_bins, summarize_groups

class CalibrationAuditTests(unittest.TestCase):
    def test_edges_and_invalid_probabilities(self):
        self.assertEqual(probability_bins(np.array([0.,.1,.999,1.])),[0,1,9,9])
        for invalid in (-.1,1.1,float('nan')):
            with self.assertRaises(ValueError):probability_bins(np.array([invalid]))

    def test_weighted_group_rates_preserve_all_rows(self):
        result = summarize_groups(['a','a','b'],np.array([.2,.8,.4]),np.array([0,1,1]),np.array([.5,.5,1.]))
        self.assertEqual(sum(r['candidates'] for r in result),3)
        self.assertAlmostEqual(result[0]['predicted_retention'],.5)
        self.assertAlmostEqual(result[0]['observed_minus_predicted'],0)
        self.assertAlmostEqual(result[1]['observed_minus_predicted'],.6)
