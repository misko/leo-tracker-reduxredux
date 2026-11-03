import unittest
import numpy as np
from constrained_fit import kkt_residual


class ConstraintTests(unittest.TestCase):
    def test_sum_constraint_allows_nonzero_outward_gradient(self):
        self.assertLess(kkt_residual([-1,-1],[.5,.5],[(None,None)]*2,np.array([[1.,1.]]),-1,1),1e-10)

    def test_same_gradient_is_not_stationary_interior(self):
        self.assertEqual(kkt_residual([-1,-1],[.4,.4],[(None,None)]*2,np.array([[1.,1.]]),-1,1),1.)

    def test_fixed_coordinate_gradient_does_not_signal_failure(self):
        self.assertEqual(kkt_residual([100,0],[0,.4],[(0,0),(None,None)],np.array([[0.,1.]]),-1,1),0.)

    def test_wrong_direction_at_boundary_still_descends(self):
        self.assertEqual(kkt_residual([1,1],[.5,.5],[(None,None)]*2,np.array([[1.,1.]]),-1,1),1.)
