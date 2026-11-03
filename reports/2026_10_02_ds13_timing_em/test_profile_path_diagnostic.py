from __future__ import annotations

import numpy as np
import pytest
from profile_path_diagnostic import (
    FRACTIONS,
    continue_profile,
    profile_positions,
    reported_status,
)


def test_profile_positions_are_exact_forward_quarters():
    actual = profile_positions([4.0, -8.0], [-4.0, 12.0])
    expected = np.array(
        [
            [4.0, -8.0],
            [2.0, -3.0],
            [0.0, 2.0],
            [-2.0, 7.0],
            [-4.0, 12.0],
        ]
    )
    np.testing.assert_array_equal(actual, expected)


def test_continuation_warm_starts_nuisance_and_fits_only_four_intervals():
    start = np.arange(9, dtype=float)
    known = np.array([10.0, -6.0])
    calls = []

    def fit_station(parameters, position):
        calls.append(parameters.copy())
        fitted = parameters.copy()
        fitted[2:] += 1.0
        return {
            "parameters": fitted,
            "status": "iteration_limit",
            "success": False,
            "elapsed_s": 3.0,
            "calls": 4,
            "best_is_terminal": True,
            "projected_gradient_inf_norm": 2.0,
            "newton_decrement": 1.0,
        }

    def evaluate_station(parameters):
        return {
            "objective": float(np.sum(parameters**2)),
            "data_objective": float(np.sum(parameters**2)),
            "prior_objective": 0.0,
            "free_position_gradient": parameters[:2].copy(),
            "parameters": parameters.copy(),
            "support": {"supported": len(parameters)},
        }

    stations = continue_profile(start, known, fit_station, evaluate_station)
    positions = profile_positions(start[:2], known)
    assert len(calls) == 4
    assert len(stations) == 5
    np.testing.assert_array_equal(stations[0]["parameters"], start)
    for index, call in enumerate(calls, start=1):
        np.testing.assert_array_equal(call[:2], positions[index])
        np.testing.assert_array_equal(call[2:], start[2:] + index - 1)
        np.testing.assert_array_equal(stations[index]["parameters"][2:], start[2:] + index)
        assert stations[index]["fraction"] == FRACTIONS[index]
    assert stations[0]["fit_calls"] == 0
    assert all(station["fit_calls"] == 4 for station in stations[1:])


def test_continuation_rejects_position_drift_from_fixed_plan():
    start = np.zeros(7)

    def drifting_fit(parameters, _position):
        parameters = parameters.copy()
        parameters[0] += 1.0e-12
        return {"parameters": parameters}

    with pytest.raises(ValueError, match="held exactly fixed"):
        continue_profile(start, [1.0, 1.0], drifting_fit, lambda _parameters: {})


def test_false_stationarity_status_is_normalized_for_summary_only():
    fitted = {"status": "projected_stationary_visibility_branch", "success": False}
    assert reported_status(fitted) == "best_finite_nonterminal_stationarity_unverified"
    assert fitted["status"] == "projected_stationary_visibility_branch"
    assert reported_status({"status": "iteration_limit", "success": False}) == (
        "iteration_limit"
    )


@pytest.mark.parametrize(
    "fractions",
    ([0.25, 1.0], [0.0, 0.5], [0.0, 0.5, 0.5, 1.0]),
)
def test_profile_positions_reject_invalid_fraction_contract(fractions):
    with pytest.raises(ValueError, match="zero to one"):
        profile_positions([0.0, 0.0], [1.0, 1.0], fractions)
