from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import legacy_timing10_fit as timing
import numpy as np
import pytest
from joint_inputs import (
    FRAME_LATITUDE_DEG,
    FRAME_LONGITUDE_DEG,
    JointData,
    _ecef,
    observation_nodes,
)


def synthetic_data(candidate_count=64):
    times = np.array([100.2, 100.2, 101.1, 102.4, 102.4, 103.3])
    nodes = observation_nodes(times)
    numbers = np.arange(candidate_count, dtype=np.int64) + 50000
    observer = _ecef(FRAME_LATITUDE_DEG, FRAME_LONGITUDE_DEG)
    up = observer / np.linalg.norm(observer)
    longitude = np.deg2rad(FRAME_LONGITUDE_DEG)
    east = np.array([-np.sin(longitude), np.cos(longitude), 0.0])
    north = np.cross(up, east)
    position = np.empty((candidate_count, len(nodes), 3))
    velocity = np.empty_like(position)
    for satellite in range(candidate_count):
        speed = 6.5 + 0.01 * satellite
        direction = np.cos(0.03 * satellite) * east + np.sin(0.03 * satellite) * north
        velocity[satellite] = speed * direction
        position[satellite] = (
            observer
            + (550.0 + satellite) * up
            + (satellite - candidate_count / 2) * 3.0 * east
            + nodes[:, None] * velocity[satellite]
        )
    initial = np.zeros(6 + candidate_count)
    initial[:6] = [2.0, -1.0, 130.0, 0.35, -90.0, -0.22]
    arrays = {
        "times": times,
        "measured": np.zeros(len(times)),
        "rf": np.array([11.0e9, 11.0e9, 11.2e9, 11.4e9, 11.4e9, 11.3e9]),
        "receiver": np.array([0, 0, 1, 0, 0, 1], dtype=np.int64),
        "channel": np.ones(len(times), dtype=np.int64),
        "group": np.array([0, 0, 1, 2, 2, 3], dtype=np.int64),
        "margin": np.ones(len(times)),
    }
    data = JointData(
        dataset="synthetic",
        unit_id="synthetic",
        child_sessions=("child",),
        child_origins_utc_ns=np.array([1_000_000_000_000], dtype=np.int64),
        origin_utc_ns=1_000_000_000_000,
        reference_time_s=101.75,
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
    truth = initial.copy()
    truth[:2] = [5.0, -4.0]
    truth[6:] = np.linspace(-0.6, 0.6, candidate_count)
    predicted, visible = data.predict(truth)
    targets = np.array([3, 9, 17, 25, 31, 47]) % candidate_count
    assert np.all(visible[np.arange(len(times)), targets])
    data.measured[:] = predicted[np.arange(len(times)), targets] + np.array(
        [35.0, -20.0, 80.0, -110.0, 55.0, 140.0]
    )
    return data, initial


def load_old_models():
    root = Path(__file__).resolve().parent.parent / "2026_10_02_localization_benchmark"
    spec = importlib.util.spec_from_file_location("legacy_timing10_old_models", root / "models.py")
    if spec is None or spec.loader is None:
        raise ImportError("cannot load historical models.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(root))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def successful_result(vector, value):
    return SimpleNamespace(
        x=np.asarray(vector).copy(),
        fun=float(value),
        success=True,
        status=0,
        message="synthetic convergence",
        nit=1,
        nfev=1,
    )


def test_objective_and_gradient_match_historical_timing_objective_for_64_candidates():
    data, initial = synthetic_data(64)
    vector = np.r_[np.array([4.5, -3.2]), np.linspace(-0.4, 0.5, 64)]
    new = timing.LegacyTimingObjective(data, initial, clock=lambda: 0.0)
    old_models = load_old_models()
    context = SimpleNamespace(
        data=data,
        arrays={"measured": data.measured, "group": data.group},
    )
    old = old_models._TimingObjective(
        context, initial, 10.0 / 3.0, 10.0, float("inf")
    )
    new_value, new_gradient = new.evaluate(vector)
    old_value, old_gradient = old.evaluate(vector)
    assert new_value == pytest.approx(old_value, rel=0.0, abs=2e-12)
    np.testing.assert_array_equal(new.last["rows"], old.last["rows"])
    np.testing.assert_array_equal(new.last["satellites"], old.last["satellites"])
    np.testing.assert_allclose(new.last["errors"], old.last["errors"], atol=2e-10)
    np.testing.assert_allclose(new_gradient, old_gradient, rtol=3e-5, atol=2e-7)


def test_dynamic_union_bank_is_not_silently_truncated_to_64():
    data, initial = synthetic_data(70)
    seen = {}

    def minimizer(function, vector, **options):
        seen["bounds"] = options["bounds"]
        value, _ = function(vector)
        return successful_result(vector, value)

    result = timing.fit_legacy_timing10(
        data, initial, minimizer=minimizer, clock=lambda: 0.0
    )
    assert result["satellite_count"] == 70
    assert len(result["parameters"]) == 76
    np.testing.assert_array_equal(result["satellite_indices"], np.arange(70))
    assert len(seen["bounds"]) == 72
    assert result["candidate_scope"].startswith("explicit supplied candidate bank")


def test_rx_lines_remain_fixed_and_optimizer_bounds_are_historical():
    data, initial = synthetic_data(64)
    observed = {}
    objective = timing.LegacyTimingObjective(data, initial, clock=lambda: 0.0)
    boundary_parameters = objective.parameters(
        np.r_[np.array([200.0, -200.0]), np.full(64, 10.0)]
    )
    np.testing.assert_array_equal(boundary_parameters[2:6], initial[2:6])
    np.testing.assert_array_equal(boundary_parameters[6:], np.full(64, 10.0))

    def minimizer(function, vector, **options):
        observed.update(options)
        terminal = vector.copy()
        terminal[:2] = [200.0, -200.0]
        terminal[2:] = 10.0
        value, _ = function(terminal)
        return successful_result(terminal, value)

    result = timing.fit_legacy_timing10(
        data, initial, minimizer=minimizer, clock=lambda: 0.0
    )
    assert observed["method"] == "L-BFGS-B"
    assert observed["bounds"][:2] == [(-200.0, 200.0)] * 2
    assert observed["bounds"][2:] == [(-10.0, 10.0)] * 64
    np.testing.assert_array_equal(result["parameters"][2:6], initial[2:6])
    assert np.all(np.abs(result["parameters"][6:]) <= 10.0)
    assert result["historical_pipeline_exact"] is False


def test_fixed_rx_slope_outside_old_drift_bound_is_rejected():
    data, initial = synthetic_data(64)
    initial[3] = 50.0001
    with pytest.raises(ValueError, match="fixed RX slope"):
        timing.LegacyTimingObjective(data, initial)


def test_deadline_stops_optimizer_and_preserves_best_finite_incumbent():
    data, initial = synthetic_data(64)

    class Clock:
        value = 0.0

        def __call__(self):
            return self.value

    clock = Clock()
    evaluated = []

    def minimizer(function, vector, callback, bounds, **options):
        value, gradient = function(vector)
        evaluated.append(value)
        for scale in (1e-4, 5e-4, 1e-3):
            candidate = np.clip(vector - scale * gradient, *np.asarray(bounds).T)
            candidate_value, _ = function(candidate)
            evaluated.append(candidate_value)
        clock.value = 61.0
        callback(vector)
        raise AssertionError("deadline callback must stop the optimizer")

    result = timing.fit_legacy_timing10(
        data,
        initial,
        budget_s=60.0,
        minimizer=minimizer,
        clock=clock,
    )
    assert result["success"] is False
    assert result["status"] == "limit_reached"
    assert result["best_finite_preserved"] is True
    assert result["optimizer_objective"] == pytest.approx(min(evaluated))


def test_successful_optimizer_with_different_retained_best_is_not_converged():
    data, initial = synthetic_data(64)
    retained = {}

    def minimizer(function, vector, bounds, **options):
        terminal_value, gradient = function(vector)
        candidates = []
        lower, upper = np.asarray(bounds).T
        for scale in (1e-4, 5e-4, 1e-3):
            candidate = np.clip(vector - scale * gradient, lower, upper)
            value, _ = function(candidate)
            candidates.append((value, candidate))
        best_value, best_vector = min(candidates, key=lambda row: row[0])
        assert best_value < terminal_value
        retained["vector"] = best_vector
        return successful_result(vector, terminal_value)

    result = timing.fit_legacy_timing10(
        data, initial, minimizer=minimizer, clock=lambda: 0.0
    )
    assert result["optimizer_reported_success"] is True
    assert result["optimizer_reported_status"] == 0
    assert result["best_matches_optimizer_terminal"] is False
    assert result["success"] is False
    assert result["status"] == "best_retained_nonterminal"
    np.testing.assert_allclose(
        result["parameters"][:2], retained["vector"][:2], rtol=0.0, atol=0.0
    )
    np.testing.assert_allclose(
        result["parameters"][6:], retained["vector"][2:], rtol=0.0, atol=0.0
    )


def test_standard_trial_fields_and_single_zero_tau_start():
    data, initial = synthetic_data(64)
    starts = []

    def minimizer(function, vector, **options):
        starts.append(vector.copy())
        value, _ = function(vector)
        return successful_result(vector, value)

    result = timing.fit_legacy_timing10(
        data, initial, minimizer=minimizer, clock=lambda: 0.0
    )
    np.testing.assert_array_equal(starts[0][:2], initial[:2])
    np.testing.assert_array_equal(starts[0][2:], np.zeros(64))
    assert {
        "parameters",
        "satellite_indices",
        "objective",
        "selection_score",
        "status",
        "success",
        "convergence_reason",
        "model_penalty",
        "assigned_groups",
    } <= result.keys()
    assert result["success"] is True
    assert result["rx_policy"].endswith("fixed throughout optimization")


def test_assignment_ties_are_deterministic_and_unmatched_loss_is_capped():
    residual = np.array([[5.0, 5.0], [5.0, 2.0], [np.inf, np.inf]])
    visible = np.isfinite(residual)
    rows, satellites, errors = timing.best_group_assignments(
        residual, visible, np.array([4, 4, 9])
    )
    np.testing.assert_array_equal(rows, [1, 2])
    np.testing.assert_array_equal(satellites, [1, 0])
    np.testing.assert_array_equal(errors, [2.0, np.inf])
    assert timing.capped_pseudo_huber(np.inf) == pytest.approx(
        timing.capped_pseudo_huber(2000.0)
    )
