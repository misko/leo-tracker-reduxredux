import unittest
import numpy as np
from inject import shifted_track


class InjectionTests(unittest.TestCase):
    def test_identity_residual_and_input_preservation(self):
        y=np.array([3.,7.,10.]);track=dict(y=y,mask=np.array([True,False,True]))
        before=np.array([[1.,2.,3.],[4.,5.,6.]])
        after=before+np.array([[2.,4.,6.],[-1.,2.,1.]])
        result=shifted_track(track,before,after,1)
        np.testing.assert_allclose(result['y']-after[1],y-before[1])
        np.testing.assert_array_equal(shifted_track(track,before,before,1)['y'],y)
        np.testing.assert_array_equal(track['y'],[3.,7.,10.])
        self.assertIs(result['mask'],track['mask'])
        self.assertFalse(np.shares_memory(result['y'],y))

    def test_invalid_displacement(self):
        with self.assertRaises(ValueError):shifted_track(dict(y=np.zeros(3)),np.zeros((1,2)),np.ones((1,2)),0)
