import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import subset_positions  # Registers research module paths.
from convergence_fisher import roundoff_accept,within_disk,fit


class PrecisionTests(unittest.TestCase):
    def test_optimizer_releases_old_boundary_and_respects_new_disk(self):
        subset_positions.enable_research_model()
        class Quadratic:
            scale=np.ones(9)
            size=8
            bounds=[(None,None)]*9
            base=SimpleNamespace(satellites=np.arange(2),basis=np.array([[1.],[-1.]])/np.sqrt(2),
                                 minimum_shift_s=-20.,maximum_shift_s=20.,deadline=float('inf'),
                                 state=lambda v:dict(parameters=np.r_[v[:6],v[6],v[6]]))
            def evaluate(self,v):
                delta=np.array(v)-np.r_[3.,0.,np.zeros(7)]
                return .5*float(delta@delta),delta
            def curvature(self,v):return np.eye(9)
        with patch('convergence_fisher.coordinate',lambda p:np.asarray(p)),patch('convergence_fisher.coordinate_jacobian',lambda p:np.eye(2)):
            old=fit(Quadratic(),np.zeros(9),[0.,0.],2.,radius_km=2.)
            new=fit(Quadratic(),old['vector'],old['point_km'],2.,radius_km=4.)
        self.assertTrue(old['success']);self.assertTrue(new['success'])
        np.testing.assert_allclose(old['point_km'],[2.,0.],atol=1e-5)
        np.testing.assert_allclose(new['point_km'],[3.,0.],atol=1e-5)

    def test_search_radius_is_a_disk_not_square(self):
        self.assertFalse(within_disk([3.,0.],2.))
        self.assertTrue(within_disk([3.,0.],4.))
        self.assertTrue(within_disk([4.,0.],4.))
        self.assertFalse(within_disk([3.,3.],4.))
        with self.assertRaises(ValueError):within_disk([0.,0.],0.)

    def test_numerically_flat_step_requires_stationarity_improvement(self):
        self.assertTrue(roundoff_accept(40000.,40000.+1e-10,1e-8,.002,.0008))
        self.assertFalse(roundoff_accept(40000.,40000.+1e-10,1e-8,.002,.003))

    def test_cannot_accept_substantial_uphill_or_large_step(self):
        self.assertFalse(roundoff_accept(40000.,40000.+1e-5,1e-8,.002,.0008))
        self.assertFalse(roundoff_accept(40000.,40000.+1e-10,.01,.002,.0008))


if __name__=='__main__':unittest.main()
