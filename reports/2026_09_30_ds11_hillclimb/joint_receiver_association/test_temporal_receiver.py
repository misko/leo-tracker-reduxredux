import itertools
import unittest
import numpy as np
from scipy.special import softmax
from temporal_receiver import sequence_score


class TemporalTests(unittest.TestCase):
    def test_enumeration_and_masking(self):
        times = np.array([0., .4, 2.])
        p = np.array([[.2, .3, .5], [.4, .5, .1], [.3, .1, .6]])
        total = 0.
        for states in itertools.product(range(3), repeat=3):
            weight = p[0, states[0]]
            for i in (1, 2):
                rho = np.exp(-(times[i] - times[i - 1]) / 1.2)
                weight *= rho * (states[i] == states[i - 1]) + (1 - rho) * p[i, states[i]]
            if states[0] == 0 and states[2] == 2:
                total += weight
        value, _ = sequence_score(times, np.log(p)[None], [1, 2, 3], [1, 0, 1], 1.2)
        self.assertAlmostEqual(value[0], np.log(total))
        other, _ = sequence_score(times, np.log(p)[None], [1, -1, 3], [1, 0, 1], 1.2)
        np.testing.assert_allclose(value, other)

    def test_independent_limit_and_empty_training(self):
        p = np.array([[[.2, .3, .5], [.4, .5, .1]]])
        value, _ = sequence_score([0., 2.], np.log(p), [1, 3], [1, 1], 0.)
        self.assertAlmostEqual(value[0], np.log(.2 * .1))
        value, _ = sequence_score([0., 2.], np.log(p), [-1, -1], [0, 0], 3.)
        self.assertEqual(value[0], 0.)

    def test_sensitivities(self):
        feature = np.array([[.2, -.1, .6], [-.4, .5, .3], [.2, .1, -.7]])
        def evaluate(parameters, derivative=False):
            p = softmax(parameters[0] * feature, axis=1)
            dlog = np.zeros((1, 3, 3, 2))
            dlog[0, :, :, 0] = feature - (p * feature).sum(axis=1)[:, None]
            return sequence_score([0., .3, 1.], np.log(p)[None], [1, 2, 3], [1, 0, 1], np.exp(parameters[1]), dlog, 1)
        parameters = np.array([.7, -.2])
        _, gradient = evaluate(parameters)
        for axis in range(2):
            delta = np.eye(2)[axis] * 1e-5
            numerical = (evaluate(parameters + delta)[0] - evaluate(parameters - delta)[0]) / 2e-5
            self.assertAlmostEqual(gradient[0, axis], numerical[0], places=8)
