"""Algorithmic fixed-point and prior-coordinate regressions, CPU-only."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import solver
from dsx01_joint_marginal import absolute_phase_linearization

class SolverInvariants(unittest.TestCase):
    def test_absolute_phase_preserves_affine_model_and_prior_at_any_reference(self):
        # A shifted reference must not become a shifted absolute-phase prior.
        a,b,mean,sigma=9.,4.,1.7,2.3
        draws=np.array([-3.,mean,5.])
        for reference in (-8.,0.,13.):
            intercept=absolute_phase_linearization(a+b*reference,b,reference)
            np.testing.assert_allclose(intercept+b*sigma*(mean/sigma+(draws-mean)/sigma),a+b*draws)

    def test_nonlinear_reference_change_is_not_objective_invariant(self):
        theta=2.
        predictions=[absolute_phase_linearization(r*r,2*r,r)+2*r*theta for r in (0.,1.)]
        self.assertNotEqual(*predictions)

    def test_damping_stabilizes_oscillation_and_reports_actual_reference(self):
        class Problem:
            labels=np.array([0]);keep=np.array([True])
            def __init__(self,r):self.reference=np.asarray(r).copy()
            def state(self,x):return {'phases':2-self.reference}
            def calculate(self,x):return {'conditional_residual_hz':np.array([0.])}
        d={'problems':{'fitted_c':(Problem([0.]),np.zeros(2))}}
        optimizer=lambda fun,x,**kw:SimpleNamespace(x=x,success=True,message='mock',nfev=1)
        with patch.object(solver.e,'build',side_effect=lambda d,z,a,r:(Problem(r),d)),patch.object(solver,'objective',return_value=0.),patch.object(solver,'minimize',side_effect=optimizer):
            legacy=solver.fit(d,{},'c0',variant='legacy',max_rounds=3)
            damped=solver.fit(d,{},'c0',max_rounds=3)
        self.assertFalse(legacy['phase_closed']);self.assertTrue(damped['phase_closed'])
        np.testing.assert_array_equal(damped['reference'],[1.])
        np.testing.assert_array_equal(damped['reference'],damped['history'][-1]['reference'])

    def test_clipped_stagnation_is_not_closure(self):
        # The closure uses the raw posterior, even when the bank clips updates.
        updated,check=solver.phase_refresh([31.],[30.],limit_s=30.)
        self.assertEqual(float(updated[0]),30.)
        self.assertGreater(check['phase_change_s'],.01)

if __name__=='__main__':unittest.main()
