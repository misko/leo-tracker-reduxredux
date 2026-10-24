"""Independent numerical identities for the research information diagnostic."""
import unittest
import numpy as np

from diagnose_information import information
from ds23_position_information import marginal_position_information


class InformationTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(20261024)
        self.u = rng.normal(size=(80, 5))
        self.j = self.u[:, :2] + rng.normal(scale=.01, size=(80, 2))
        self.w = rng.uniform(.1, 2., 80)
        self.prior = rng.uniform(.1, 3., 5)

    def test_augmented_QR_agrees_in_near_confounded_design(self):
        got = information(self.j, self.u, self.w, self.prior)
        expected = marginal_position_information(self.j, self.u, self.w, self.prior)
        np.testing.assert_allclose(got, expected, rtol=1e-11, atol=1e-11)

    def test_adding_points_and_freezing_nuisance_cannot_reduce_information(self):
        full = information(self.j, self.u, self.w, self.prior)
        half = information(self.j[:40], self.u[:40], self.w[:40], self.prior)
        fixed = information(self.j, self.u[:, 1:], self.w, self.prior[1:])
        self.assertGreaterEqual(np.linalg.eigvalsh(full-half).min(), -1e-12)
        self.assertGreaterEqual(np.linalg.eigvalsh(fixed-full).min(), -1e-12)

    def test_confounded_information_saturates_with_measurement_precision(self):
        # If J=U, arbitrarily accurate data cannot distinguish position from
        # nuisance: remaining information approaches the nuisance prior.
        j = self.u[:, :2]
        u = j.copy()
        prior = np.array([.5, 2.])
        got = information(j, u, self.w*1e10, prior)
        np.testing.assert_allclose(got, np.diag(prior), rtol=1e-8, atol=1e-8)


if __name__ == '__main__':
    unittest.main()
