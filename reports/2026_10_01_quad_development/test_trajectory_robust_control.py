import unittest
import numpy as np
from trajectory_robust_control import robust_fit,density

class RobustTests(unittest.TestCase):
    def test_clean_curve_and_offset(self):
        t=np.arange(20.);y=10+2*t+.3*t*t
        a=robust_fit(t,y,100);b=robust_fit(t,y+50000,100)
        self.assertTrue(a['converged']);np.testing.assert_allclose(a['beta'],b['beta'],atol=1e-8)
    def test_density_symmetry_and_scale(self):
        np.testing.assert_equal(density(np.array([-100.,100.]),100),density(np.array([100.,-100.]),100))
        self.assertAlmostEqual(float(density(0,200)-density(0,100)),-np.log(2))

if __name__=='__main__':unittest.main()
