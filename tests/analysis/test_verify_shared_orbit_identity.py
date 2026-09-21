import numpy as np

from tools.verify_shared_orbit_identity import (
    conservative_omitted_fraction_bound,
    quadratic_state,
)


def test_quadratic_state_reproduces_cached_nodes():
    centre = np.array([[[2.0, 3.0, 4.0]]])
    minus = np.array([[[1.0, 1.0, 1.0]]])
    plus = np.array([[[5.0, 7.0, 9.0]]])
    np.testing.assert_allclose(quadratic_state(centre, minus, plus, 0.0), centre)
    np.testing.assert_allclose(quadratic_state(centre, minus, plus, -1.0), minus)
    np.testing.assert_allclose(quadratic_state(centre, minus, plus, 1.0), plus)


def test_tail_bound_counts_omitted_perfect_fits_and_zero_tail():
    assert conservative_omitted_fraction_bound(np.array([-20.0]), 0, 10, 250.0) == 0
    one = conservative_omitted_fraction_bound(np.array([-55.0]), 1, 10, 250.0)
    many = conservative_omitted_fraction_bound(np.array([-55.0]), 100, 10, 250.0)
    assert 0 < one < many < 1
