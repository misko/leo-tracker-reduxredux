import unittest
from types import SimpleNamespace
import numpy as np
import experiment

class AuditChecks(unittest.TestCase):
    def objective(self):
        return SimpleNamespace(prior=SimpleNamespace(radius_km=250.),
            bank=SimpleNamespace(numbers=np.array([1,2]),nodes_s=np.array([-30.,30.])),
            observations=SimpleNamespace(times_s=np.array([-5.,5.])),
            basis=np.array([[1.],[-1.]])/np.sqrt(2))

    def test_audit_uses_actual_refinement_radius(self):
        v=np.zeros(9);v[0]=30.
        narrow=experiment.audit(self.objective(),v,np.zeros(9),'fitted-c',[0,0],25.)
        wide=experiment.audit(self.objective(),v,np.zeros(9),'fitted-c',[0,0],50.)
        self.assertFalse(narrow['feasible'])
        self.assertTrue(wide['converged'])

    def test_both_slope_bound_signs_use_constrained_stationarity(self):
        for index in (3,5):
            for sign in (-1.,1.):
                v=np.zeros(9);v[index]=sign*60.
                g=np.zeros(9);g[index]=-sign
                result=experiment.audit(self.objective(),v,g,'fitted-c',[0,0],25.)
                self.assertTrue(result['converged'])
                self.assertEqual(result['slope_active_bounds'],[index])
                v[index]=sign*61.
                self.assertFalse(experiment.audit(self.objective(),v,g,'fitted-c',[0,0],25.)['feasible'])

    def test_zero_c_requires_exact_zero_and_timing_support(self):
        v=np.zeros(9);v[6]=1.
        self.assertFalse(experiment.audit(self.objective(),v,np.zeros(9),'zero-c',[0,0],25.)['feasible'])
        v[6]=0;v[8]=40.
        self.assertFalse(experiment.audit(self.objective(),v,np.zeros(9),'zero-c',[0,0],25.)['feasible'])

if __name__=='__main__':unittest.main(verbosity=2)
