from types import SimpleNamespace

import numpy as np
import pytest
from information_curvature import (
    calibrated_current_vector,
    central_gradient_hessian,
    compare_hessians,
    matrix_spectrum,
    profile_position_information,
)


def test_central_gradient_hessian_recovers_quadratic_at_both_steps():
    hessian = np.array(
        [
            [4.0, 1.0, -0.5],
            [1.0, 3.0, 0.25],
            [-0.5, 0.25, 2.0],
        ]
    )
    linear = np.array([2.0, -3.0, 1.0])

    def evaluate(vector):
        return 0.5 * vector @ hessian @ vector + linear @ vector, hessian @ vector + linear

    results = [
        central_gradient_hessian(evaluate, [0.4, -1.2, 2.0], [20.0, 5.0, 1000.0], step)
        for step in (1.0e-5, 3.0e-6)
    ]
    for result in results:
        np.testing.assert_allclose(result["hessian"], hessian, rtol=2.0e-11, atol=2.0e-11)
        assert result["relative_asymmetry"] < 1.0e-10
    assert compare_hessians(results[0]["hessian"], results[1]["hessian"])[
        "relative_frobenius_difference"
    ] < 1.0e-10


def test_schur_profile_matches_direct_block_calculation_and_uncertainty():
    nuisance = np.diag([4.0, 5.0])
    cross = np.array([[1.0, 0.5], [0.0, 1.0]])
    position = np.array([[9.0, 1.0], [1.0, 7.0]])
    hessian = np.block([[position, cross], [cross.T, nuisance]])
    expected = position - cross @ np.linalg.inv(nuisance) @ cross.T
    result = profile_position_information(hessian)
    np.testing.assert_allclose(result["profiled_position_information"], expected)
    np.testing.assert_allclose(
        result["local_uncertainty"]["covariance_km2"],
        np.linalg.inv(expected),
    )
    assert result["information_degeneracy"] is False
    assert result["profiled_to_fixed_trace_fraction"] < 1.0


def test_singular_nuisance_and_indefinite_profile_are_reported_not_hidden():
    singular = np.diag([4.0, 3.0, 0.0])
    result = profile_position_information(singular)
    assert result["information_degeneracy"] is True
    assert result["nuisance_spectrum"]["near_zero_count"] == 1
    indefinite = matrix_spectrum(np.diag([2.0, -0.1]))
    assert indefinite["negative_count"] == 1
    assert indefinite["finite_psd_with_tolerance"] is False


def test_nuisance_optimizer_scaling_makes_schur_profile_unit_invariant():
    scaled = np.array(
        [
            [8.0, 1.0, 2.0, -1.0],
            [1.0, 6.0, 0.5, 1.5],
            [2.0, 0.5, 5.0, 0.25],
            [-1.0, 1.5, 0.25, 4.0],
        ]
    )
    scales = np.array([20.0, 20.0, 1000.0, 0.01])
    nuisance_transform = np.diag([1.0, 1.0, *scales[2:]])
    physical = np.linalg.inv(nuisance_transform) @ scaled @ np.linalg.inv(
        nuisance_transform
    )
    expected = profile_position_information(scaled)
    actual = profile_position_information(physical, scales)
    np.testing.assert_allclose(
        actual["profiled_position_information"],
        expected["profiled_position_information"],
    )
    assert actual["nuisance_spectrum"]["positive_rank"] == 2


def test_position_uncertainty_is_suppressed_for_coupled_discarded_mode():
    hessian = np.array(
        [
            [2.0, 0.0, 1.0],
            [0.0, 2.0, 0.0],
            [1.0, 0.0, 0.0],
        ]
    )
    result = profile_position_information(hessian)
    assert result["discarded_modes_couple_to_position"] is True
    assert result["nuisance_profile_valid"] is False
    assert result["local_uncertainty"]["covariance_km2"] is None


def test_central_difference_rejects_infeasible_symmetric_probe():
    def evaluate(vector):
        return float(vector @ vector), 2.0 * np.asarray(vector)

    with pytest.raises(ValueError, match="feasible"):
        central_gradient_hessian(
            evaluate,
            [0.0, 0.0],
            [1.0, 1.0],
            1.0e-5,
            validator=lambda vector: vector[0] <= 0.0,
        )


def test_calibrated_current_vector_preserves_sealed_rf_coefficient():
    class Base:
        @staticmethod
        def state(vector):
            return {"parameters": np.asarray(vector, dtype=float)}

    objective = SimpleNamespace(initial=np.zeros(4), base=Base())
    fitted = {
        "vector": [1.0, 2.0, 3.0],
        "parameters": [1.0, 2.0, 3.0],
        "rf_coefficient_hz_per_ghz": [456.0],
    }
    actual = calibrated_current_vector(objective, fitted)
    np.testing.assert_array_equal(actual, [1.0, 2.0, 3.0, 456.0])
