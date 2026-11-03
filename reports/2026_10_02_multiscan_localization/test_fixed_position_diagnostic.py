from types import SimpleNamespace

import numpy as np
import scipy.optimize

import fixed_position_diagnostic
from test_staged_gradient import centered_difference, synthetic_orbital_data


def synthetic_sourcefit(parameters):
    satellites = np.array([0, 2])
    return {
        "fit": {
            "keep_track_identity": True,
            "anchors": [{"groups": np.array([7, 2])}],
            "score_leader": {
                "parameters": np.asarray(parameters).copy(),
                "satellite_indices": satellites,
                "objective": 123.0,
                "identity_masses": {
                    "raw_satellite_mass": np.array([0.4, 0.4]),
                    "raw_background_mass": 0.2,
                    "anchor_satellite_mass": np.array([[0.4, 0.4]]),
                    "anchor_unknown_mass": np.array([0.2]),
                },
            },
        }
    }


def test_fixed_position_is_immutable_and_nuisance_gradient_matches_centered_difference(
    monkeypatch,
):
    data, parameters = synthetic_orbital_data()
    sourcefit = synthetic_sourcefit(parameters)
    fixed_position = np.array([13.0, -9.0])
    original_prediction = fixed_position_diagnostic.paired_prediction_jacobian
    observed_positions = []

    def guarded_prediction(data, current, rows, satellites):
        observed_positions.append(np.asarray(current[:2]).copy())
        np.testing.assert_array_equal(current[:2], fixed_position)
        return original_prediction(data, current, rows, satellites)

    def intercept_minimize(function, vector, *, method, jac, bounds, options):
        assert method == "L-BFGS-B"
        assert jac is True
        assert len(vector) == 6
        probe = vector + np.array([0.012, -0.018, -0.015, 0.021, 0.04, -0.05])
        value, analytic = function(probe)
        steps = np.array([1e-4, 1e-5, 1e-4, 1e-5, 1e-4, 1e-4])
        numerical = centered_difference(function, probe, steps)
        np.testing.assert_allclose(analytic, numerical, rtol=7e-4, atol=4e-5)
        assert np.isfinite(value)
        return SimpleNamespace(
            x=probe,
            success=True,
            message="intercepted after gradient check",
            nit=0,
        )

    monkeypatch.setattr(
        fixed_position_diagnostic,
        "paired_prediction_jacobian",
        guarded_prediction,
    )
    monkeypatch.setattr(scipy.optimize, "minimize", intercept_minimize)
    result = fixed_position_diagnostic.fit_nuisance_at_position(
        data,
        sourcefit,
        fixed_position,
        budget_s=10.0,
    )

    assert observed_positions
    np.testing.assert_array_equal(result["position_km"], fixed_position)
    np.testing.assert_array_equal(result["parameters"][:2], fixed_position)
    assert result["position_fixed"] is True
    assert result["free_parameters"] == 6
    assert result["success"] is True
    assert result["source_leader_objective"] == 123.0
    omitted = np.setdiff1d(np.arange(len(data.numbers)), [0, 2])
    np.testing.assert_array_equal(result["parameters"][6 + omitted], 0.0)
