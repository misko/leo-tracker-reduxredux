import numpy as np
from satellite65745_identity_search import local_minima, weighted_cost


def test_weighted_cost_uses_every_point():
    value = weighted_cost(np.array([[3., 4.], [0., 10.]]), np.ones((2, 2), bool), [1., 1.])
    np.testing.assert_allclose(value, [12.5, 50.])


def test_invisible_point_is_not_free():
    assert weighted_cost(np.zeros(2), [True, False], np.ones(2)) > 1e9


def test_minima_include_boundaries():
    np.testing.assert_array_equal(local_minima([0., 2., 1., 3., 0.]), [0, 2, 4])


def test_flat_plateau_is_only_refined_once():
    np.testing.assert_array_equal(local_minima(np.ones(401)), [0])
