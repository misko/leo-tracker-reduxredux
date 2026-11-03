import unittest
import numpy as np
from run import allocate,differential


class CorrectionTests(unittest.TestCase):
    def test_allocations_same_difference_different_common_mode(self):
        d = np.array([-30.,0.,40.])
        for alpha in (0.,.5,1.):
            np.testing.assert_allclose(allocate(1,d,alpha)-allocate(0,d,alpha),-d)
        np.testing.assert_array_equal(allocate(1,d,0.),np.zeros(3))
        np.testing.assert_array_equal(allocate(0,d,1.),np.zeros(3))

    def test_training_only_native_conversion_and_fallback(self):
        t = np.arange(10.)
        a = dict(visits=list(range(10)),times_s=t.tolist(),mask=t<6,rf_hz=10.71e9,y=(200+2*t)*11.2/10.71)
        b = dict(a,y=np.zeros(10))
        first = differential(a,b,(2.,1.,8.))
        expected = np.where((t>=1)&(t<=8),2*(t-2.5)*11.2/10.71,0)
        np.testing.assert_allclose(first[0],expected,atol=1e-8)
        changed = dict(a,y=a['y'].copy())
        changed['y'][6:] += 100000
        second = differential(changed,b,(2.,1.,8.))
        np.testing.assert_array_equal(first,second)


if __name__=='__main__':
    unittest.main()
