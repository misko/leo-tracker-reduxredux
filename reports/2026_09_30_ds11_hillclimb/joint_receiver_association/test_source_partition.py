import itertools
import unittest
import numpy as np
from scipy.special import logsumexp
from source_partition import partition


def brute(n, factors):
    scores, gradients = [], []
    for assignment in itertools.product(range(len(factors)), repeat=n):
        value, grad = 0., np.zeros(factors[0][2].shape[-1])
        for s, (tracks, weights, derivatives) in enumerate(factors):
            members = [i for i, chosen in enumerate(assignment) if chosen == s]
            if any(i not in tracks for i in members):
                value = -np.inf
                break
            subset = sum(1 << tracks.index(i) for i in members)
            value += weights[subset]
            grad += derivatives[subset]
        scores.append(value)
        gradients.append(grad)
    total = logsumexp(scores)
    return total, np.exp(np.array(scores) - total) @ np.array(gradients)


class SourcePartitionTests(unittest.TestCase):
    def test_enumeration_derivative_and_source_order(self):
        rng = np.random.default_rng(7)
        factors = []
        for support in ([0, 1], [1, 2], [0, 2]):
            values = rng.normal(size=4)
            grad = rng.normal(size=(4, 2))
            values[0] = 0.
            grad[0] = 0.
            factors.append((support, values, grad))
        actual = partition(3, factors)
        expected = brute(3, factors)
        self.assertAlmostEqual(actual[0], expected[0])
        np.testing.assert_allclose(actual[1], expected[1], atol=1e-12)
        reverse = partition(3, factors[::-1])
        np.testing.assert_allclose(reverse[1], actual[1], atol=1e-12)
        self.assertAlmostEqual(reverse[0], actual[0])
        for axis in range(2):
            plus = [(t, v + 1e-5 * g[:, axis], g) for t, v, g in factors]
            minus = [(t, v - 1e-5 * g[:, axis], g) for t, v, g in factors]
            num = (partition(3, plus)[0] - partition(3, minus)[0]) / 2e-5
            self.assertAlmostEqual(num, actual[1][axis], places=8)

    def test_independent_assignment_normalizes(self):
        factors = []
        for source in range(3):
            values = np.array([-int(s).bit_count() * np.log(3) for s in range(8)])
            factors.append(([0, 1, 2], values, np.zeros((8, 1))))
        score, grad = partition(3, factors)
        self.assertAlmostEqual(score, 0.)
        self.assertEqual(grad[0], 0.)

    def test_one_source_can_own_all_fragments(self):
        values = np.array([0., -3., -4., -1.])
        result = partition(2, [([0, 1], values, np.zeros((4, 1)))])
        self.assertEqual(result[0], -1.)
        with self.assertRaises(ValueError):
            partition(17, [])
