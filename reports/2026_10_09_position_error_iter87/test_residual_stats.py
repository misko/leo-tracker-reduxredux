"""Known-answer tests without recording access or numerical fitting."""

import math

import pytest
from residual_stats import summarize_residuals


def row(receiver, satellite, channel, time_s, residual_hz, probability=1, margin=1):
    return dict(
        receiver=receiver,
        satellite=satellite,
        channel=channel,
        time_s=time_s,
        residual_hz=residual_hz,
        assignment_probability=probability,
        margin=margin,
    )


def test_exact_join_duplicate_averaging_channels_and_no_nearest():
    rows = [
        row(0, 1, 4, 0.0001, 2),
        row(0, 1, 4, 0.0002, 4),
        row(1, 1, 4, 0.0003, 8),
        row(1, 1, 4, 0.002, 100),
        row(0, 1, 5, 0, -100),
        row(1, 2, 4, 0, 100),
    ]
    result = summarize_residuals(rows)["receiver_pairs"]
    assert result["pairs_total"] == 1
    assert result["orientation"] == "RX1-RX0"
    assert result["satellites"][0]["mean_hz"] == 5
    assert result["satellites"][0]["std_hz"] == 0
    assert result["no_op"]


def test_pair_moments_and_ten_pair_two_satellite_gate():
    rows = [
        row(rx, satellite, 0, t, rx * t) for satellite in (1, 2) for rx in (0, 1) for t in range(10)
    ]
    result = summarize_residuals(rows)["receiver_pairs"]
    assert result["eligible_satellite_count"] == 2
    assert not result["no_op"]
    for satellite in result["satellites"]:
        assert satellite["pair_count"] == 10
        assert satellite["mean_hz"] == satellite["median_hz"] == 4.5
        assert satellite["std_hz"] == pytest.approx(math.sqrt(8.25))
        assert satellite["rms_hz"] == pytest.approx(math.sqrt(28.5))
    assert summarize_residuals(rows[:-1])["receiver_pairs"]["no_op"]


def test_frozen_assignment_threshold_noise_and_nonfinite():
    rows = [
        row(0, 0, 0, 0, 1),
        row(0, 1, 0, 0, 1, 0.5),
        row(0, 1, 0, 0, 1, 0.50001),
        row(1, 1, 0, 0, 2),
        row(0, 1, 0, 1, float("nan")),
        row(1, 1, 0, 1, 3, float("nan")),
    ]
    result = summarize_residuals(rows)
    assert result["counts"] == dict(
        total=6, assigned=5, eligible_assignment=2, noise=1, nonfinite=2
    )
    assert result["receiver_pairs"]["pairs_total"] == 1


def test_serial_requires_ten_adjacent_pairs_and_excludes_gaps():
    rows = [row(0, 1, 0, t * 2, t) for t in range(11)]
    rows += [row(0, 1, 0, 23, 100), row(0, 1, 1, 0, 1)]
    stats = summarize_residuals(rows)["serial_groups"]
    assert stats[0]["pair_count"] == 10
    assert stats[0]["eligible"]
    assert stats[0]["correlation"] == pytest.approx(1)
    assert stats[1]["correlation"] is None
    stats = summarize_residuals(rows[1:])["serial_groups"]
    assert stats[0]["pair_count"] == 9
    assert not stats[0]["eligible"]


def test_margin_is_descriptive_and_undefined_constant_correlations():
    rows = [row(0, 1, 0, t, t + 1, margin=t + 1) for t in range(12)]
    margin = summarize_residuals(rows)["margin"]
    assert margin["correlation_residual"] == pytest.approx(1)
    assert margin["correlation_abs_residual"] == pytest.approx(1)
    assert [q["count"] for q in margin["quartile_groups"]] == [3, 3, 3, 3]
    assert "no variance calibration" in margin["description"]
    assert (
        summarize_residuals([row(0, 1, 0, t, 1) for t in range(11)])["serial_groups"][0][
            "correlation"
        ]
        is None
    )
    empty = summarize_residuals([])
    assert empty["receiver_pairs"]["no_op"]
    assert empty["margin"]["correlation_residual"] is None
