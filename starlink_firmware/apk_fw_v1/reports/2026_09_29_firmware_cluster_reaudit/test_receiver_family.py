import numpy as np
from receiver_family import correlation, coupled_reference


def test_receiver_correlation_removes_static_coordinate_bias():
    a = np.arange(12).reshape(4, 3)
    assert abs(correlation(a, a + np.array([100, -20, 50])) - 1) < 1e-12
    assert abs(correlation(a, -a) + 1) < 1e-12
    assert correlation(np.ones((4, 3)), a) == 0


def test_coupled_cycles_weight_unequal_intervals():
    values, weights = coupled_reference([np.array([[1., 0.]]), np.array([[1., 0., 0.]])])
    np.testing.assert_allclose(weights, [1 / 3, 1 / 6, 1 / 6, 1 / 3])
    np.testing.assert_allclose(values[:, 0], [1, .5, 0, 0])
    np.testing.assert_allclose(weights @ values, [5 / 12])
