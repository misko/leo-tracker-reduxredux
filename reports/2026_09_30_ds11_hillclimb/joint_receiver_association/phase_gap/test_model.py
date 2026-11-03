import unittest
import numpy as np
from model import fit, wrap


class PhaseGapTests(unittest.TestCase):
    def fixture(self):
        t=np.linspace(0,30,121)
        y=(1325+2*t+.01*t*t)%1333.3333333333333
        mask=np.arange(len(t))%2 == 0
        return t,y,mask,1333.3333333333333

    def test_wrapped_quadratic_extrapolation(self):
        args=self.fixture();r=fit(*args)
        self.assertTrue(r['qualified'])
        self.assertLess(max(abs(np.array(r['held_errors_us']))),1e-6)
        self.assertGreater(min(r['gap_s']),0)

    def test_held_and_late_training_phase_cannot_change_fit(self):
        t,y,mask,p=self.fixture();first=fit(t,y,mask,p)
        changed=y.copy();changed[(~mask)|(t>first['boundary_s'])]+=200
        second=fit(t,changed,mask,p)
        np.testing.assert_array_equal(first['coefficients'],second['coefficients'])
        np.testing.assert_allclose(second['held_errors_us'],200,atol=1e-6)

    def test_missing_support_and_circular_residual(self):
        self.assertFalse(fit([0,1],[0,1],[False,False],10)['eligible'])
        np.testing.assert_allclose(wrap([9,-9],10),[-1,1])


if __name__ == '__main__':unittest.main()
