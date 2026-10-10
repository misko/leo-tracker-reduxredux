"""Independent receiver-block sign/prior/locked-direction checks."""

import numpy as np
from clock_step import LINEAR, step
from test_clock_step import fixture


def test_surrogate_gradient_at_current_matches_exact_clock_gradient():
    model, vector, clock = fixture("fitted-c")
    _, _, exact_gradient, terms = model.evaluate_joint(vector, clock)
    collapsed = LINEAR["collapse_mixture"](
        terms.residual_hz, terms.responsibilities, model.score.sigma_hz
    )
    surrogate_gradient = (
        -model.clock_design.T @ (collapsed["weights"] * collapsed["residual_hz"])
        + model.precision @ clock
    )
    # Satellite coefficients are held fixed and are implemented outside the
    # receiver design. Only optimized receiver columns must match gradients.
    receiver_columns = np.r_[
        np.arange(model.smooth_clock_count), np.arange(len(clock) - 2, len(clock))
    ]
    np.testing.assert_allclose(
        surrogate_gradient[receiver_columns],
        exact_gradient[receiver_columns],
        rtol=1e-12,
        atol=1e-12,
    )


def test_fixed_rf_fitted_arm_and_satellite_coefficients_remain_locked():
    model, vector, clock = fixture("fitted-c")
    model.fixed_rf_drift = True
    clock[-2:] = 0
    result = step(model, vector, clock, "fitted-c")
    assert result["objective_after"] <= result["objective_before"]
    np.testing.assert_array_equal(result["clock_coefficients"][-2:], [0, 0])
    np.testing.assert_array_equal(
        result["clock_coefficients"][model.slope_slice], clock[model.slope_slice]
    )
