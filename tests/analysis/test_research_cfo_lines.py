from __future__ import annotations

import time

import numpy as np
import pytest

from leo.analysis.research.cfo_lines import (
    CfoPoint,
    DynamicProgrammingConfig,
    HoughConfig,
    LineDetectionConfig,
    LineSegment,
    RansacConfig,
    dynamic_programming_lines,
    robust_ransac_lines,
    weighted_hough_lines,
)

ALIAS_HZ = 1.0 / 4.4e-6


def _point(identifier: str, time_s: float, frequency_hz: float, margin: float = 0.18) -> CfoPoint:
    return CfoPoint(identifier, time_s, frequency_hz, 0.22, 0.04, margin)


def _cloud(*, gap: bool = False) -> tuple[CfoPoint, ...]:
    rng = np.random.default_rng(2048)
    points = []
    times = np.arange(0.0, 6.01, 0.1)
    for time_index, time_s in enumerate(times):
        if not gap or not 2.1 <= time_s <= 2.6:
            alias = (time_index % 3) - 1
            first = -25_000.0 + 4_000.0 * time_s + alias * ALIAS_HZ
            second = 28_000.0 - 4_000.0 * time_s - alias * ALIAS_HZ
            points.append(_point(f"cross-a-{time_index}", time_s, first + rng.normal(0, 35)))
            points.append(_point(f"cross-b-{time_index}", time_s, second + rng.normal(0, 35)))
        parallel = 62_000.0 + 4_000.0 * time_s + ((time_index + 1) % 2) * ALIAS_HZ
        points.append(_point(f"parallel-{time_index}", time_s, parallel + rng.normal(0, 30), 0.14))
        for clutter_index in range(3):
            points.append(
                _point(
                    f"noise-{time_index}-{clutter_index}",
                    time_s,
                    rng.uniform(-2.0 * ALIAS_HZ, 2.0 * ALIAS_HZ),
                    -0.002,
                )
            )
    return tuple(points)


def _common(**changes: float | int) -> LineDetectionConfig:
    values: dict[str, float | int] = {
        "alias_spacing_hz": ALIAS_HZ,
        "minimum_slope_hz_per_s": -10_000.0,
        "maximum_slope_hz_per_s": 10_000.0,
        "residual_gate_hz": 350.0,
        "maximum_gap_s": 0.8,
        "minimum_span_s": 2.0,
        "minimum_support": 16,
        "minimum_point_weight": 0.05,
        "maximum_tracks": 5,
    }
    values.update(changes)
    return LineDetectionConfig(**values)  # type: ignore[arg-type]


def _detectors(common: LineDetectionConfig):
    return (
        (
            weighted_hough_lines,
            HoughConfig(common=common, slope_bins=121, intercept_bins=512, peak_candidates=24),
        ),
        (
            robust_ransac_lines,
            RansacConfig(
                common=common,
                maximum_hypotheses=1_500,
                minimum_pair_separation_s=0.5,
            ),
        ),
        (
            dynamic_programming_lines,
            DynamicProgrammingConfig(
                common=common,
                slope_bins=81,
                maximum_predecessor_groups=9,
            ),
        ),
    )


def _nearest(segments: tuple[LineSegment, ...], slope: float) -> LineSegment:
    return min(segments, key=lambda segment: abs(segment.slope_hz_per_s - slope))


def _alias_distance(value: float, expected: float) -> float:
    return abs((value - expected + ALIAS_HZ / 2.0) % ALIAS_HZ - ALIAS_HZ / 2.0)


@pytest.mark.parametrize("detector,config", _detectors(_common()))
def test_crossing_parallel_alias_lines_are_recovered(detector, config) -> None:
    segments = detector(_cloud(), config)
    assert len(segments) >= 3
    assert _nearest(segments, 4_000.0).support >= 45
    assert _nearest(segments, -4_000.0).support >= 45
    assert abs(_nearest(segments, 4_000.0).slope_hz_per_s - 4_000.0) < 180.0
    assert abs(_nearest(segments, -4_000.0).slope_hz_per_s + 4_000.0) < 180.0
    positive = [segment for segment in segments if abs(segment.slope_hz_per_s - 4_000.0) < 180]
    assert len(positive) >= 2  # distinct modulo-alias intercepts preserve parallel tracks


@pytest.mark.parametrize("detector,config", _detectors(_common()))
def test_bounded_gap_is_bridged(detector, config) -> None:
    segments = detector(_cloud(gap=True), config)
    first = min(
        (segment for segment in segments if abs(segment.slope_hz_per_s - 4_000.0) < 180),
        key=lambda segment: _alias_distance(segment.intercept_mod_alias_hz, -25_000.0),
    )
    assert first.start_s <= 0.1
    assert first.end_s >= 5.9
    assert 0.65 <= first.maximum_gap_s <= 0.75


@pytest.mark.parametrize("detector,config", _detectors(_common()))
def test_permutation_determinism(detector, config) -> None:
    points = _cloud()
    shuffled = tuple(points[index] for index in np.random.default_rng(11).permutation(len(points)))
    assert detector(points, config) == detector(shuffled, config)


@pytest.mark.parametrize("detector,config", _detectors(_common()))
def test_noise_only_is_rejected_and_runtime_is_bounded(detector, config) -> None:
    rng = np.random.default_rng(9)
    points = tuple(
        _point(f"noise-{index}", index * 0.02, rng.uniform(-500_000, 500_000), -0.001)
        for index in range(300)
    )
    started = time.perf_counter()
    assert detector(points, config) == ()
    assert time.perf_counter() - started < 2.0


def test_explicit_track_bound_is_respected() -> None:
    config = HoughConfig(common=_common(maximum_tracks=2))
    assert len(weighted_hough_lines(_cloud(), config)) == 2


def test_duplicate_identifiers_and_nonfinite_values_are_rejected() -> None:
    duplicate = _point("same", 0.0, 1.0)
    with pytest.raises(ValueError, match="identifiers"):
        weighted_hough_lines((duplicate, duplicate))
    with pytest.raises(ValueError, match="finite"):
        weighted_hough_lines((_point("bad", 0.0, float("nan")),))
