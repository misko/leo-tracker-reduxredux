import unittest
import numpy as np
from old_b_panel import decompose


class DecompositionTests(unittest.TestCase):
    def test_constant_revision_is_squared_mean_not_spread(self):
        mean, spread, second, stats=decompose([[1,2,3],[1,2,3]])
        np.testing.assert_array_equal(spread,np.zeros((3,3)))
        np.testing.assert_array_equal(second,np.outer(mean,mean))
        self.assertEqual(stats['squared_mean_trace_fraction'],1)

    def test_symmetric_revision_has_zero_signed_mean(self):
        mean, spread, second, stats=decompose([[1,2,3],[-1,-2,-3]])
        np.testing.assert_array_equal(mean,np.zeros(3))
        np.testing.assert_array_equal(spread,second)
        self.assertEqual(stats['squared_mean_trace_fraction'],0)


if __name__=='__main__':unittest.main()
