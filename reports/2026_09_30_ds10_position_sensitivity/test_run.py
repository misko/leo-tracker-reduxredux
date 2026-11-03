import unittest
import numpy as np
from run import profile


class ProjectionTests(unittest.TestCase):
    def test_timing_removes_collinear_position(self):
        j=np.array([[-1.,1.,-1.],[0.,-2.,0.],[1.,1.,1.]])
        fixed,free,shift=profile(j,np.ones(3))
        self.assertAlmostEqual(free[0,0],0)
        self.assertEqual(free[1,1],fixed[1,1])
        np.testing.assert_allclose(shift,[-1.,0.])

    def test_zero_timing_retains_information(self):
        j=np.array([[1.,2.,0.],[-1.,-2.,0.]])
        a,b,s=profile(j,np.array([.2,.4]))
        np.testing.assert_allclose(a,b)
        np.testing.assert_allclose(s,[0.,0.])
