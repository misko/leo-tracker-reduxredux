from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.channel_group_calibration import (
    GroupCalibrationFrame,
    GroupCalibrationObjective,
    fit_group_calibration,
    group_frame,
    project_calibration_seed,
)
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.regional_position_score import ALIAS_HZ, circular
from leo.contracts.regional_position import POSITION_SCORES, PositionObservations


def base(monkeypatch, *, count=32):
    import leo.analysis.hard60_score as score_module

    rx = np.arange(count) % 2
    channel = 1 + (np.arange(count) // 2) % 8
    times = np.linspace(0, 150, count)
    observations = PositionObservations(
        tuple(map(str, range(count))),
        times,
        np.linspace(0, 30, count),
        10.5e9 + channel * 250e6,
        rx,
        channel,
        np.ones(count),
    )

    def predictor(bank, obs, prior, point, shifts, **kwargs):
        k = len(bank.numbers)
        prediction = np.broadcast_to(np.arange(k)[None, :] * 1000.0, (len(obs.times_s), k)).copy()
        spatial = np.broadcast_to(np.array([0.3, -0.2]), (len(obs.times_s), k, 2))
        timing = np.full((len(obs.times_s), k), 2.0)
        prediction += spatial @ point + timing * shifts
        return prediction, np.ones(prediction.shape, bool), spatial, timing

    monkeypatch.setattr(score_module, "predict_orbits", predictor)
    bank = SimpleNamespace(numbers=np.arange(1001, 1004), nodes_s=np.arange(-40.0, 201.0, 10.0))
    prior = SimpleNamespace(radius_km=250.0)
    return Hard60Objective(observations, bank, prior, POSITION_SCORES["V16"])


def test_group_terms_nest_original_model_without_mutating_observations(monkeypatch):
    original = base(monkeypatch)
    model = GroupCalibrationObjective(original, original.observations.channel >= 5)
    vector = np.zeros(model.size)
    vector[2:7] = [5, 0.1, -3, -0.2, 10]
    expected = original.evaluate(vector)
    actual = model.evaluate_joint(vector, np.zeros(model.group_count))
    assert model.size == original.size and model.observations is original.observations
    np.testing.assert_allclose(actual[0], expected[0], atol=1e-10)
    np.testing.assert_allclose(actual[1], expected[1], atol=1e-10)
    np.testing.assert_array_equal(actual[3].responsibilities, expected[2].responsibilities)
    np.testing.assert_allclose(model.group_design.sum(axis=0), 0, atol=1e-14)


def test_joint_group_derivative_and_prior_are_correct(monkeypatch):
    original = base(monkeypatch)
    model = GroupCalibrationObjective(original, original.observations.channel >= 5)
    v = np.zeros(model.size)
    v[2:7] = [5, 0.1, -3, -0.2, 10]
    n = np.array([150.0, -70.0])
    _, g, extra, _ = model.evaluate_joint(v, n)
    state = np.r_[v, n]
    numeric = []
    for i in range(len(state)):
        delta = np.zeros_like(state)
        delta[i] = 1e-4
        a, b = state + delta, state - delta
        numeric.append(
            (
                model.evaluate_joint(a[: model.size], a[model.size :])[0]
                - model.evaluate_joint(b[: model.size], b[model.size :])[0]
            )
            / 2e-4
        )
    np.testing.assert_allclose(np.r_[g, extra], numeric, atol=3e-7, rtol=2e-5)


def test_carried_offsets_are_restored_once_in_a_new_objective(monkeypatch):
    original = base(monkeypatch)
    model = GroupCalibrationObjective(original, original.observations.channel >= 5)
    gamma = np.array([-24000.0, 38000.0])
    vector = np.zeros(model.size)
    baseline = model.correction(vector, gamma)
    frozen = Hard60Objective(
        original.observations,
        original.bank,
        original.prior,
        original.score,
        receiver_baseline_hz=baseline,
    )
    restored = GroupCalibrationObjective(
        frozen, original.observations.channel >= 5, carried_group_hz=gamma
    )
    np.testing.assert_allclose(restored.correction(vector, restored.initial_nuisance), baseline)
    np.testing.assert_array_equal(original.baseline, np.zeros(len(original.baseline)))


def test_prediction_preserves_training_centering_without_held_recenter():
    rx = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    high = np.array([0, 0, 0, 1, 0, 1, 1, 1], bool)
    frame = group_frame(rx, high)
    assert frame.high_fractions == (0.25, 0.75)
    held_rx = np.array([0, 1])
    held_high = np.array([True, True])
    np.testing.assert_array_equal(frame.design(held_rx, held_high), [[0.75, 0], [0, 0.25]])
    # Recomputing on this held-only view would erase both identifiable offsets.
    assert group_frame(held_rx, held_high).receivers == ()


def test_joint_clock_and_group_gradient_and_restoration(monkeypatch):
    import leo.analysis.hard60_joint_clock as clock_module
    import leo.analysis.hard60_score as score_module

    original = base(monkeypatch)
    monkeypatch.setattr(clock_module, "predict_orbits", score_module.predict_orbits)
    nodes = np.arange(0.0, 151.0, 30.0)
    clock = clock_module.JointClockObjective(original, nodes, np.zeros((2, len(nodes))), 4)
    model = GroupCalibrationObjective(clock, original.observations.channel >= 5)
    vector = np.zeros(model.size)
    vector[2:7] = [5, 0.1, -3, -0.2, 10]
    nuisance = np.r_[np.linspace(-10, 10, model.clock_count), [120.0, -80.0]]
    _, _, gradient, _ = model.evaluate_joint(vector, nuisance)
    numerical = []
    for i in range(len(nuisance)):
        delta = np.zeros_like(nuisance)
        delta[i] = 1e-4
        numerical.append(
            (
                model.evaluate_joint(vector, nuisance + delta)[0]
                - model.evaluate_joint(vector, nuisance - delta)[0]
            )
            / 2e-4
        )
    np.testing.assert_allclose(gradient, numerical, atol=3e-7, rtol=2e-5)


def test_group_drift_derivative_prior_and_units(monkeypatch):
    original = base(monkeypatch)
    model = GroupCalibrationObjective(
        original, original.observations.channel >= 5, group_drift_sigma_hz_s=2.0
    )
    vector = np.zeros(model.size)
    nuisance = np.array([100.0, -150.0, 0.2, -0.3])
    value, _, gradient, _ = model.evaluate_joint(vector, nuisance)
    numeric = []
    for i in range(4):
        d = np.zeros(4)
        d[i] = 1e-5
        numeric.append(
            (
                model.evaluate_joint(vector, nuisance + d)[0]
                - model.evaluate_joint(vector, nuisance - d)[0]
            )
            / 2e-5
        )
    np.testing.assert_allclose(gradient, numeric, atol=1e-6, rtol=2e-5)
    assert model.group_limits.tolist() == [ALIAS_HZ / 2, ALIAS_HZ / 2, 60.0, 60.0]
    assert np.isfinite(value)
    with pytest.raises(ValueError):
        GroupCalibrationObjective(
            original, original.observations.channel >= 5, group_drift_sigma_hz_s=0
        )


def test_carried_calibration_projection_respects_actual_fitter_bounds(monkeypatch):
    import leo.analysis.hard60_joint_clock as clock_module

    original = base(monkeypatch, count=128)
    nodes = np.arange(0.0, 151.0, 30.0)
    clock = clock_module.JointClockObjective(original, nodes, np.zeros((2, len(nodes))), 4)
    model = GroupCalibrationObjective(clock, original.observations.channel >= 5)
    vector = np.zeros(model.size)
    vector[2:7] = [-80000.0, 2.0, -54000.0, 1.5, -600.0]
    nuisance = np.r_[np.full(model.clock_count, 2400.0), [-24000.0, 38000.0]]
    target = model.correction(vector, nuisance)
    seed = project_calibration_seed(model, target)
    coefficients = seed["coefficients"]
    assert np.max(abs(coefficients[5 : 5 + model.clock_count])) <= 2000.0 + 1e-7
    assert np.max(abs(coefficients[5 + model.clock_count :])) <= ALIAS_HZ / 2
    assert np.isfinite(seed["rms_hz"])
    assert seed["active_bounds"]


def test_partial_and_single_group_support_remain_explicit():
    rx = np.array([0, 0, 1, 1])
    high = np.array([0, 0, 0, 1], bool)
    frame = group_frame(rx, high)
    assert frame.receivers == (1,)
    np.testing.assert_array_equal(frame.design(rx, high), [[0], [0], [-0.5], [0.5]])
    assert group_frame(rx, np.zeros(4, bool)).receivers == ()
    with pytest.raises(ValueError):
        GroupCalibrationFrame((0,), (0.0,))


def test_differential_clock_gradient_and_physical_prior(monkeypatch):
    import leo.analysis.hard60_joint_clock as clock_module
    import leo.analysis.hard60_score as score_module

    original = base(monkeypatch)
    monkeypatch.setattr(clock_module, "predict_orbits", score_module.predict_orbits)
    nodes = np.arange(0.0, 151.0, 30.0)
    clock = clock_module.JointClockObjective(original, nodes, np.zeros((2, len(nodes))), 4)
    model = GroupCalibrationObjective(
        clock, original.observations.channel >= 5, group_drift_sigma_hz_s=2, group_clock=True
    )
    assert model.group_clock_count == model.clock_count
    np.testing.assert_array_equal(
        model.group_precision[-model.clock_count :, -model.clock_count :], clock.precision
    )
    vector = np.zeros(model.size)
    nuisance = np.r_[
        np.linspace(-10, 10, model.clock_count),
        [120.0, -80.0, 0.1, -0.2],
        np.linspace(-20, 20, model.group_clock_count),
    ]
    _, _, gradient, _ = model.evaluate_joint(vector, nuisance)
    for i in range(len(nuisance)):
        delta = np.zeros_like(nuisance)
        delta[i] = 1e-4
        numeric = (
            model.evaluate_joint(vector, nuisance + delta)[0]
            - model.evaluate_joint(vector, nuisance - delta)[0]
        ) / 2e-4
        np.testing.assert_allclose(gradient[i], numeric, atol=3e-7, rtol=2e-5)


def test_alias_equivalent_offsets_preserve_circular_physical_corrections(monkeypatch):
    original = base(monkeypatch)
    model = GroupCalibrationObjective(original, original.observations.channel >= 5)
    vector = np.zeros(model.size)
    gamma = np.array([-24000.0, 38000.0])
    first = model.correction(vector, gamma)
    shifted = gamma.copy()
    shifted[0] += ALIAS_HZ
    vector[2] += model.frame.high_fractions[0] * ALIAS_HZ
    np.testing.assert_allclose(circular(model.correction(vector, shifted) - first), 0, atol=1e-9)


def test_known_group_offsets_recovered_and_zero_c_locked(monkeypatch):
    original = base(monkeypatch, count=128)
    model = GroupCalibrationObjective(original, original.observations.channel >= 5)
    truth = np.zeros(model.size)
    truth[2:7] = [-80000, 2, -54000, 1.5, -600]
    gamma = np.array([-24000.0, 38000.0])
    measured = model.correction(truth, gamma)
    obs = replace(original.observations, measured_hz=measured)
    fitted_model = GroupCalibrationObjective(
        Hard60Objective(obs, original.bank, original.prior, original.score), obs.channel >= 5
    )
    seed = truth.copy()
    seed[2] += 40
    seed[4] -= 40
    seed[6] = 0
    result = fit_group_calibration(
        fitted_model,
        seed,
        gamma + np.array([100.0, -100.0]),
        fixed_position=True,
        seconds=10,
        iterations=600,
    )
    assert result["converged"]
    np.testing.assert_allclose(result["group_offsets_hz"], gamma, atol=2)
    assert abs(result["vector"][6] - truth[6]) < 2
    zero = fit_group_calibration(
        fitted_model,
        result["vector"],
        result["nuisance"],
        arm="zero-c",
        fixed_position=True,
        seconds=10,
        iterations=600,
    )
    assert zero["vector"][6] == 0
    assert zero["posterior_rms_hz"] > result["posterior_rms_hz"]
