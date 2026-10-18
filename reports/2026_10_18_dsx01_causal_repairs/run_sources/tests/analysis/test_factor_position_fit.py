import numpy as np
import pytest

from leo.analysis.research.factor_position_fit import factor_gauss_newton


def test_factors_share_position_with_independent_receiver_calibrations():
    # Each scan's constant is independent; the curved geometric columns jointly
    # identify east/north. No reference coordinate enters the numerical solver.
    t = np.linspace(-1, 1, 31)
    observed = [1.4 * t + -2.3 * t**2 + 8, 1.4 * t**2 - 2.3 * t + -11]
    functions = [
        lambda x: x[0] * t + x[1] * t**2 + x[2] - observed[0],
        lambda x: x[0] * t**2 + x[1] * t + x[2] - observed[1],
    ]
    result = factor_gauss_newton(
        functions, [[0, 1, 2], [0, 1, 3]], [0, 0, 0, 0], [-12.5] * 4, [12.5] * 4
    )
    np.testing.assert_allclose(result["parameters"], [1.4, -2.3, 8, -11], atol=1e-5)
    assert np.all(np.diff([r["score"] for r in result["history"]]) < 0)


def test_shared_parameter_is_applied_once_per_factor_and_maps_are_validated():
    result = factor_gauss_newton(
        [lambda x: np.array([x[0] - 3]), lambda x: np.array([2 * (x[0] - 3)])],
        [[0], [0]],
        [0],
        [-5],
        [5],
    )
    assert result["parameters"][0] == pytest.approx(3, abs=1e-6)
    with pytest.raises(ValueError):
        factor_gauss_newton([lambda x: x], [[0, 0]], [0], [-5], [5])
