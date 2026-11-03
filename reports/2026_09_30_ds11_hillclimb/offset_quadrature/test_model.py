import importlib.util
from pathlib import Path
import unittest
import numpy as np
from model import integrate,LOG_C,SIGMA,PRIOR

spec=importlib.util.spec_from_file_location('adaptive_gradient',Path(__file__).resolve().parents[1]/'offset_integral_sensitivity/model.py')
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)


class QuadratureTests(unittest.TestCase):
    def test_adaptive_value_gradient_agreement(self):
        cases=[np.zeros(56),np.array([-900.,-850.,850.,900.]),np.linspace(-250,350,13)+1e6]
        for r in cases:
            offset=float(np.median(r));jac=np.column_stack((np.ones(len(r)),np.linspace(-5,8,len(r))))
            score=len(r)*LOG_C-2.5*np.log1p(((r-offset)/SIGMA)**2/4).sum()-.5*(offset/PRIOR)**2
            expected=oracle.value_gradient(r,jac,offset,score);actual=integrate(r,jac,offset,64)
            self.assertLess(abs(expected['value']-actual['value']),1e-7)
            np.testing.assert_allclose(actual['gradient'],expected['gradient'],atol=1e-7,rtol=1e-7)

    def test_anchor_and_order_convergence(self):
        r=np.array([-800.,-300.,20.,50.,60.,700.]);jac=np.eye(len(r))
        a=integrate(r,jac,0.,32);b=integrate(r,jac,700.,64)
        self.assertLess(abs(a['value']-b['value']),1e-7)
        np.testing.assert_allclose(a['gradient'],b['gradient'],atol=1e-7,rtol=1e-7)
