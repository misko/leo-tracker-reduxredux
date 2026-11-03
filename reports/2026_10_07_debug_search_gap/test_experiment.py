import unittest
import numpy as np
from experiment import shared_seeds, selection, arm_seed

class SharedSeedTests(unittest.TestCase):
    def test_union_copies_preserve_nonzero_coefficient_for_free_arm(self):
        free=np.arange(9,dtype=float); zero=free.copy();zero[6]=0
        seeds=shared_seeds(free,zero)
        np.testing.assert_array_equal(seeds[0][1],free)
        np.testing.assert_array_equal(seeds[1][1],zero)
        seeds[0][1][6]=0
        self.assertEqual(free[6],6)
    def test_selection_ignores_position_truth(self):
        good=dict(selection_score=9,horizontal_error_m=999999)
        self.assertIs(selection([good,dict(selection_score=10,horizontal_error_m=0)]),good)
    def test_zero_projection_changes_only_coefficient(self):
        vector=np.arange(12,dtype=float)
        projected=arm_seed(vector,'zero-c')
        self.assertEqual(projected[6],0)
        np.testing.assert_array_equal(np.delete(projected,6),np.delete(vector,6))
        np.testing.assert_array_equal(arm_seed(vector,'fitted-c'),vector)
        self.assertEqual(vector[6],6)

if __name__=='__main__':unittest.main()
