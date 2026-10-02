import unittest
import numpy as np
from quality_residual_stats import ranks,summarize

class StatsTest(unittest.TestCase):
    def test_tied_ranks(self):
        np.testing.assert_equal(ranks([3,1,1,5]),[2,.5,.5,3])
    def test_direction_and_satellite_groups(self):
        rows=[dict(median_margin=x,energy_per_dimension=1-x,norad=g) for x,g in [(.1,1),(.2,1),(.7,2),(.8,2)]]
        s=summarize(rows)
        self.assertAlmostEqual(s['spearman'],-1)
        self.assertEqual(s['within_satellite_concordant'],2)
        self.assertTrue(s['directional_gate'])
    def test_no_comparison_is_not_success(self):
        self.assertFalse(summarize([])['directional_gate'])
        self.assertFalse(summarize([dict(median_margin=.5,energy_per_dimension=1,norad=1)]*2)['directional_gate'])

if __name__=='__main__': unittest.main()
