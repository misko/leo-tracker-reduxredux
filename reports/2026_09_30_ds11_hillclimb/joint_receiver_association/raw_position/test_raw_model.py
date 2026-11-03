import unittest
import numpy as np
from raw_model import source_average


class SourceAverageTests(unittest.TestCase):
    def test_all_subsets_and_duplicate_anchor(self):
        windows=[[(0,0,b'b'),(1,0,b'a'),(1,0,b'a')],[(0,1,b'c')]]
        values=[np.array([2.,4.]),np.array([7.])]
        derivatives=[np.array([[1.,0.],[3.,0.]]),np.array([[5.,0.]])]
        score,grad=source_average(2,windows,values,derivatives)
        np.testing.assert_array_equal(score,[0.,3.,7.,5.5])
        np.testing.assert_array_equal(grad[:,0],[0.,2.,5.,4.])
        repeat=source_average(2,windows*3,values,derivatives)
        np.testing.assert_array_equal(repeat[0],score)
        np.testing.assert_array_equal(repeat[1],grad)

    def test_no_owned_windows_is_zero(self):
        score,grad=source_average(1,[],[np.array([1.])],[np.zeros((1,3))])
        np.testing.assert_array_equal(score,[0.,0.]);self.assertFalse(grad.any())
