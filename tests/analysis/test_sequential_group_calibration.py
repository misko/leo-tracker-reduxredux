from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.channel_group_calibration import GroupCalibrationObjective, fit_group_calibration
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.low_informed_joint_seed import low_informed_joint_seed
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.analysis.sequential_group_calibration import (
    SequentialHighObjective,
    SequentialShift,
    fit_sequential_path,
    fixed_shift_objective,
    freeze_sequential_calibration,
    physical_shift_seed,
)
from leo.contracts.regional_position import POSITION_SCORES, PositionObservations, RegionalPrior


def model(monkeypatch, channels, *, measurements=None):
    import leo.analysis.hard60_score as score

    n = len(channels)
    rx = np.arange(n) % 2
    times = np.linspace(0, 150, n)
    observations = PositionObservations(
        tuple(map(str, range(n))), times,
        np.zeros(n) if measurements is None else measurements,
        10.5e9 + np.asarray(channels) * 250e6,
        rx, np.asarray(channels), np.ones(n),
    )

    def predictor(bank, obs, prior, point, shifts, **kwargs):
        prediction = np.broadcast_to(
            np.arange(len(bank.numbers))[None, :] * 1000.0, (len(obs.times_s), len(bank.numbers))
        ).copy()
        spatial = np.broadcast_to(np.array([0.3, -0.2]), (*prediction.shape, 2))
        timing = np.full(prediction.shape, 2.0)
        return prediction + spatial @ point + timing * shifts, np.ones(
            prediction.shape, bool
        ), spatial, timing

    monkeypatch.setattr(score, "predict_orbits", predictor)
    monkeypatch.setattr("leo.analysis.hard60_joint_clock.predict_orbits", predictor)
    monkeypatch.setattr("leo.analysis.sequential_group_calibration.predict_orbits", predictor)
    bank = SimpleNamespace(numbers=np.arange(1001, 1004), nodes_s=np.arange(-40.0, 201.0, 10.0))
    return Hard60Objective(observations, bank, RegionalPrior(), POSITION_SCORES["V16"])


def freeze_low(base):
    low = GroupCalibrationObjective(base, base.observations.channel >= 5, enabled=False)
    vector = np.zeros(base.size)
    vector[2:7] = [-80000, 2, -54000, 1.5, -600]
    return freeze_group_calibration(low, dict(vector=vector, nuisance=np.empty(0)))


def test_high_locks_full_low_function_and_geometry_but_fits_timing_and_offsets(monkeypatch):
    low = model(monkeypatch, np.tile(np.arange(1, 5), 32))
    frozen = freeze_low(low)
    high = model(monkeypatch, np.tile(np.arange(5, 9), 32))
    stage = SequentialHighObjective(high, frozen, {0, 1})
    vector = np.zeros(high.size)
    vector[:2] = [1.0, 2.0]
    offsets = np.array([-24000.0, 38000.0])
    expected = frozen.predict(
        high.observations.times_s, high.observations.rf_hz,
        high.observations.receiver, high.observations.channel >= 5,
    ) + offsets[high.observations.receiver]
    np.testing.assert_allclose(stage.correction(vector, offsets), expected)
    vector[2:7] = [1e6, 5, -1e6, -5, 3000]
    np.testing.assert_allclose(stage.correction(vector, offsets), expected)
    _, gradient, extra, _ = stage.evaluate_joint(vector, offsets)
    np.testing.assert_array_equal(gradient[2:7], 0)
    for i in range(2):
        delta = np.eye(2)[i] * 1e-4
        numeric = (
            stage.evaluate_joint(vector, offsets + delta)[0]
            - stage.evaluate_joint(vector, offsets - delta)[0]
        ) / 2e-4
        np.testing.assert_allclose(extra[i], numeric, atol=1e-6)


def test_high_cannot_infer_a_shift_without_low_receiver_support(monkeypatch):
    low = model(monkeypatch, np.tile(np.arange(1, 5), 8))
    high = model(monkeypatch, np.tile(np.arange(5, 9), 8))
    with pytest.raises(ValueError, match="lacks low-stage"):
        SequentialHighObjective(high, freeze_low(low), {0})
    with pytest.raises(ValueError, match="no learned"):
        SequentialShift((0,), np.array([12.0])).predict(np.array([1]), np.array([True]))


def test_final_shift_is_fixed_and_frozen_prediction_closes_at_original_centres(monkeypatch):
    base = model(monkeypatch, np.tile(np.arange(1, 9), 8))
    shift = SequentialShift((0, 1), np.array([-24000.0, 38000.0]))
    final = fixed_shift_objective(base, shift)
    assert final.group_count == 0 and final.initial_nuisance.size == 0
    vector = np.zeros(base.size)
    vector[2:7] = [-80000, 2, -54000, 1.5, -600]
    frozen = freeze_sequential_calibration(final, dict(vector=vector, nuisance=np.empty(0)), shift)
    obs = base.observations
    np.testing.assert_allclose(
        frozen.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5),
        final.correction(vector, np.empty(0)), atol=1e-8,
    )
    # Shift remains physical high-minus-low, regardless of training fractions or c.
    for receiver in (0, 1):
        args = (np.array([43.0, 43.0]), np.array([11.7e9, 11.7e9]),
                np.array([receiver, receiver]), np.array([False, True]))
        np.testing.assert_allclose(np.diff(frozen.predict(*args)), shift.offsets_hz[receiver])
    with pytest.raises(ValueError):
        shift.offsets_hz[0] = 0


def test_seed_compares_physical_functions_and_handles_alias_gauge(monkeypatch):
    low = model(monkeypatch, np.tile(np.arange(1, 5), 8))
    high = model(monkeypatch, np.tile(np.arange(5, 9), 8))
    low_state = freeze_low(low)
    # Change centres and intercepts in a gauge that preserves the same function.
    time_shift, rf_shift = 17.0, 0.7e9
    coefficients = low_state.receiver_rf_coefficients.copy()
    coefficients[[0, 2]] += coefficients[[1, 3]] * time_shift + coefficients[4] * rf_shift / 1e9
    coefficients[[0, 2]] += [ALIAS_HZ + 500.0, -ALIAS_HZ - 900.0]
    high_state = replace(
        low_state, time_center_s=low_state.time_center_s + time_shift,
        rf_center_hz=low_state.rf_center_hz + rf_shift,
        receiver_rf_coefficients=coefficients,
    )
    np.testing.assert_allclose(
        physical_shift_seed(high_state, low_state, high.observations, (0, 1)),
        [500.0, -900.0], atol=1e-8,
    )


def test_smooth_common_clock_is_locked_in_high_and_transported_once_in_final(monkeypatch):
    base = model(monkeypatch, np.tile(np.arange(1, 9), 8))
    nodes = np.arange(0.0, 151.0, 30.0)
    clock = JointClockObjective(base, nodes, np.zeros((2, len(nodes))), 4)
    common = GroupCalibrationObjective(clock, base.observations.channel >= 5, enabled=False)
    vector = np.zeros(base.size)
    vector[2:7] = [-80000, 2, -54000, 1.5, -600]
    nuisance = np.linspace(-30, 40, common.clock_count)
    frozen_common = freeze_group_calibration(common, dict(vector=vector, nuisance=nuisance))
    high = model(monkeypatch, np.tile(np.arange(5, 9), 8))
    stage = SequentialHighObjective(high, frozen_common, {0, 1})
    offsets = np.array([-500.0, 800.0])
    high_obs = high.observations
    np.testing.assert_allclose(
        stage.correction(np.zeros(base.size), offsets),
        frozen_common.predict(high_obs.times_s, high_obs.rf_hz,
                              high_obs.receiver, high_obs.channel >= 5)
        + offsets[high_obs.receiver], atol=1e-8,
    )
    shift = SequentialShift((0, 1), offsets)
    final = fixed_shift_objective(clock, shift)
    frozen = freeze_sequential_calibration(final, dict(vector=vector, nuisance=nuisance), shift)
    obs = base.observations
    np.testing.assert_allclose(
        frozen.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5),
        frozen_common.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5)
        + shift.predict(obs.receiver, obs.channel >= 5), atol=1e-8,
    )


def test_matched_c_arms_and_stationary_sequential_path(monkeypatch):
    low_base = model(monkeypatch, np.tile(np.arange(1, 5), 32))
    high_base = model(monkeypatch, np.tile(np.arange(5, 9), 32))
    all_base = model(monkeypatch, np.tile(np.arange(1, 9), 32))
    shift = SequentialShift((0, 1), np.array([-24000.0, 38000.0]))
    vector = np.zeros(low_base.size)
    vector[2:7] = [-80000, 2, -54000, 1.5, -600]
    frozen = freeze_low(low_base)
    bases = []
    for base in (low_base, high_base, all_base):
        obs = base.observations
        measured = frozen.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5)
        measured += shift.predict(obs.receiver, obs.channel >= 5)
        bases.append(
            Hard60Objective(replace(obs, measured_hz=measured), base.bank, base.prior, base.score)
        )
    low = GroupCalibrationObjective(bases[0], bases[0].observations.channel >= 5, enabled=False)
    result = fit_sequential_path(
        low, bases[1], bases[2], vector, vector, vector,
        high_shift_seed=shift.offsets_hz, seconds=10, iterations=600,
        local_center=np.zeros(2), local_radius_km=1,
    )
    assert result["status"] == "complete"
    np.testing.assert_allclose(result["shift"].offsets_hz, shift.offsets_hz, atol=2)
    np.testing.assert_array_equal(result["high"]["vector"][2:7], 0)
    # Constant timing derivatives expose the exact local frequency degeneracy.
    diagnostics = result["high"]["offset_timing_diagnostic"]
    assert 0 < diagnostics["rx0"]["timing_explained_offset_fraction"] <= 1
    zero = fit_group_calibration(
        result["final_model"], result["final"]["vector"], result["final"]["nuisance"],
        arm="zero-c", fixed_position=True, seconds=10, iterations=600,
    )
    assert zero["vector"][6] == 0
    assert zero["posterior_rms_hz"] > result["final"]["posterior_rms_hz"]


@pytest.mark.parametrize("arm", ["fitted-c", "zero-c"])
def test_low_informed_seed_transports_clock_contrast_and_satellite_identity(monkeypatch, arm):
    nodes = np.arange(0.0, 151.0, 30.0)
    low_base = model(monkeypatch, np.tile(np.arange(1, 5), 16))
    low = GroupCalibrationObjective(
        JointClockObjective(low_base, nodes, np.zeros((2, len(nodes))), 4),
        low_base.observations.channel >= 5, enabled=False,
    )
    vector = np.zeros(low.size)
    vector[:2], vector[2:7] = [1, 2], [-80000, 2, -54000, 1.5, -600]
    if arm == "zero-c":
        vector[6] = 0
    timing = np.array([0.3, -0.2, 0.8])
    vector[7], vector[8:] = timing.mean(), low.basis.T @ (timing - timing.mean())
    fit = dict(vector=vector, nuisance=np.linspace(-10, 20, low.clock_count), converged=True)
    frozen = freeze_group_calibration(low, fit)
    high_state = replace(
        frozen, receiver_rf_coefficients=frozen.receiver_rf_coefficients + [500, 0, -900, 0, 0]
    )
    high = model(monkeypatch, np.tile(np.arange(5, 9), 16))
    all_base = model(monkeypatch, np.tile(np.arange(1, 9), 16))
    all_base.bank.numbers = all_base.bank.numbers[::-1]
    target = GroupCalibrationObjective(
        JointClockObjective(all_base, nodes, np.zeros((2, len(nodes))), 4),
        all_base.observations.channel >= 5,
    )
    seed = low_informed_joint_seed(low, fit, high_state, high.observations, target, arm=arm)
    obs = target.observations
    expected = frozen.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5)
    expected += (obs.channel >= 5) * np.array([500, -900])[obs.receiver]
    np.testing.assert_allclose(target.correction(seed["vector"], seed["nuisance"]), expected,
                               atol=1e-6)
    np.testing.assert_allclose(
        seed["vector"][7] + target.basis @ seed["vector"][8:], timing[::-1], atol=1e-12
    )
    assert seed["initializer"]["projection_maximum_abs_hz"] < 1e-6
    assert not seed["initializer"]["low_used_as_prior"]
    assert not seed["initializer"]["low_covariance_used"]
    if arm == "zero-c":
        assert seed["vector"][6] == 0
    with pytest.raises(ValueError, match="stationary own-arm"):
        low_informed_joint_seed(low, dict(fit, converged=False), high_state,
                               high.observations, target, arm=arm)
    if arm == "fitted-c":
        with pytest.raises(ValueError, match="own exact zero-c"):
            low_informed_joint_seed(low, fit, high_state, high.observations, target, arm="zero-c")


def test_joint_contrast_likelihood_and_priors_are_counted_once(monkeypatch):
    base = model(monkeypatch, np.tile(np.arange(1, 9), 16))
    nodes = np.arange(0.0, 151.0, 30.0)
    target = GroupCalibrationObjective(
        JointClockObjective(base, nodes, np.zeros((2, len(nodes))), 4),
        base.observations.channel >= 5,
    )
    vector = np.zeros(target.size)
    vector[7:] = [0.2, -0.1, 0.3]
    nuisance = np.r_[np.linspace(-10, 20, target.clock_count), [500.0, -900.0]]
    value, gradient, extra, terms = target.evaluate_joint(vector, nuisance)
    clock, group = target.split(nuisance)
    relative = target.basis @ vector[8:]
    timing_prior = 0.5 * (vector[7] / target.score.common_sigma_s)**2
    timing_prior += 0.5 * np.sum((relative / target.score.relative_sigma_s)**2)
    priors = timing_prior + 0.5 * clock @ target.base.precision @ clock
    priors += 0.5 * group @ target.group_precision @ group
    import leo.analysis.hard60_score as score

    predictions, visible, _, _ = score.predict_orbits(
        target.bank, target.observations, target.prior, vector[:2], vector[7] + relative
    )
    predictions += target.correction(vector, nuisance)[:, None]
    total = 0.0
    for high in (False, True):
        mask = (target.observations.channel >= 5) == high
        total += score.likelihood(target.observations.measured_hz[mask], predictions[mask],
                                  visible[mask], target.score).nll
    np.testing.assert_allclose(value, total + priors, atol=1e-10)
    for index, actual in ((6, gradient[6]), (len(vector), extra[0]),
                          (len(vector) + target.clock_count, extra[target.clock_count])):
        state = np.r_[vector, nuisance]
        direction = np.eye(len(state))[index] * 1e-4
        left, right = state - direction, state + direction
        numeric = (target.evaluate_joint(right[:len(vector)], right[len(vector):])[0]
                   - target.evaluate_joint(left[:len(vector)], left[len(vector):])[0]) / 2e-4
        np.testing.assert_allclose(actual, numeric, atol=1e-6)
