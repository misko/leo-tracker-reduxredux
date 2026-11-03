import unittest
import numpy as np
from conditional_receiver import design, score_gradient


class ConditionalTests(unittest.TestCase):
    def test_normalization_and_gradient(self):
        x = design(np.tile([.3, .4, .866], (3, 1)), [0, 0, 0], 1, 'signed')
        p = np.array([-.5, .8, 3.])
        scores, grad = score_gradient(p, x, [1, 2, 3])
        self.assertAlmostEqual(np.exp(scores).sum(), 1.)
        for i in range(3):
            step = np.eye(3)[i] * 1e-5
            numerical = (score_gradient(p + step, x, [1, 2, 3])[0].sum() - score_gradient(p - step, x, [1, 2, 3])[0].sum()) / 2e-5
            self.assertAlmostEqual(grad[i], numerical, places=7)

    def test_swap_and_zero_geometry_parity(self):
        los = np.array([[.6, 0., .8], [-.6, 0., .8]])
        a = design(los, [0, 0], 1, 'signed')
        b = design(los, [0, 0], 1, 'swapped')
        p = np.array([.2, -.1, 2.])
        np.testing.assert_allclose(score_gradient(p, a, [1, 2])[0], score_gradient(p[[1, 0, 2]], b, [2, 1])[0])
        np.testing.assert_allclose(score_gradient([.2, -.1, 0.], a, [1, 2])[0], score_gradient([.2, -.1], design(los, [0, 0], 1, 'receiver'), [1, 2])[0])

    def test_unknown_or_empty_is_not_negative(self):
        x = design([[0., 0., 1.]], [0], 1, 'receiver')
        for state in (-1, 0, 4):
            with self.assertRaises(ValueError):
                score_gradient([0., 0.], x, [state])
