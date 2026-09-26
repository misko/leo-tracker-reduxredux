import importlib.util
import sys
from pathlib import Path

import numpy as np

PATH = (
    Path(__file__).resolve().parents[2]
    / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track/multitrack/model.py"
)
SPEC = importlib.util.spec_from_file_location("multitrack_model", PATH)
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


def test_joint_fit_recovers_gauge_fixed_common_and_relative_tracks():
    t = np.tile(np.linspace(0, 0.06, 61), 2)
    mode = np.repeat(["a", "b"], 61)
    x = (t - 0.03) / 0.03
    common = 0.3 + 0.7 * x - 0.2 * x**2
    geometry = np.where(mode == "a", 0.5 - 0.1 * x, -0.5 + 0.1 * x)
    fit = M.fit_joint_gauge(mode, t, common + geometry, degree=2)
    np.testing.assert_allclose(fit.common, [0.3, 0.7, -0.2], atol=1e-12)
    np.testing.assert_allclose(fit.deviations[0] - fit.deviations[1], [1, -0.2, 0], atol=1e-12)
    assert fit.unconstrained_nullity == 3
    assert fit.rank == 6


def test_unwrap_does_not_choose_cycle_branch_across_missing_gap():
    t = np.array([0, 0.01, 0.02, 1.0, 1.01])
    wrapped = np.angle(np.exp(1j * np.array([2.8, 3.2, 3.6, -2.7, -2.3])))
    unwrapped, segment = M.unwrap_contiguous(t, wrapped, max_gap_s=0.02)
    np.testing.assert_array_equal(segment, [0, 0, 0, 1, 1])
    assert np.allclose(np.diff(unwrapped[:3]), 0.4)
    assert np.allclose(np.diff(unwrapped[3:]), 0.4)
    _, increments = M.synchronized_increments(t, unwrapped, segment)
    np.testing.assert_allclose(increments, [0.4, 0.4, 0.4])


def test_increment_transfer_preserves_held_phase_and_detects_wrong_time_control():
    common = np.sin(np.linspace(0, 4 * np.pi, 80)) * 0.15
    distinct = np.linspace(-0.01, 0.01, 80)
    target = common + distinct
    good = M.increment_transfer_score(common, target)
    wrong = M.increment_transfer_score(np.roll(common, 17), target)
    assert good["correlation"] > 0.99
    assert good["rmse_rad"] < wrong["rmse_rad"] / 5


def test_invalid_shapes_and_single_mode_are_rejected():
    with np.testing.assert_raises(ValueError):
        M.fit_joint_gauge(np.array(["a", "a"]), np.array([0.0, 1.0]), np.zeros(2))


def test_frozen_difference_preserves_target_track_with_simultaneous_donor():
    t = np.linspace(0, 0.12, 25)
    common = 8 * np.sin(13 * t) + 30 * t
    donor = common + 0.2 - 0.4 * t
    target = common - 0.7 + 0.9 * t
    train = t <= 0.06
    predicted, coefficients = M.calibrated_donor_prediction(t, donor, target, train)
    np.testing.assert_allclose(np.angle(np.exp(1j * (predicted - target))), 0, atol=1e-12)
    assert len(coefficients) == 2
    wrong, _ = M.calibrated_donor_prediction(t, np.roll(donor, 5), target, train)
    assert np.sqrt(np.mean(np.angle(np.exp(1j * (wrong[~train] - target[~train]))) ** 2)) > 1


def test_calibration_is_invariant_to_independent_cycles_and_held_target_changes():
    t = np.linspace(0, 0.12, 25)
    donor = np.sin(20 * t)
    target = donor + 0.4 + 2 * t
    train = t <= 0.02
    first, coefficients = M.calibrated_donor_prediction(t, donor, target, train)
    cycled, cycled_coefficients = M.calibrated_donor_prediction(
        t, donor + 4 * np.pi, target - 6 * np.pi, train
    )
    changed_target = target.copy()
    changed_target[~train] += 1.3
    changed, changed_coefficients = M.calibrated_donor_prediction(t, donor, changed_target, train)
    np.testing.assert_allclose(np.angle(np.exp(1j * (first - cycled))), 0, atol=1e-12)
    np.testing.assert_allclose(first, changed, atol=1e-12)
    np.testing.assert_allclose(coefficients, cycled_coefficients, atol=1e-12)
    np.testing.assert_allclose(coefficients, changed_coefficients, atol=1e-12)
