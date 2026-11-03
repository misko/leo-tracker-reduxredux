import unittest
import numpy as np


class ResponseTest(unittest.TestCase):
    def test_profiled_downweight_response_matches_full_quadratic(self):
        a=np.array([[5.,.2,.8],[.2,4.,-.4],[.8,-.4,2.]])
        b=np.array([[3.,.1,-.3],[.1,6.,.6],[-.3,.6,3.]])
        h=np.zeros((4,4))
        h[:2,:2]=a[:2,:2]+b[:2,:2]
        h[:2,2]=a[:2,2];h[2,:2]=a[2,:2];h[2,2]=a[2,2]
        h[:2,3]=b[:2,2];h[3,:2]=b[2,:2];h[3,3]=b[2,2]
        g=np.array([2.,-1.,.7,0.])
        profiled=a[:2,:2]-np.outer(a[:2,2],a[2,:2])/a[2,2]
        profiled+=b[:2,:2]-np.outer(b[:2,2],b[2,:2])/b[2,2]
        contribution=g[:2]-a[:2,2]/a[2,2]*g[2]
        expected=-np.linalg.solve(profiled,contribution)
        np.testing.assert_allclose(expected,-np.linalg.solve(h,g)[:2],atol=1e-12)
        track_h=np.zeros((4,4));track_h[:3,:3]=.1*a
        epsilon=1e-6
        perturbed=-epsilon*np.linalg.solve(h-epsilon*track_h,g)
        np.testing.assert_allclose(perturbed[:2]/epsilon,expected,rtol=1e-6,atol=1e-9)


if __name__=='__main__':
    unittest.main()
