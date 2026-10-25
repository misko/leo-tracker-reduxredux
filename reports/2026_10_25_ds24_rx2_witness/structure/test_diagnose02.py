import unittest
import numpy as np
from diagnose02 import fit_polynomial, direct_loo


class PolynomialTests(unittest.TestCase):
    def test_LOO_matches_direct_irregular_design(self):
        t=np.r_[np.linspace(0,10,24),18.]
        y=3+t+.12*t*t+np.sin(t)
        for degree in (1,2,3,4):
            fit=fit_polynomial(t,y,degree)
            direct,_=direct_loo(t,y,degree)
            np.testing.assert_allclose(fit['loo'],direct,atol=1e-8,rtol=1e-8)
            self.assertAlmostEqual(float(fit['leverage'].sum()),degree+1)

    def test_quadratic_curvature_and_offset_gauge(self):
        t=np.linspace(1,8,25);y=5+2*t+3*t*t
        a=fit_polynomial(t,y,2);b=fit_polynomial(t,y+454545.,2)
        self.assertAlmostEqual(a['curvature'],6.)
        np.testing.assert_allclose(a['residual'],b['residual'],atol=1e-8)
        np.testing.assert_allclose(a['leverage'],b['leverage'])


if __name__=='__main__':unittest.main()
