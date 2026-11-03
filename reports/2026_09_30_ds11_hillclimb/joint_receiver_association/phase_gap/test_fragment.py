import unittest
import numpy as np
from fragment_model import predict


class FragmentTests(unittest.TestCase):
    def test_fixed_masks_and_held_isolation(self):
        t=np.arange(20.)
        y=(950+4*t+.1*t*t)%1000
        train=t<12;held=t>=15
        a=predict(t,y,train,held,1000)
        changed=y.copy();changed[~train]+=300
        b=predict(t,changed,train,held,1000)
        self.assertTrue(a['qualified'])
        np.testing.assert_allclose(a['errors_us'],0,atol=1e-6)
        np.testing.assert_array_equal(a['coefficients'],b['coefficients'])
        np.testing.assert_allclose(b['errors_us'],300,atol=1e-6)

    def test_overlap_is_invalid_and_missing_support_explicit(self):
        with self.assertRaises(ValueError):predict([0],[0],[True],[True],1000)
        self.assertFalse(predict([0,1],[0,1],[True,False],[False,True],1000)['qualified'])
