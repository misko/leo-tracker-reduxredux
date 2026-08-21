from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.research.tle_doppler_alignment import (
    ObservedCfoTrajectory,
    PredictedDopplerTrajectory,
    compare_trajectory,
    rank_predictions,
    threshold_intervals,
)

ANCHOR_NS = 1_787_343_000_000_000_000


def _observed(
    *,
    coefficients: tuple[float, ...] = (0.5, -2_000.0, 350_000.0),
) -> ObservedCfoTrajectory:
    return ObservedCfoTrajectory(
        trajectory_id="observed-a",
        path_id="session/stream-0/rx-0",
        polynomial_degree=len(coefficients) - 1,
        reference_time_s=30.0,
        coefficients_hz=coefficients,
        start_s=0.0,
        end_s=60.0,
        first_estimate_utc_ns=ANCHOR_NS - 30_000_000_000,
        first_earliest_utc_ns=ANCHOR_NS - 30_200_000_000,
        first_latest_utc_ns=ANCHOR_NS - 29_800_000_000,
    )


def _predicted(
    catalog_number: int,
    *,
    slope: float = -2_000.0,
    acceleration: float = 1.0,
    intercept: float = 100_000.0,
) -> PredictedDopplerTrajectory:
    return PredictedDopplerTrajectory(
        object_name=f"STARLINK-{catalog_number}",
        catalog_number=catalog_number,
        reference_utc_ns=ANCHOR_NS,
        start_utc_ns=ANCHOR_NS - 30_000_000_000,
        end_utc_ns=ANCHOR_NS + 30_000_000_000,
        frequency_at_reference_hz=intercept,
        slope_hz_s=slope,
        acceleration_hz_s2=acceleration,
        jerk_hz_s3=0.0,
        element_epoch_utc_ns=ANCHOR_NS - 3_600_000_000_000,
        element_age_s=3_600.0,
        peak_elevation_deg=45.0,
    )


def test_comparison_ignores_the_unknown_frequency_intercept() -> None:
    first = compare_trajectory(_observed(), _predicted(1, intercept=-250_000.0))
    second = compare_trajectory(_observed(), _predicted(1, intercept=450_000.0))

    assert first is not None and second is not None
    assert first.detrended_frequency_rms_hz == pytest.approx(0.0, abs=1e-9)
    assert second.detrended_frequency_rms_hz == pytest.approx(0.0, abs=1e-9)
    assert first.comparison_score == pytest.approx(second.comparison_score, abs=1e-12)
    assert first.fitted_frequency_offset_hz != second.fitted_frequency_offset_hz


def test_derivative_disagreement_is_exposed() -> None:
    result = compare_trajectory(_observed(), _predicted(1, slope=-1_500.0))

    assert result is not None
    assert result.slope_rms_difference_hz_s == pytest.approx(500.0)
    assert result.comparison_score == pytest.approx(500.0)


def test_ranking_is_deterministic_and_includes_timing_sensitivity() -> None:
    ranked = rank_predictions(
        _observed(),
        (
            _predicted(30, slope=-1_000.0),
            _predicted(20),
            _predicted(10),
        ),
        limit=2,
    )

    assert [item.prediction.catalog_number for item in ranked] == [10, 20]
    assert [item.rank for item in ranked] == [1, 2]
    assert ranked[0].best_timing_score <= ranked[0].worst_timing_score


def test_nonoverlapping_prediction_is_not_ranked() -> None:
    prediction = _predicted(1)
    shifted = replace(
        prediction,
        start_utc_ns=ANCHOR_NS + 120_000_000_000,
        end_utc_ns=ANCHOR_NS + 180_000_000_000,
    )

    assert rank_predictions(_observed(), (shifted,)) == ()


def test_threshold_intervals_interpolate_crossings_and_report_clipping() -> None:
    intervals = threshold_intervals(
        np.asarray((0.0, 1.0, 2.0, 3.0, 4.0)),
        np.asarray((61.0, 59.0, 61.0, 63.0, 59.0)),
        threshold=60.0,
    )

    assert len(intervals) == 2
    assert intervals[0].start_s == pytest.approx(0.0)
    assert intervals[0].end_s == pytest.approx(0.5)
    assert intervals[0].clipped_at_start is True
    assert intervals[0].clipped_at_end is False
    assert intervals[1].start_s == pytest.approx(1.5)
    assert intervals[1].end_s == pytest.approx(3.75)
    assert intervals[1].clipped_at_start is False
    assert intervals[1].clipped_at_end is False


def test_threshold_intervals_reject_nonmonotonic_times() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        threshold_intervals(
            np.asarray((0.0, 1.0, 1.0)),
            np.asarray((0.0, 1.0, 2.0)),
            threshold=1.0,
        )
