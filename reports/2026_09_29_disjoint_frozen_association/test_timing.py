import unittest
import numpy as np
from run import timing_fit


class Quadratic:
    def evaluate(self,x,gradient=True):
        x=np.asarray(x)
        residual=x[2:]-np.array([.3,-.8])
        return dict(score=-float(residual@residual),gradient=np.r_[17.,-31.,-2*residual])


class TimingTest(unittest.TestCase):
    def test_holds_position_and_optimizes_only_timing(self):
        result=timing_fit(Quadratic(),[2.,-3.],[0.,0.])
        self.assertTrue(result['qualified'])
        np.testing.assert_allclose(result['x'],[2.,-3.,.3,-.8],atol=1e-7)


if __name__=='__main__':
    unittest.main()
