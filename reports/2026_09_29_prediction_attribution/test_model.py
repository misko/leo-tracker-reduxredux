import unittest

import numpy as np
from study import source

source.numerical_imports()
from model import decompose  # noqa: E402


class DecompositionTests(unittest.TestCase):
    def test_identity_matches_explicit_density(self):
        likelihood = np.array([[0.2, 0.5], [0.8, 0.1]])
        prior = np.array([0.3, 0.7])
        result = decompose(np.log(likelihood), np.log(prior), np.ones((2, 2)))
        self.assertAlmostEqual(result["log_score"], np.log(0.3 * 0.2 * 0.5 + 0.7 * 0.8 * 0.1))
        self.assertAlmostEqual(sum(result["expected_tracks"]) - result["kl"], result["log_score"])
        self.assertGreater(result["kl"], 0)

    def test_constant_likelihood_preserves_prior_and_permutation(self):
        scores = np.array([[-10000.0, -5], [-10000.0, -5]])
        prior = np.log([0.1, 0.9])
        r = decompose(scores, prior, np.zeros_like(scores))
        self.assertAlmostEqual(r["kl"], 0)
        self.assertAlmostEqual(r["log_score"], -10005)
        rev = decompose(scores[:, ::-1], prior, np.zeros_like(scores))
        np.testing.assert_allclose(rev["expected_tracks"], r["expected_tracks"][::-1])


if __name__ == "__main__":
    unittest.main()
