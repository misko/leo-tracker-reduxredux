from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.research.adaptive_frame_cfo import (
    AdaptiveFrameCfoHistoryChangeReason,
    AdaptiveFrameCfoPoint,
    AdaptiveFrameCfoResetReason,
    AdaptiveFrameCfoSelectionReason,
    track_adaptive_frame_cfo,
)

_FRAME_RATE_HZ = 750.0
_SAMPLE_RATE_HZ = 2_500_000.0
_CFO_ORIGIN_HZ = 100_000.0


def _ramp_points(
    *,
    duration_s: float,
    rate_hz_s: float = -1_800.0,
    sigma_hz: float = 20.0,
    noise_seed: int | None = 4,
    continuity_segment: int = 0,
) -> tuple[AdaptiveFrameCfoPoint, ...]:
    frame_count = round(duration_s * _FRAME_RATE_HZ) + 1
    rng = np.random.default_rng(noise_seed)
    noise = (
        np.zeros(frame_count, dtype=float)
        if noise_seed is None
        else rng.normal(0.0, sigma_hz, frame_count)
    )
    return tuple(
        AdaptiveFrameCfoPoint(
            frame_start_sample=round(index * _SAMPLE_RATE_HZ / _FRAME_RATE_HZ),
            reference_time_s=index / _FRAME_RATE_HZ,
            continuity_segment=continuity_segment,
            even_cfo_hz=_CFO_ORIGIN_HZ + rate_hz_s * index / _FRAME_RATE_HZ + noise[index],
            even_cfo_sigma_hz=sigma_hz,
        )
        for index in range(frame_count)
    )


def test_constant_ramp_reaches_the_longest_history_with_finite_covariance() -> None:
    rate_hz_s = -1_800.0
    points = _ramp_points(duration_s=0.80, rate_hz_s=rate_hz_s)

    result = track_adaptive_frame_cfo(points)
    estimate = result.estimates[-1]

    assert estimate.selected_history_s == 0.500
    assert estimate.selection_reason is AdaptiveFrameCfoSelectionReason.LONGEST_AVAILABLE
    assert estimate.cfo_hz == pytest.approx(
        _CFO_ORIGIN_HZ + rate_hz_s * estimate.reference_time_s,
        abs=8.0,
    )
    assert estimate.rate_hz_s == pytest.approx(rate_hz_s, abs=40.0)
    assert estimate.cfo_sigma_hz is not None and estimate.cfo_sigma_hz > 0.0
    assert estimate.rate_sigma_hz_s is not None and estimate.rate_sigma_hz_s > 0.0
    assert estimate.cfo_rate_covariance_hz2_s is not None
    covariance_determinant = (
        estimate.cfo_sigma_hz**2 * estimate.rate_sigma_hz_s**2
        - estimate.cfo_rate_covariance_hz2_s**2
    )
    assert covariance_determinant > 0.0
    assert result.training_source == "independent even-Qin frame CFO"
    assert not result.carrier_phase_connected
    assert not result.receiver_relative_timing_used_for_doppler


def test_rate_change_shortens_history_and_discloses_the_change() -> None:
    rng = np.random.default_rng(12)
    change_time_s = 0.65
    first_rate_hz_s = -1_200.0
    second_rate_hz_s = 2_500.0
    points = []
    for index in range(round(1.05 * _FRAME_RATE_HZ) + 1):
        time_s = index / _FRAME_RATE_HZ
        true_cfo_hz = (
            _CFO_ORIGIN_HZ
            + first_rate_hz_s * min(time_s, change_time_s)
            + second_rate_hz_s * max(time_s - change_time_s, 0.0)
        )
        points.append(
            AdaptiveFrameCfoPoint(
                frame_start_sample=round(index * _SAMPLE_RATE_HZ / _FRAME_RATE_HZ),
                reference_time_s=time_s,
                continuity_segment=0,
                even_cfo_hz=true_cfo_hz + rng.normal(0.0, 12.0),
                even_cfo_sigma_hz=12.0,
            )
        )

    result = track_adaptive_frame_cfo(tuple(points))
    changed = [
        estimate
        for estimate in result.estimates
        if estimate.reference_time_s > change_time_s
        and estimate.history_change_reason
        is AdaptiveFrameCfoHistoryChangeReason.SHORTENED_BY_CHANGE
    ]

    assert changed
    assert min(estimate.selected_history_s or 1.0 for estimate in changed) == 0.075
    assert all(
        estimate.selection_reason is AdaptiveFrameCfoSelectionReason.LONGER_HISTORY_INCONSISTENT
        for estimate in changed
    )
    assert any(
        candidate.consistency_chi_square_to_shorter is not None
        and not candidate.consistent_with_all_shorter
        for candidate in changed[-1].candidate_fits
    )
    settled = result.estimates[-1]
    assert settled.rate_hz_s == pytest.approx(second_rate_hz_s, abs=80.0)


def test_outputs_are_exactly_invariant_to_future_frames() -> None:
    points = _ramp_points(duration_s=0.90, rate_hz_s=-2_100.0, noise_seed=19)
    prefix_count = 500

    prefix = track_adaptive_frame_cfo(points[:prefix_count])
    full = track_adaptive_frame_cfo(points)

    assert full.estimates[:prefix_count] == prefix.estimates


def test_time_gap_and_continuity_change_each_reset_all_history() -> None:
    first = list(_ramp_points(duration_s=0.60, noise_seed=None))
    last = first[-1]
    after_gap = AdaptiveFrameCfoPoint(
        frame_start_sample=last.frame_start_sample + round(0.030 * _SAMPLE_RATE_HZ),
        reference_time_s=last.reference_time_s + 0.030,
        continuity_segment=last.continuity_segment,
        even_cfo_hz=last.even_cfo_hz - 54.0,
        even_cfo_sigma_hz=20.0,
    )
    after_segment_change = AdaptiveFrameCfoPoint(
        frame_start_sample=0,
        reference_time_s=after_gap.reference_time_s + 1.0 / _FRAME_RATE_HZ,
        continuity_segment=1,
        even_cfo_hz=after_gap.even_cfo_hz - 2.4,
        even_cfo_sigma_hz=20.0,
    )

    result = track_adaptive_frame_cfo((*first, after_gap, after_segment_change))
    gap_estimate = result.estimates[-2]
    segment_estimate = result.estimates[-1]

    assert gap_estimate.reset_reason is AdaptiveFrameCfoResetReason.TIME_GAP
    assert gap_estimate.history_change_reason is AdaptiveFrameCfoHistoryChangeReason.RESET
    assert gap_estimate.selected_history_s is None
    assert gap_estimate.candidate_fits == ()
    assert segment_estimate.reset_reason is AdaptiveFrameCfoResetReason.CONTINUITY_SEGMENT_CHANGED
    assert segment_estimate.history_change_reason is AdaptiveFrameCfoHistoryChangeReason.RESET
    assert segment_estimate.selected_history_s is None


def test_robust_weighted_fit_rejects_high_leverage_frame_outliers() -> None:
    rng = np.random.default_rng(3)
    truth_rate_hz_s = -2_200.0
    points = []
    for index in range(376):
        time_s = index / _FRAME_RATE_HZ
        value_hz = _CFO_ORIGIN_HZ + truth_rate_hz_s * time_s + rng.normal(0.0, 15.0)
        if 300 <= index <= 375 and index % 4 == 0:
            value_hz += 2_000.0
        points.append(
            AdaptiveFrameCfoPoint(
                frame_start_sample=round(index * _SAMPLE_RATE_HZ / _FRAME_RATE_HZ),
                reference_time_s=time_s,
                continuity_segment=0,
                even_cfo_hz=value_hz,
                even_cfo_sigma_hz=15.0,
            )
        )

    result = track_adaptive_frame_cfo(tuple(points))
    estimate = result.estimates[-1]
    ordinary_rate_hz_s = float(
        np.polyfit(
            [point.reference_time_s for point in points],
            [point.even_cfo_hz for point in points],
            1,
        )[0]
    )

    assert estimate.selected_history_s == 0.500
    assert estimate.rate_hz_s == pytest.approx(truth_rate_hz_s, abs=50.0)
    assert abs(ordinary_rate_hz_s - truth_rate_hz_s) > 500.0
    selected_fit = estimate.candidate_fits[-1]
    assert selected_fit.downweighted_fraction > 0.15
    assert selected_fit.effective_frame_count < selected_fit.frame_count


def test_rate_uncertainty_falls_with_history_and_tracks_reported_frame_sigma() -> None:
    low_sigma = _ramp_points(duration_s=0.55, sigma_hz=10.0, noise_seed=None)
    high_sigma = tuple(
        AdaptiveFrameCfoPoint(
            frame_start_sample=point.frame_start_sample,
            reference_time_s=point.reference_time_s,
            continuity_segment=point.continuity_segment,
            even_cfo_hz=point.even_cfo_hz,
            even_cfo_sigma_hz=40.0,
        )
        for point in low_sigma
    )

    low_result = track_adaptive_frame_cfo(low_sigma).estimates[-1]
    high_result = track_adaptive_frame_cfo(high_sigma).estimates[-1]
    low_rate_sigmas = [fit.rate_sigma_hz_s for fit in low_result.candidate_fits]

    assert len(low_rate_sigmas) == 4
    assert all(
        longer < shorter
        for shorter, longer in zip(low_rate_sigmas, low_rate_sigmas[1:], strict=False)
    )
    assert high_result.rate_sigma_hz_s == pytest.approx(4.0 * low_result.rate_sigma_hz_s)
    assert high_result.cfo_sigma_hz == pytest.approx(4.0 * low_result.cfo_sigma_hz)


def test_invalid_order_cannot_be_silently_sorted_across_a_locklet() -> None:
    points = list(_ramp_points(duration_s=0.10))
    points[4], points[5] = points[5], points[4]

    with pytest.raises(ValueError, match="strictly increasing"):
        track_adaptive_frame_cfo(tuple(points))
