"""Independent known-optimum checks for the bounded numerical polisher."""
import unittest
from types import SimpleNamespace
import numpy as np
from strict_polish import polish
from leo.analysis.regional_position_score import WindowLikelihood,zero_sum_basis


class Quadratic:
    size=10
    clock_count=0
    group_scales=np.array([1.])
    group_limits=np.array([2.])
    bank=SimpleNamespace(numbers=np.arange(3),nodes_s=np.array([-30.,330.]))
    prior=SimpleNamespace(radius_km=250.)
    observations=SimpleNamespace(times_s=np.array([0.,300.]))
    basis=zero_sum_basis(3)
    scales=np.r_[1.,1.,200.,2.,200.,2.,200.,np.ones(3)]
    target=np.array([2.,-3.,100.,1.,-200.,-2.,-50.,.2,.1,-.1])

    def evaluate_joint(self,v,n):
        delta=(v-self.target)/self.scales
        value=.5*float(delta@delta)+.5*float((n[0]-3)**2)
        return value,delta/self.scales,np.array([n[0]-3]),WindowLikelihood(
            value,np.full((2,3),1/3),np.zeros(2),np.zeros((2,3)),np.zeros((2,3)))


class PolishTests(unittest.TestCase):
    def check_arm(self,arm):
        model=Quadratic();start=model.target+.01*model.scales
        if arm=='zero-c':start[6]=0.
        before=model.evaluate_joint(start,np.array([1.9]))[0]
        fitted,audit=polish(model,dict(vector=start,nuisance=np.array([1.9])),
            arm=arm,local_center=np.zeros(2),local_radius_km=250.,seconds=5.)
        self.assertTrue(audit['accepted'],audit)
        self.assertLessEqual(audit['stationarity'],.001)
        self.assertLessEqual(fitted['objective'],before+1e-7)
        expected=model.target.copy()
        if arm=='zero-c':expected[6]=0.
        np.testing.assert_allclose(fitted['vector'],expected,atol=1e-6)
        np.testing.assert_allclose(fitted['nuisance'],[2.],atol=1e-7)

    def test_fitted_rf_and_active_nuisance_bound(self):self.check_arm('fitted-c')
    def test_zero_rf_is_fixed_during_polish(self):self.check_arm('zero-c')


if __name__=='__main__':unittest.main()
