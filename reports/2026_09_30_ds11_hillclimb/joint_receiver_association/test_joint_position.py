import unittest
import numpy as np
from joint_position import mixture


class MixtureTests(unittest.TestCase):
    def test_gradient_and_permutation(self):
        scores = np.array([-2., -.5, -4.])
        derivatives = np.array([[1., 2., -1.], [-.5, .1, .3], [.2, -.3, 4.]])
        value, grad = mixture(scores, derivatives, 20)
        for axis in range(3):
            d = derivatives[:, axis] * 1e-5
            numerical = (mixture(scores + d, derivatives, 20)[0] - mixture(scores - d, derivatives, 20)[0]) / 2e-5
            self.assertAlmostEqual(grad[axis], numerical, places=8)
        other = mixture(scores[::-1], derivatives[::-1], 20)
        self.assertAlmostEqual(value, other[0])
        np.testing.assert_allclose(grad, other[1])

    def test_impossible(self):
        value, gradient = mixture(np.array([-np.inf]), np.ones((1, 3)), 10)
        self.assertEqual(value, -np.inf)
        np.testing.assert_array_equal(gradient, 0.)
