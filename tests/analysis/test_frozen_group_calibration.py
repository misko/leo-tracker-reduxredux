from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.channel_group_calibration import GroupCalibrationFrame, GroupCalibrationObjective
from leo.analysis.frozen_group_calibration import FrozenGroupCalibration, freeze_group_calibration
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.hard60_score import Hard60Objective
from leo.contracts.regional_position import POSITION_SCORES, PositionObservations, RegionalPrior


def state():
    return FrozenGroupCalibration(
        150.0,
        11.5e9,
        GroupCalibrationFrame((0, 1), (0.25, 0.75)),
        np.array([-80000.0, 2.0, -54000.0, 1.0, -600.0]),
        np.array([[100.0, 0.1], [-200.0, -0.1]]),
        np.array([-24000.0, 38000.0]),
        np.array([0.2, -0.3]),
        np.array([0.0, 150.0, 300.0]),
        np.array([[0.0, 30.0, 0.0], [0.0, -30.0, 0.0]]),
    )


def test_held_prediction_uses_training_centers_and_fractions():
    frozen = state()
    # This held-only view's RF/time/group means differ from the trained frame.
    times = np.array([200.0, 240.0])
    rf = np.array([12e9, 12.5e9])
    rx = np.array([0, 1])
    high = np.ones(2, bool)
    actual = frozen.predict(times, rf, rx, high)
    expected = [
        100 + 0.1 * 50 - 80000 + 2 * 50 - 600 * 0.5 - 24000 * 0.75 + 0.2 * 0.75 * 50 + 20,
        -200 - 0.1 * 90 - 54000 + 90 - 600 + 38000 * 0.25 - 0.3 * 0.25 * 90 - 12,
    ]
    np.testing.assert_allclose(actual, expected, atol=1e-10)
    assert frozen.time_center_s == 150 and frozen.rf_center_hz == 11.5e9
    assert frozen.frame.high_fractions == (0.25, 0.75)


def test_frozen_arrays_are_immutable_copies():
    frozen = state()
    with pytest.raises(ValueError):
        frozen.group_offsets_hz[0] = 0


def test_uncovered_clock_support_is_an_explicit_failure():
    frozen = state()
    with pytest.raises(ValueError, match="outside"):
        frozen.predict(np.array([400.0]), np.array([11e9]), np.array([0]), np.array([False]))


def test_invalid_dimensions_and_native_prediction_arrays_are_rejected():
    frozen = state()
    with pytest.raises(ValueError):
        frozen.predict(np.array([200.0]), np.array([11e9, 12e9]), np.array([0]), np.array([False]))
    with pytest.raises(ValueError):
        frozen.predict(np.array([200.0]), np.array([11e9]), np.array([3]), np.array([False]))


@pytest.mark.parametrize("group_clock", [False, True])
def test_export_proves_training_prediction_closure_with_clock_and_group_drift(group_clock):
    n = 32
    times = np.linspace(0, 150, n)
    rx = np.arange(n) % 2
    channels = 1 + (np.arange(n) // 2) % 8
    observations = PositionObservations(
        tuple(map(str, range(n))),
        times,
        np.zeros(n),
        10.5e9 + channels * 250e6,
        rx,
        channels,
        np.ones(n),
    )
    base = Hard60Objective(
        observations,
        SimpleNamespace(numbers=np.arange(1, 4)),
        RegionalPrior(),
        POSITION_SCORES["V16"],
    )
    nodes = np.arange(0.0, 151.0, 30.0)
    clock = JointClockObjective(base, nodes, np.zeros((2, len(nodes))), 4)
    model = GroupCalibrationObjective(
        clock, channels >= 5, group_drift_sigma_hz_s=2, group_clock=group_clock
    )
    vector = np.zeros(model.size)
    vector[2:7] = [-80000.0, 2.0, -54000.0, 1.0, -600.0]
    nuisance = np.r_[np.linspace(-10, 10, model.clock_count), [-24000.0, 38000.0, 0.2, -0.3]]
    nuisance = np.r_[nuisance, np.linspace(-20, 20, model.group_clock_count)]
    frozen = freeze_group_calibration(model, {"vector": vector, "nuisance": nuisance})
    np.testing.assert_allclose(
        frozen.predict(times, observations.rf_hz, rx, channels >= 5),
        model.correction(vector, nuisance),
        atol=1e-8,
    )
    held_times = times + 3
    held_times[-1] = times[-1]
    assert np.isfinite(frozen.predict(held_times, observations.rf_hz, rx, channels >= 5)).all()
