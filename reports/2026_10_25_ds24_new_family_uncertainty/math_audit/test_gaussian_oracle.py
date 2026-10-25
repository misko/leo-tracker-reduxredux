"""Algebra tests for a target predictive factor sharing parent uncertainty."""
import unittest
import numpy as np
from gaussian_oracle import dense_nll, schur_factorization, covariance_from_features


class CovarianceTests(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(2026102511)
        self.parent_count, self.target_count, width = 4, 5, 6
        self.design = self.rng.normal(size=(9, width))
        z = self.rng.normal(size=(width, width))
        self.parent_covariance = z@z.T + .4*np.eye(width)
        self.root = np.linalg.cholesky(self.parent_covariance)
        self.sigma = self.rng.uniform(.5, 1.5, 9)
        self.phase = np.r_[np.zeros(4), self.rng.normal(size=5)]
        self.constant = np.r_[np.zeros(4), np.full(5, .3)]
        self.shape = np.vstack((np.zeros((4, 3)), self.rng.normal(size=(5, 3))))
        self.raw = self.rng.normal(size=9)

    def features(self, scale):
        return np.column_stack((self.design@self.root, self.phase, self.constant, scale*self.shape))

    def test_dense_equals_coefficient_space_and_schur(self):
        for scale in (0., 1.):
            uncertainty = self.features(scale)
            covariance = covariance_from_features(self.sigma, uncertainty)
            reference = dense_nll(self.raw, covariance)['negative_twice_log_density']
            a, b = uncertainty/self.sigma[:, None], self.raw/self.sigma
            gram = np.eye(a.shape[1]) + a.T@a
            coefficient = np.linalg.solve(gram, a.T@b)
            quadratic = (b-a@coefficient)@(b-a@coefficient)+coefficient@coefficient
            coefficient_loss = quadratic + 2*np.log(self.sigma).sum() + np.linalg.slogdet(gram)[1] + 9*np.log(2*np.pi)
            self.assertAlmostEqual(reference, coefficient_loss, places=12)
            self.assertAlmostEqual(reference, schur_factorization(self.raw, covariance, 4), places=12)

    def test_covariance_increment_is_exact_original_three_mode_prior(self):
        zero = covariance_from_features(self.sigma, self.features(0.))
        prior = covariance_from_features(self.sigma, self.features(1.))
        np.testing.assert_allclose(prior-zero, self.shape@self.shape.T, atol=1e-13, rtol=0.)
        self.assertGreaterEqual(np.linalg.eigvalsh(prior-zero).min(), -1e-12)
        self.assertEqual(np.linalg.matrix_rank(prior-zero, tol=1e-10), 3)
        np.testing.assert_array_equal(zero[:4, :4], prior[:4, :4])
        np.testing.assert_array_equal(zero[:4, 4:], prior[:4, 4:])

    def test_joint_target_is_not_independent_of_existing_predictive(self):
        covariance = covariance_from_features(self.sigma, self.features(1.))
        joint = dense_nll(self.raw, covariance)['negative_twice_log_density']
        independent = dense_nll(self.raw[:4], covariance[:4, :4])['negative_twice_log_density']
        independent += dense_nll(self.raw[4:], covariance[4:, 4:])['negative_twice_log_density']
        self.assertGreater(abs(joint-independent), 1.)
        expected = self.design[:4]@self.parent_covariance@self.design[4:].T
        np.testing.assert_allclose(covariance[:4, 4:], expected, atol=1e-13)

    def test_shape_basis_rotation_and_zero_column_removal(self):
        q, _ = np.linalg.qr(self.rng.normal(size=(3, 3)))
        original = covariance_from_features(self.sigma, self.features(1.))
        rotated = np.column_stack((self.features(0.)[:, :-3], self.shape@q))
        np.testing.assert_allclose(original, covariance_from_features(self.sigma, rotated), atol=1e-13)
        np.testing.assert_array_equal(covariance_from_features(self.sigma, self.features(0.)),
            covariance_from_features(self.sigma, self.features(0.)[:, :-3]))


if __name__ == '__main__':
    unittest.main()
