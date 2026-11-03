import numpy as np
from plot_south_attribution import binned_means


def test_binned_means_require_support_and_preserve_signed_residuals():
    actual = binned_means(np.array([1., 2., 3., 11.]), np.array([-10., 0., 10., 100.]),
                          np.ones(4))
    np.testing.assert_allclose(actual, [[2., 0.]])
    assert binned_means(np.array([]), np.array([]), np.array([])).shape == (0, 2)
