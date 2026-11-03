import unittest
import numpy as np
from run import interpolate, objective


class CalibrationTests(unittest.TestCase):
    def test_prediction_uses_training_only(self):
        t=np.array([0.,1.,2.]); y=3*t+5; mask=np.array([True,False,True])
        before=interpolate(t,y,mask,1)[0]
        self.assertEqual(before[0],8)
        y[1]=999
        self.assertEqual(interpolate(t,y,mask,1)[0],before)

    def test_support(self):
        t=np.array([0.,1.,3.]); mask=np.array([True,False,True])
        self.assertEqual(interpolate(t,t,mask,1)[1],'gap_over_2s')
        self.assertEqual(interpolate(t,t,mask,0)[1],'unbracketed')

    def test_gradient(self):
        x=np.array([[1.,-.5],[1.,-2.],[1.,-.8]])
        e=np.array([50.,-20.,300.]); w=np.ones(3)/3; theta=np.array([4.,-.2])
        _,g=objective(theta,x,e,w)
        numeric=[]
        for i in range(2):
            d=np.eye(2)[i]*1e-5
            numeric.append((objective(theta+d,x,e,w)[0]-objective(theta-d,x,e,w)[0])/2e-5)
        np.testing.assert_allclose(g,numeric,atol=1e-8)
