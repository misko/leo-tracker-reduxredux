import unittest
import numpy as np
from model import value_gradient,LOG_C,SIGMA,PRIOR


class DerivativeTests(unittest.TestCase):
    def test_expected_score_gradient_against_finite_difference(self):
        r=np.array([-180.,-90.,20.,75.,360.]);jac=np.array([[1.,2.],[2.,-1.],[3.,0.],[-1.,4.],[5.,-3.]])
        def evaluate(residual):
            score=len(r)*LOG_C-2.5*np.log1p((residual/SIGMA)**2/4).sum()
            return value_gradient(residual,jac,0.,score)
        result=evaluate(r);step=1e-3
        for axis in range(2):
            finite=(evaluate(r-step*jac[:,axis])['value']-evaluate(r+step*jac[:,axis])['value'])/(2*step)
            self.assertAlmostEqual(finite,result['gradient'][axis],places=7)

    def test_constant_prediction_direction_has_only_prior_sensitivity(self):
        r=np.zeros(8);result=value_gradient(r,np.ones((8,1)),0.,8*LOG_C)
        self.assertLess(abs(result['gradient'][0]),1e-12)
