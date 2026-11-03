import itertools
from pathlib import Path
import sys
import unittest
import numpy as np
from scipy.special import logsumexp
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probes import probe
from source_partition_fast import partition


class PosteriorProbeTests(unittest.TestCase):
    def test_matches_exhaustive_correlated_assignments(self):
        values = [np.array([0., -1., -2., -1.5]), np.array([0., -2., -.3, -3.])]
        factors = [([0, 1], v, np.array([[0.], [1.], [1.], [1.]])) for v in values]
        assignments = list(itertools.product(range(2), repeat=2))
        weights = np.array([sum(values[c][sum(1 << t for t, a in enumerate(row) if a == c)] for c in range(2)) for row in assignments])
        z = logsumexp(weights)
        probabilities = np.exp(weights - z)
        expected = probabilities @ np.array([[row[0] == 0, row[1] == 1] for row in assignments])
        score, gradient, result = probe(2, factors, [100, 200], [100, 200])
        old_score, old_gradient = partition(2, factors)
        self.assertAlmostEqual(score, z)
        self.assertAlmostEqual(score, old_score)
        np.testing.assert_allclose(gradient, old_gradient)
        np.testing.assert_allclose(result['reference_probability'], expected)
        self.assertAlmostEqual(result['entropy'], -float(probabilities @ np.log(probabilities)))

    def test_impossible_assignment_does_not_corrupt_entropy(self):
        factors = [([0], np.array([0., -np.inf]), np.zeros((2, 1))), ([0], np.array([0., -9.]), np.zeros((2, 1)))]
        _, _, result = probe(1, factors, [1, 2], [1])
        self.assertEqual(result['reference_probability'][0], 0.)
        self.assertEqual(result['entropy'], 0.)
