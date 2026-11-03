import unittest
import numpy as np
from plot import sky,boundary
from test_mark import frame

class PlotTests(unittest.TestCase):
    def test_disk_is_zenith_center_and_horizon_rim(self):
        np.testing.assert_allclose(sky(np.array([[0,0,1.],[1.,0,0],[0,1.,0]])),[[0,0],[1,0],[0,1]],atol=1e-12)
    def test_boundary_is_normalized(self):
        theta=np.array([np.radians(30),np.radians(20),np.log(.3),.2,.1]);edge=boundary(theta,frame(270,70),0)
        np.testing.assert_allclose(np.linalg.norm(edge,axis=1),1.,atol=1e-12)

if __name__=='__main__':unittest.main()
