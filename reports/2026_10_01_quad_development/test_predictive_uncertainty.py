import unittest
import numpy as np
from trajectory_mixture import fit,predict
from predictive_uncertainty import setup,score,leverage

class PredictionTests(unittest.TestCase):
    def test_constant_design_leverage(self):
        np.testing.assert_allclose(leverage(np.ones((10,1)),np.ones(10),np.ones((3,1))),.1)
    def test_rank_deficiency_rejected(self):
        with self.assertRaises(ValueError):leverage(np.ones((10,2)),np.ones(10),np.ones((2,2)))
    def test_gaussian_parity_and_extrapolation(self):
        t=np.arange(30.);y=t*t+np.where(np.arange(30)%2,1000.,-1000.);m=fit(t,y)
        p=setup(m,t,y,t,'mixture');np.testing.assert_allclose(score(p,y,'gaussian_fixed'),predict(m,t,y),atol=1e-10)
        a=setup(m,t,y,np.array([15.,100.]),'single')
        self.assertGreater(a['leverage'][1,0],a['leverage'][0,0])
    def test_matched_scale_peak(self):
        p=dict(means=np.zeros((1,1)),weights=np.ones(1),sigma=100.,leverage=np.zeros((1,1)),error=None)
        self.assertAlmostEqual(float(score(p,[0.],'t4_matched_fixed')[0]-score(p,[0.],'t4_same_fixed')[0]),.5*np.log(2))

if __name__=='__main__':unittest.main()
