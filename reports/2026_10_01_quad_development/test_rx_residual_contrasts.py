import unittest
import numpy as np
from rx_residual_contrasts import compare,helmert

class ContrastTests(unittest.TestCase):
    def test_offset_invariance(self):
        a=np.array([2.,3.,7.]);b=np.array([4.,1.,9.]);V=np.eye(3)
        x=compare(a,V,b,V);y=compare(a+1000,V,b-500,V)
        for key in ('common_energy','differential_energy'):self.assertAlmostEqual(x[key],y[key],places=10)
    def test_aligned_opposed(self):
        a=np.arange(4.);V=np.eye(4)
        self.assertAlmostEqual(compare(a,V,a,V)['differential_energy'],0)
        self.assertAlmostEqual(compare(a,V,-a,V)['common_energy'],0)
    def test_covariance_and_orthogonality(self):
        H=helmert(5);np.testing.assert_allclose(H@H.T,np.eye(4),atol=1e-15)
        a=np.arange(5.);V=np.eye(5)
        self.assertAlmostEqual(compare(a,2*V,a,2*V)['common_energy'],compare(a,V,a,V)['common_energy']/2)

if __name__=='__main__':unittest.main()
