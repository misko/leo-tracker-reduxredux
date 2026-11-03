import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from timing_bound_comparison import feasible_start
from subset_positions import enable_research_model
enable_research_model()
from timing_model import zero_sum_basis
from convergence_fisher import fit


class TimingBoundTests(unittest.TestCase):
    def test_optimizer_enforces_total_timing_limit(self):
        class Quadratic:
            scale=np.ones(9)
            size=8
            bounds=[(None,None)]*9
            base=SimpleNamespace(satellites=np.arange(2),basis=zero_sum_basis(2),
                minimum_shift_s=-10.,maximum_shift_s=10.,deadline=float('inf'),
                state=lambda v:dict(parameters=np.r_[v[:6],v[6]+zero_sum_basis(2)@v[7:8]]))
            def evaluate(self,v):
                target=np.zeros(9);target[7]=12*np.sqrt(2)
                d=np.asarray(v)-target
                return .5*float(d@d),d
            def curvature(self,v):return np.eye(9)
        with patch('convergence_fisher.coordinate',lambda p:np.asarray(p)),patch('convergence_fisher.coordinate_jacobian',lambda p:np.eye(2)):
            result=fit(Quadratic(),np.zeros(9),[0.,0.],2.,radius_km=4.)
        self.assertTrue(result['success'])
        np.testing.assert_allclose(result['parameters'][6:],[10.-1e-6,-10.+1e-6],atol=1e-5)

    def test_clips_total_not_relative_and_preserves_other_nuisance(self):
        obj=SimpleNamespace(base=SimpleNamespace(basis=zero_sum_basis(4)))
        p=np.r_[np.arange(6),[-19.,-3.,8.,17.]]
        r=dict(parameters=p,coefficient=123.)
        v=feasible_start(obj,r,10.,'fitted-c')
        total=v[6]+obj.base.basis@v[7:-1]
        np.testing.assert_allclose(total,[-10.+2e-6,-3.,8.,10.-2e-6],atol=1e-10)
        np.testing.assert_array_equal(v[:6],p[:6]);self.assertEqual(v[-1],123.)
        self.assertLessEqual(abs(v[6]),10.);self.assertAlmostEqual(sum(total-v[6]),0.)

    def test_feasible_existing_shifts_unchanged_and_c_zero_enforced(self):
        obj=SimpleNamespace(base=SimpleNamespace(basis=zero_sum_basis(3)))
        r=dict(parameters=np.r_[np.zeros(6),[-1.,4.,6.]],coefficient=123.)
        for limit in [10.,20.]:
            v=feasible_start(obj,r,limit,'zero-c')
            np.testing.assert_allclose(v[6]+obj.base.basis@v[7:-1],[-1.,4.,6.])
            self.assertEqual(v[-1],0.)


if __name__=='__main__':unittest.main()
