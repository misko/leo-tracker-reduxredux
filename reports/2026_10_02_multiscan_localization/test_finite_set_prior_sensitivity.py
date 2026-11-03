import numpy as np
import pytest
from finite_set_prior_sensitivity import prior_sensitivity


def test_prior_precision_response_matches_quadratic_refit_derivative():
    data_hessian = np.array([[2.0, 0.0, 1.0], [0.0, 3.0, -1.0], [1.0, -1.0, 2.0]])
    prior_hessian = np.diag([0.0, 0.0, 1.0])
    linear = np.array([0.3, -0.6, 2.0])
    hessian = data_hessian + prior_hessian
    vector = np.linalg.solve(hessian, linear)
    prior_gradient = prior_hessian @ vector
    result = prior_sensitivity(
        hessian, np.zeros(3), prior_gradient, vector,
        [(None, None)] * 3, np.array([20.0, 20.0, 1.0]),
    )
    step = 1e-5
    plus = np.linalg.solve(data_hessian + (1 + step) * prior_hessian, linear)
    minus = np.linalg.solve(data_hessian + (1 - step) * prior_hessian, linear)
    expected = (plus - minus) / (2 * step) * np.array([20.0, 20.0, 1.0])
    np.testing.assert_allclose(result["physical_response_per_unit_precision"], expected)
    np.testing.assert_allclose(
        result["linearized_zero_precision_position_shift_km"], -expected[:2],
    )


def test_one_free_set_uses_total_gradient_at_bound():
    result = prior_sensitivity(
        np.array([[2.0, 0.0, 1.0], [0.0, 2.0, 0.0], [1.0, 0.0, 2.0]]),
        np.array([0.0, 0.0, -1.0]), np.array([0.0, 0.0, 3.0]),
        np.array([0.0, 0.0, 3.0]), [(None, None), (None, None), (-3.0, 3.0)],
        np.ones(3),
    )
    assert result["free_mask"] == [True, True, False]
    np.testing.assert_array_equal(result["physical_response_per_unit_precision"], 0)


@pytest.mark.parametrize("minimum,reason", [(0.0, "nonpositive_curvature"),
                                              (1e-14, "ill_conditioned")])
def test_singular_geometry_is_not_silently_regularized(minimum, reason):
    result = prior_sensitivity(
        np.diag([1.0, minimum]), np.zeros(2), np.ones(2), np.zeros(2),
        [(None, None)] * 2, np.ones(2),
    )
    assert result["available"] is False
    assert result["reason"] == reason
