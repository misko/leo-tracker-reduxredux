import unittest

import numpy as np

from information import check


class Quadratic:
    def __init__(self,matrix,weight):
        self.matrix=np.asarray(matrix)
        self.weight=weight

    def evaluate(self,x):
        return dict(gradient=-self.matrix@x,signal_weights=[self.weight])


class InformationTests(unittest.TestCase):
    def test_timing_is_profiled_before_position_precision(self):
        model=Quadratic([[2.,0,1.],[0,3.,0],[1.,0,1.]],4.)
        result=check(model,[1,2,3])
        self.assertTrue(result['scientifically_qualified'])
        np.testing.assert_allclose(result['horizontal_profile_eigenvalues'],[1,3],atol=1e-10)

    def test_flat_and_weak_signal_rejected(self):
        self.assertFalse(check(Quadratic(np.zeros((3,3)),0),[0,0,0])['scientifically_qualified'])
        self.assertFalse(check(Quadratic(np.eye(3),2.9),[0,0,0])['scientifically_qualified'])
        self.assertFalse(check(Quadratic(np.diag([1e-4,1,1]),4),[0,0,0])['scientifically_qualified'])


if __name__=='__main__':
    unittest.main()
