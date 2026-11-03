import unittest
import numpy as np
from characterize_leave_one_out import profiled_information
from plot_leave_out_score_tradeoffs import timing_terms


class InformationTests(unittest.TestCase):
    def test_timing_terms_use_relative_and_common_priors(self):
        record=dict(parameters=[0.]*6+[1.,3.],vector=[0.]*6+[2.,0.,0.])
        individual,common=timing_terms(record)
        np.testing.assert_allclose(individual,[.5,.5])
        self.assertAlmostEqual(common,.02)

    def test_profiles_free_nuisance(self):
        h=np.array([[4.,0.,1.],[0.,3.,0.],[1.,0.,2.]])
        schur,eigen=profiled_information(h,np.array([True,True,True]))
        np.testing.assert_allclose(schur,[[3.5,0.],[0.,3.]])
        np.testing.assert_allclose(eigen,[3.,3.5])

    def test_fixed_nuisance_not_profiled(self):
        h=np.array([[4.,0.,1.],[0.,3.,0.],[1.,0.,2.]])
        schur,eigen=profiled_information(h,np.array([True,True,False]))
        np.testing.assert_allclose(schur,[[4.,0.],[0.,3.]])


if __name__=='__main__':unittest.main()
