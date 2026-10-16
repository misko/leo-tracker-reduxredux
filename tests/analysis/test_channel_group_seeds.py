from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.channel_group_calibration import GroupCalibrationObjective
from leo.analysis.channel_group_seeds import (
    bootstrap_correction,
    declocked_training_observations,
    shared_bootstrap_seed,
)
from leo.analysis.hard60_score import Hard60Objective
from leo.contracts.regional_position import POSITION_SCORES, PositionObservations, RegionalPrior


def observations(channels):
    n = len(channels)
    return PositionObservations(
        tuple(map(str, range(n))),
        np.linspace(0, 150, n),
        np.zeros(n),
        10.5e9 + np.asarray(channels) * 250e6,
        np.arange(n) % 2,
        np.asarray(channels),
        np.ones(n),
    )


def test_seed_transport_keeps_training_time_rf_centers():
    train = observations([1, 1, 2, 2])
    target = observations([7, 8, 7, 8])
    bootstrap = SimpleNamespace(vector=np.r_[0.0, 0.0, 100.0, 2.0, 200.0, 3.0, -500.0, 0.0, 0.0])
    value = bootstrap_correction(bootstrap, train, target)
    expected = (
        np.array([100.0, 200.0, 100.0, 200.0])
        + np.array([2.0, 3.0, 2.0, 3.0]) * (target.times_s - train.time_center_s)
        - 500 * (target.rf_hz - train.rf_center_hz) / 1e9
    )
    np.testing.assert_allclose(value, expected)
    assert not np.allclose(value, bootstrap_correction(bootstrap, target, target))


def test_declocking_preserves_original_native_support_and_removes_only_calibration():
    original = observations([1, 2, 7, 8])
    calibration = np.array([100.0, 200.0, 300.0, 400.0])
    seen = []

    def predict(times, rf, receivers, high):
        seen.append((times, rf, receivers, high))
        return calibration

    corrected = declocked_training_observations(original, SimpleNamespace(predict=predict))
    np.testing.assert_array_equal(corrected.measured_hz, original.measured_hz - calibration)
    np.testing.assert_array_equal(original.measured_hz, np.zeros(4))
    for field in ("window_ids", "times_s", "rf_hz", "receiver", "channel", "margin"):
        np.testing.assert_array_equal(getattr(corrected, field), getattr(original, field))
    assert corrected.time_center_s == original.time_center_s
    assert corrected.rf_center_hz == original.rf_center_hz
    assert len(seen) == 1


def test_shared_seed_carries_union_timings_and_physical_band_offsets():
    full = observations([1, 1, 2, 2, 7, 7, 8, 8] * 4)
    low, high = observations([1, 1, 2, 2]), observations([7, 7, 8, 8])
    first = SimpleNamespace(
        satellite_indices=(0, 1), vector=np.r_[4.0, 5.0, 100.0, 2.0, 200.0, 3.0, 0.0, 1.0, 0.0]
    )
    second = SimpleNamespace(
        satellite_indices=(1, 2), vector=np.r_[4.0, 5.0, -23900.0, 2.0, 38200.0, 3.0, 0.0, 3.0, 0.0]
    )
    base = Hard60Objective(
        full,
        SimpleNamespace(numbers=np.array([1001, 1002, 1003])),
        RegionalPrior(),
        POSITION_SCORES["V16"],
    )
    model = GroupCalibrationObjective(base, full.channel >= 5)
    result = shared_bootstrap_seed(model, (0, 1, 2), {"low": (first, low), "high": (second, high)})
    physical = result["vector"][7] + model.basis @ result["vector"][8:]
    np.testing.assert_allclose(physical, [1.0, 2.0, 3.0])
    np.testing.assert_allclose(result["nuisance"], [-24000.0, 38000.0], atol=1e-6)
    assert result["projection"]["rms_hz"] < 1e-6
    second.vector[0] += 1
    with pytest.raises(ValueError, match="common discovery point"):
        shared_bootstrap_seed(model, (0, 1, 2), {"low": (first, low), "high": (second, high)})


def test_reassociated_seed_adds_old_clock_once_and_preserves_missing_training_timings():
    obs = observations([1, 1, 7, 7] * 4)
    base = Hard60Objective(
        obs,
        SimpleNamespace(numbers=np.array([1001, 1002, 1003])),
        RegionalPrior(),
        POSITION_SCORES["V16"],
    )
    model = GroupCalibrationObjective(base, obs.channel >= 5)
    proposal = SimpleNamespace(
        satellite_indices=(1, 2),
        vector=np.r_[4.0, 5.0, 10.0, 0.0, 20.0, 0.0, 0.0, 2.0, 0.0],
    )
    carried = SimpleNamespace(predict=lambda t, _f, rx, _h: np.where(rx == 0, 100.0, 200.0))
    result = shared_bootstrap_seed(
        model,
        (0, 1, 2),
        {"all": (proposal, obs)},
        carried_corrections={"all": carried},
        fallback_timings={0: 7.0},
    )
    np.testing.assert_allclose(
        model.correction(result["vector"], result["nuisance"]),
        np.where(obs.receiver == 0, 110.0, 220.0),
        atol=1e-6,
    )
    shifts = result["vector"][7] + model.basis @ result["vector"][8:]
    np.testing.assert_allclose(shifts, [7.0, 2.0, 2.0])
    with pytest.raises(ValueError, match="finite training timing"):
        shared_bootstrap_seed(
            model, (0, 1, 2), {"all": (proposal, obs)}, fallback_timings={0: np.nan}
        )
