"""Projection invariance and exact nuisance confounding checks."""
import unittest

import numpy as np

from audit_position_observability import projected_information, retention


class ObservabilityTests(unittest.TestCase):
    def test_confounding_and_rescaling(self):
        rng = np.random.default_rng(77)
        b = rng.normal(size=(30, 3))
        a = np.column_stack([b[:, 0], rng.normal(size=30)])
        first, rank, _ = projected_information(a, b)
        second, rank2, _ = projected_information(a, b*np.array([1e-9, 1e8, 2.]))
        self.assertEqual(rank, rank2)
        self.assertLess(first[0, 0], 1e-20)
        np.testing.assert_allclose(first, second, atol=1e-12)

    def test_retention_generalized_eigenvalues(self):
        reference = np.array([[4., 1.], [1., 2.]])
        np.testing.assert_allclose(retention(.3*reference, reference), [.3, .3])


if __name__ == '__main__':
    unittest.main()
