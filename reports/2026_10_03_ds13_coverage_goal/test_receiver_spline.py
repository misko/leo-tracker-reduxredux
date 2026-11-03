import unittest
import numpy as np
from receiver_spline import fit,predict,NULL,NODES


class ReceiverSplineTests(unittest.TestCase):
    def test_no_constant_or_linear_correction(self):
        t=np.linspace(0,300,100);b=fit(t,np.zeros(100,int),30*np.sin(t/60))
        knots=NULL@b[0]
        self.assertAlmostEqual(knots.sum(),0.,places=10)
        self.assertAlmostEqual(knots@(NODES-150),0.,places=8)

    def test_receiver_isolation_and_no_support_zero_prior(self):
        t=np.linspace(0,300,100);b=fit(t,np.zeros(100,int),30*np.sin(t/60))
        np.testing.assert_array_equal(predict(b,t,np.ones(100,int)),np.zeros(100))
        self.assertGreater(np.max(abs(predict(b,t,np.zeros(100,int)))),0)

    def test_zero_residual_and_no_extrapolation(self):
        np.testing.assert_array_equal(fit(np.arange(10.),np.zeros(10,int),np.zeros(10)),np.zeros((2,9)))
        with self.assertRaises(ValueError):predict(np.zeros((2,9)),np.array([301.]),np.array([0]))


if __name__=='__main__':unittest.main()
