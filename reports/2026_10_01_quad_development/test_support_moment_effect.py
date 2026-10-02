import unittest
import numpy as np
from support_moment_effect import correction

class MomentTest(unittest.TestCase):
    def test_cubic_exact(self):
        offsets=np.array([-.03,-.01,.04]);m=[1.,0.,np.mean(offsets**2)/2,np.mean(offsets**3)/6]
        f=lambda t:2+3*t+4*t*t+5*t**3
        for h in (.02,.04):
            got=correction([f(i*h) for i in (-2,-1,0,1,2)],h,m)
            self.assertAlmostEqual(got,np.mean(f(offsets))-f(0),places=12)
    def test_constant_linear_zero(self):
        self.assertAlmostEqual(correction([1,2,3,4,5],1,[1,0,.1,.01]),0)
    def test_offcenter_rejected(self):
        with self.assertRaises(ValueError):correction([0]*5,.02,[1,.1,.01,0])

if __name__=='__main__':unittest.main()
