from types import SimpleNamespace

import numpy as np
import pytest
import scipy.optimize
from grouped_likelihood import prepare_grouped_likelihood
from joint_inputs import JointData, _coordinates, _ecef, observation_nodes
from staged_fit import refine_bank


class SyntheticOrbitalData(JointData):
    def __getattr__(self, name):
        if "truth" in name or name in {"known_site", "reference_coordinates"}:
            raise AssertionError(f"solver attempted to read forbidden {name}")
        raise AttributeError(name)


def synthetic_orbital_data():
    times = np.array([0.37, 2.13, 4.81, 6.42])
    nodes = observation_nodes(times)
    numbers = np.array([101, 202, 303], dtype=np.int64)
    latitude, longitude = np.deg2rad(_coordinates(np.zeros(2)))
    observer = _ecef(*np.rad2deg([latitude, longitude]))
    up = np.array(
        [
            np.cos(latitude) * np.cos(longitude),
            np.cos(latitude) * np.sin(longitude),
            np.sin(latitude),
        ]
    )
    east = np.array([-np.sin(longitude), np.cos(longitude), 0.0])
    north = np.array(
        [
            -np.sin(latitude) * np.cos(longitude),
            -np.sin(latitude) * np.sin(longitude),
            np.cos(latitude),
        ]
    )
    position = np.empty((len(numbers), len(nodes), 3))
    velocity = np.empty_like(position)
    for satellite in range(len(numbers)):
        base = (
            observer
            + (780.0 + 35.0 * satellite) * up
            + (90.0 * satellite - 70.0) * east
            + (25.0 * satellite - 20.0) * north
        )
        initial_velocity = (
            (6.5 + 0.15 * satellite) * east + (0.8 - 0.1 * satellite) * north + 0.03 * up
        )
        acceleration = 0.0015 * east - 0.0007 * north + 0.001 * up
        position[satellite] = (
            base + nodes[:, None] * initial_velocity + 0.5 * nodes[:, None] ** 2 * acceleration
        )
        velocity[satellite] = initial_velocity + nodes[:, None] * acceleration
    initial = np.array([8.0, -6.0, 120.0, 0.8, -90.0, -0.55, 0.12, -0.08, 0.18])
    arrays = {
        "times": times,
        "measured": np.zeros(len(times)),
        "rf": np.array([11.0e9, 11.15e9, 11.3e9, 11.05e9]),
        "receiver": np.array([0, 1, 0, 1], dtype=np.int64),
        "channel": np.ones(len(times), dtype=np.int64),
        "group": np.array([7, 2, 7, 9], dtype=np.int64),
        "margin": np.ones(len(times)),
    }
    data = SyntheticOrbitalData(
        dataset="synthetic",
        unit_id="synthetic-gradient",
        child_sessions=("synthetic-child",),
        child_origins_utc_ns=np.array([1_000_000_000_000], dtype=np.int64),
        origin_utc_ns=1_000_000_000_000,
        reference_time_s=3.0,
        snapshot={"provider": "synthetic", "collected_utc_ns": 1, "digest": "synthetic"},
        arrays=arrays,
        nodes=nodes,
        numbers=numbers,
        position=position,
        velocity=velocity,
        initial=initial,
        tracks=[],
        capture_index=np.zeros(len(times), dtype=np.int64),
        provenance={"reference_truth_read": False},
    )
    full_prediction, full_visible = data.predict(initial)
    assert np.all(full_visible[:, [0, 2]])
    data.measured = np.array(
        [
            full_prediction[0, 0] + 25.0,
            full_prediction[1, 2] - 40.0,
            full_prediction[2, 0] + 60.0,
            full_prediction[3, 2] - 35.0,
        ]
    )
    return data, initial


def centered_difference(objective_and_gradient, vector, steps):
    output = np.empty_like(vector)
    for index, step in enumerate(steps):
        lower = vector.copy()
        upper = vector.copy()
        lower[index] -= step
        upper[index] += step
        lower_value = objective_and_gradient(lower)[0]
        upper_value = objective_and_gradient(upper)[0]
        output[index] = (upper_value - lower_value) / (2 * step)
    return output


@pytest.mark.parametrize("share_predictions", [False, True])
def test_refine_bank_objective_gradient_matches_centered_difference(monkeypatch, share_predictions):
    data, initial = synthetic_orbital_data()
    satellites = np.array([0, 2])
    prepared = prepare_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=np.array([1.0, 0.5, 2.0, 1.5]),
    )
    checked = []

    def intercept_minimize(function, vector, *, method, jac, bounds, options):
        assert method == "L-BFGS-B"
        assert jac is True
        assert len(bounds) == len(vector)
        assert options["maxiter"] > 0
        perturbations = (
            np.array([0.08, -0.06, 0.013, -0.021, -0.017, 0.019, 0.025, -0.03]),
            np.array([-0.04, 0.07, -0.009, 0.016, 0.011, -0.014, -0.02, 0.035]),
        )
        steps = np.array([5e-5, 5e-5, 1e-4, 1e-5, 1e-4, 1e-5, 1e-4, 1e-4])
        final = None
        for perturbation in perturbations:
            probe = vector + perturbation
            value, analytic = function(probe)
            numerical = centered_difference(function, probe, steps)
            np.testing.assert_allclose(analytic, numerical, rtol=6e-4, atol=3e-5)
            assert np.isfinite(value)
            assert np.all(probe != 0)
            checked.append((analytic.copy(), numerical.copy()))
            final = probe
        return SimpleNamespace(
            x=final,
            success=True,
            message="intercepted after gradient checks",
            nit=0,
        )

    monkeypatch.setattr(scipy.optimize, "minimize", intercept_minimize)
    result = refine_bank(
        data,
        initial,
        satellites,
        np.array([9.0, 7.0]),
        prepared,
        sigma_hz=260.0,
        tau_sigma_s=0.7,
        budget_s=30.0,
        share_predictions=share_predictions,
    )

    assert len(checked) == 2
    assert result["success"]
    assert result["gradient_method"].startswith("Analytic likelihood")
    assert data.provenance == {"reference_truth_read": False}


class ConstantLikelihood:
    def evaluate(self, predicted, visible, **options):
        assert options["return_gradient"] is True
        satellite_count = predicted.shape[1]
        return {
            "total_log_likelihood": -17.0,
            "prediction_gradient": np.zeros_like(predicted),
            "group_values": np.arange(3),
            "satellite_support": np.zeros(satellite_count),
            "null_support": 3.0,
        }


def test_refine_bank_tau_prior_gradient_has_physical_sign_and_scaling(monkeypatch):
    data, initial = synthetic_orbital_data()
    satellites = np.array([0, 2])
    tau_sigma_s = 0.4
    scales = np.array([20.0, 20.0, 1000.0, 10.0, 1000.0, 10.0, 1.0, 1.0])

    def intercept_minimize(function, vector, **kwargs):
        probe = vector + np.array([0.03, -0.02, 0.01, -0.01, -0.02, 0.015, 0.05, -0.4])
        value, gradient = function(probe)
        physical = probe * scales
        expected = np.zeros_like(probe)
        expected[-2:] = physical[-2:] / tau_sigma_s**2
        np.testing.assert_allclose(gradient, expected, rtol=0.0, atol=1e-12)
        assert gradient[-2] > 0
        assert gradient[-1] < 0
        assert value == 17.0 + 0.5 * np.sum((physical[-2:] / tau_sigma_s) ** 2)
        numerical = centered_difference(
            function,
            probe,
            np.full(len(probe), 1e-5),
        )
        np.testing.assert_allclose(gradient, numerical, rtol=2e-8, atol=2e-8)
        return SimpleNamespace(
            x=probe,
            success=True,
            message="intercepted after prior check",
            nit=0,
        )

    monkeypatch.setattr(scipy.optimize, "minimize", intercept_minimize)
    result = refine_bank(
        data,
        initial,
        satellites,
        np.array([1.0, 1.0]),
        ConstantLikelihood(),
        tau_sigma_s=tau_sigma_s,
        budget_s=30.0,
    )

    assert result["success"]
    assert data.provenance["reference_truth_read"] is False
