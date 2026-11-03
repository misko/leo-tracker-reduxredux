import unittest

import numpy as np
from study import covariance


class Tests(unittest.TestCase):
    def test_mean_model_variance(self):
        values = np.array([[1.0, 2.0], [2.0, -1.0], [-2.0, 4.0], [3.0, 5.0]])
        centered = values - values.mean(0)
        expected = np.cov(values.T, ddof=1) / len(values)
        np.testing.assert_allclose(covariance(np.eye(2) * len(values), centered), expected)

    def test_within_cluster_duplication_does_not_fake_precision(self):
        h = np.array([[4.0, 0.2], [0.2, 6.0]])
        g = np.array([[1.0, 2.0], [-2.0, 3.0], [1.0, -5.0]])
        np.testing.assert_allclose(covariance(7 * h, 7 * g), covariance(h, g))


if __name__ == "__main__":
    unittest.main()
