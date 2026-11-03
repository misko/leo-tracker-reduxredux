"""Tests for row identity, own-arm selection and independent KKT diagnosis."""
import unittest
import numpy as np
from experiment import subset,choose,options
from baseline import correction_off_seed
from leo.contracts.regional_position import PositionObservations
from leo.analysis.regional_position_score import zero_sum_basis

class DiagnosticTests(unittest.TestCase):
    def test_correction_removal_preserves_affine_prediction_and_arm(self):
        design=np.array([[1.,-1.,0.,0.,.2],[1.,1.,0.,0.,-.2],[0.,0.,1.,-1.,.1],[0.,0.,1.,1.,-.1]])
        vector=np.zeros(9);vector[6]=0.;correction=design[:,:4]@np.array([3.,2.,5.,4.])
        seed,affine=correction_off_seed(vector,design,correction)
        np.testing.assert_allclose(design@seed[2:7],design@vector[2:7]+correction)
        self.assertEqual(seed[6],0.)
    def test_subset_preserves_every_field_and_identity(self):
        obs=PositionObservations(('a','b','c'),np.array([0.,1.,2.]),np.array([3.,4.,5.]),np.array([1e9,2e9,3e9]),np.array([0,1,0]),np.array([4,5,6]),np.array([7.,8.,9.]))
        got=subset(obs,np.array([True,False,True]));self.assertEqual(got.window_ids,('a','c'))
        for name in ('times_s','measured_hz','rf_hz','receiver','channel','margin'):np.testing.assert_array_equal(getattr(got,name),getattr(obs,name)[[0,2]])
    def test_selection_uses_own_arm_score_without_truth(self):
        rows=[dict(arm='fitted-c',feasible=True,selection_score=5,basin='b',origin='a',error_m=9000),dict(arm='fitted-c',feasible=True,selection_score=6,basin='b',origin='a',error_m=0),dict(arm='zero-c',feasible=True,selection_score=1,basin='b',origin='a',error_m=1)]
        self.assertIs(choose(rows,'fitted-c'),rows[0])
    def test_independent_audit_detects_interior_gradient(self):
        basis=zero_sum_basis(2);v=np.zeros(9);g=np.zeros(9);g[0]=.1
        result=options.audit(v,g,basis,'fitted-c',250,np.zeros(2),12.5,-20,20)
        self.assertTrue(result['feasible']);self.assertFalse(result['converged']);self.assertAlmostEqual(result['stationarity'],.1)

if __name__=='__main__':unittest.main()
