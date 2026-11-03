import unittest
import numpy as np
from experiment import penalty
from leo.analysis.regional_position_score import zero_sum_basis

class TimingAuditTests(unittest.TestCase):
    def test_physical_relative_offsets_preserve_norm_and_sum(self):
        coefficients=np.array([.4,-2.,3.])
        relative=zero_sum_basis(4)@coefficients
        self.assertAlmostEqual(float(relative.sum()),0)
        self.assertAlmostEqual(float(relative@relative),float(coefficients@coefficients))

    def test_repricing_preserves_common_penalty(self):
        v=np.r_[np.zeros(7),3.,.3,-.6]
        self.assertAlmostEqual(penalty(v,.15),10.5)
        self.assertAlmostEqual(penalty(v,.5),1.4)
        self.assertAlmostEqual(penalty(v,1.),.725)

    def test_nested_zero_is_same_vector_objective(self):
        # A free-c hypothesis can use the exact zero-c vector without any prior change.
        v=np.r_[np.zeros(7),2.,1.,-1.]
        free=v.copy(); free[6]=0
        self.assertEqual(penalty(v,.15),penalty(free,.15))

if __name__=='__main__': unittest.main()
