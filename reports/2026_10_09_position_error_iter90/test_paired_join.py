"""Synthetic pairing and existing smooth-clock confounding qualification."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from paired_join import extract_pairs

REPORTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter87"))
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter88"))
from linear_contrast import projected_ridge  # noqa: E402
from residual_stats import summarize_residuals  # noqa: E402


def observation(times, receivers, channels):
    return SimpleNamespace(
        times_s=np.asarray(times), receiver=np.asarray(receivers), channel=np.asarray(channels)
    )


def test_duplicate_means_linkage_and_exact_design_difference():
    obs = observation([0.0001, 0.0002, 0.0003, 0.0004], [0, 0, 1, 1], [3] * 4)
    result = extract_pairs(
        obs,
        [11] * 4,
        [2, 4, 10, 14],
        assignment_probability=[1] * 4,
        smooth_clock_design=[[1, 2], [3, 4], [8, 10], [12, 14]],
    )
    np.testing.assert_array_equal(result["y_hz"], [9])
    np.testing.assert_array_equal(result["smooth_design"], [[8, 9]])
    pair = result["pairs"][0]
    assert pair["rx0_indices"] == [0, 1]
    assert pair["rx1_indices"] == [2, 3]
    assert pair["rx0_count"] == pair["rx1_count"] == 2
    assert pair["time_s"] == 0
    assert pair["rx0_time_mean_s"] == pytest.approx(0.00015)
    assert pair["rx1_time_mean_s"] == pytest.approx(0.00035)


def test_wrong_satellite_channel_or_millisecond_has_no_join():
    obs = observation([0, 0, 0, 0.001], [0, 1, 1, 1], [1, 2, 1, 1])
    result = extract_pairs(obs, [11, 11, 22, 11], [1, 2, 3, 4], assignment_probability=[1] * 4)
    assert len(result["pairs"]) == 0
    assert result["smooth_design"].shape == (0, 0)


def test_half_millisecond_ties_use_even_pair_key():
    obs = observation([0.0005, 0.0004, 0.0015, 0.002], [0, 1, 0, 1], [1] * 4)
    result = extract_pairs(obs, [11] * 4, [1, 3, 4, 9], assignment_probability=[1] * 4)
    np.testing.assert_array_equal(result["time_s"], [0, 0.002])
    assert [r["tick_ms"] for r in result["pairs"]] == [0, 2]
    np.testing.assert_array_equal(result["y_hz"], [2, 5])


def test_fitted_assignment_threshold_and_identical_membership_in_both_arms():
    obs = observation([0] * 6, [0, 1, 0, 1, 0, 1], [1] * 6)
    numbers = [11, 11, 0, 0, 22, 22]
    probability = [0.51, 0.51, 1, 1, 0.5, 1]
    fitted = extract_pairs(obs, numbers, [1, 3, 10, 20, 30, 40], assignment_probability=probability)
    zero = extract_pairs(obs, numbers, [100, 150, 1, 2, 3, 4], assignment_probability=probability)
    assert (
        fitted["counts"]
        == zero["counts"]
        == dict(total=6, assigned=4, eligible_assignment=3, noise=2, nonfinite=0)
    )
    assert fitted["pairs"][0]["rx0_indices"] == zero["pairs"][0]["rx0_indices"]
    assert fitted["pairs"][0]["rx1_indices"] == zero["pairs"][0]["rx1_indices"]
    np.testing.assert_array_equal(fitted["satellite"], zero["satellite"])
    np.testing.assert_array_equal(fitted["y_hz"], [2])
    np.testing.assert_array_equal(zero["y_hz"], [50])


def test_agrees_with_iteration87_pair_counts_and_means():
    obs = observation([0, 0.0001, 0, 1, 1, 2, 2, 2], [0, 0, 1, 0, 1, 0, 1, 1], [3] * 8)
    numbers = [11] * 5 + [22] * 3
    residuals = [2, 4, 9, 3, 7, -2, 5, 9]
    probability = [1] * 8
    paired = extract_pairs(obs, numbers, residuals, assignment_probability=probability)
    rows = [
        dict(
            receiver=int(obs.receiver[i]),
            satellite=numbers[i],
            channel=3,
            time_s=float(obs.times_s[i]),
            residual_hz=residuals[i],
            assignment_probability=1,
            margin=1,
        )
        for i in range(8)
    ]
    original = summarize_residuals(rows)
    assert paired["counts"] == original["counts"]
    assert len(paired["pairs"]) == original["receiver_pairs"]["pairs_total"]
    for row in original["receiver_pairs"]["satellites"]:
        values = paired["y_hz"][paired["satellite"] == row["satellite"]]
        assert len(values) == row["pair_count"]
        assert np.mean(values) == row["mean_hz"]


def test_smooth_clock_difference_can_explain_apparent_satellite_contrast():
    # Two satellites' apparent +/-12Hz means arise entirely from an existing
    # smooth-clock column; projecting that column removes identifiability.
    satellites = np.repeat([11, 22], 10)
    pairs = len(satellites)
    times = np.repeat(np.arange(pairs), 2)
    obs = observation(times, np.tile([0, 1], pairs), np.zeros(2 * pairs, int))
    numbers = np.repeat(satellites, 2)
    signal = np.where(satellites == 11, 1.0, -1.0)
    design = np.column_stack([np.repeat(signal, 2) * np.tile([0, 1], pairs)])
    residuals = design[:, 0] * 12
    joined = extract_pairs(
        obs,
        numbers,
        residuals,
        assignment_probability=np.ones(2 * pairs),
        smooth_clock_design=design,
    )
    contrast = signal[:, None] / np.sqrt(2)
    ordinary = projected_ridge(joined["y_hz"], contrast, np.ones((pairs, 1)), np.ones(pairs), 30)
    projected = projected_ridge(
        joined["y_hz"],
        contrast,
        np.column_stack([np.ones(pairs), joined["smooth_design"]]),
        np.ones(pairs),
        30,
    )
    assert ordinary["data_rank"] == 1
    assert abs(ordinary["coefficients"][0]) > 10
    assert projected["data_rank"] == 0
    np.testing.assert_allclose(projected["coefficients"], 0, atol=1e-12)


@pytest.mark.parametrize("target", ["residual", "probability", "time", "design"])
def test_nonfinite_input_fails_explicitly_even_noise_rows(target):
    obs = observation([0, 0], [0, 1], [1, 1])
    residuals, probability, design = [1, 2], [1, 1], [[1], [2]]
    if target == "residual":
        residuals[0] = float("nan")
    elif target == "probability":
        probability[0] = float("inf")
    elif target == "time":
        obs.times_s = np.array([float("nan"), 0])
    else:
        design[0][0] = float("nan")
    with pytest.raises(ValueError):
        extract_pairs(
            obs, [0, 11], residuals, assignment_probability=probability, smooth_clock_design=design
        )
