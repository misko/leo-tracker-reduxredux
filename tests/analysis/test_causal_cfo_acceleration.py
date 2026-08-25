from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pytest

from leo.analysis.research.causal_cfo_acceleration import (
    CausalCfoMode,
    CausalCfoPoint,
    CausalCfoResetReason,
    CausalCfoTransition,
    LikelihoodGateFeatures,
    LikelihoodGateMethod,
    choose_causal_likelihood_method,
    track_causal_cfo_acceleration,
)


def _point(index: int, cfo_hz: float, *, segment: int = 0) -> CausalCfoPoint:
    return CausalCfoPoint(
        frame_start_sample=index * 3333,
        reference_time_s=index / 750.0,
        continuity_segment=segment,
        even_cfo_hz=cfo_hz,
    )


def _quadratic_points(count: int) -> tuple[CausalCfoPoint, ...]:
    output = []
    for index in range(count):
        time_s = index / 750.0
        cfo_hz = 120_000.0 - 3_200.0 * time_s + 0.5 * 420.0 * time_s**2
        cfo_hz += 2.0 * np.sin(index * 0.31)
        output.append(_point(index, cfo_hz))
    return tuple(output)


def test_track_is_prefix_invariant() -> None:
    points = _quadratic_points(900)

    prefix = track_causal_cfo_acceleration(points[:700])
    full = track_causal_cfo_acceleration(points)

    assert full.estimates[:700] == prefix.estimates


def test_odd_qin_perturbation_cannot_change_state_or_mode() -> None:
    rows = [
        {
            "point": point,
            "odd_absolute_cfo_hz": point.even_cfo_hz + 10.0,
        }
        for point in _quadratic_points(800)
    ]
    first = track_causal_cfo_acceleration(tuple(row["point"] for row in rows))
    for index, row in enumerate(rows):
        row["odd_absolute_cfo_hz"] = (-1.0 if index % 2 else 1.0) * 1e12
    second = track_causal_cfo_acceleration(tuple(row["point"] for row in rows))

    assert second == first
    assert "odd" not in CausalCfoPoint.__dataclass_fields__


def test_quadratic_state_recovers_cfo_rate_and_acceleration() -> None:
    track = track_causal_cfo_acceleration(_quadratic_points(900))
    estimate = track.estimates[-1]
    assert estimate.mode is CausalCfoMode.STABLE_500MS
    assert estimate.selected_fit is not None
    cutoff_s = estimate.reference_time_s

    assert estimate.selected_fit.cfo_hz == pytest.approx(
        120_000.0 - 3_200.0 * cutoff_s + 0.5 * 420.0 * cutoff_s**2,
        abs=1.0,
    )
    assert estimate.selected_fit.rate_hz_s == pytest.approx(
        -3_200.0 + 420.0 * cutoff_s,
        abs=10.0,
    )
    assert estimate.selected_fit.acceleration_hz_s2 == pytest.approx(420.0, abs=50.0)
    assert {fit.requested_history_s for fit in estimate.baseline_fits} == {
        0.020,
        0.125,
        0.500,
    }


def test_hysteresis_requires_sustained_evidence_and_a_calm_recovery() -> None:
    points = []
    for index in range(1_650):
        time_s = index / 750.0
        cfo_hz = (
            -3_000.0 * time_s if time_s < 0.70 else -3_000.0 * 0.70 + 18_000.0 * (time_s - 0.70)
        )
        points.append(_point(index, cfo_hz))

    track = track_causal_cfo_acceleration(tuple(points))
    enter = [
        item for item in track.estimates if item.transition is CausalCfoTransition.ENTER_CHANGE
    ]
    leave = [
        item for item in track.estimates if item.transition is CausalCfoTransition.LEAVE_CHANGE
    ]

    assert len(enter) == 1
    assert enter[0].reference_time_s > 0.70
    assert enter[0].mode is CausalCfoMode.CHANGE_125MS
    assert len(leave) == 1
    assert leave[0].reference_time_s - enter[0].reference_time_s >= 0.250
    assert leave[0].mode is CausalCfoMode.STABLE_500MS


def test_segment_change_resets_history_and_mode() -> None:
    first = list(_quadratic_points(700))
    last = first[-1]
    second = CausalCfoPoint(
        frame_start_sample=last.frame_start_sample + 3333,
        reference_time_s=last.reference_time_s + 1.0 / 750.0,
        continuity_segment=1,
        even_cfo_hz=last.even_cfo_hz,
    )

    estimate = track_causal_cfo_acceleration(tuple((*first, second))).estimates[-1]

    assert estimate.reset_reason is CausalCfoResetReason.CONTINUITY_SEGMENT_CHANGED
    assert estimate.transition is CausalCfoTransition.RESET
    assert estimate.mode is CausalCfoMode.STABLE_500MS
    assert estimate.selected_fit is None
    assert not estimate.baseline_fits


@pytest.mark.parametrize(
    ("exact_control", "top_second", "method", "weak", "ambiguous"),
    [
        (8.0, 7.0, LikelihoodGateMethod.ORDINARY_CONTINUOUS_PROFILE, False, False),
        (4.0, 7.0, LikelihoodGateMethod.SUMMED_FULL_LIKELIHOOD, True, False),
        (8.0, 4.0, LikelihoodGateMethod.SUMMED_FULL_LIKELIHOOD, False, True),
        (4.0, 4.0, LikelihoodGateMethod.SUMMED_FULL_LIKELIHOOD, True, True),
    ],
)
def test_likelihood_gate_is_even_only_and_fail_closed_to_full_likelihood(
    exact_control: float,
    top_second: float,
    method: LikelihoodGateMethod,
    weak: bool,
    ambiguous: bool,
) -> None:
    features = LikelihoodGateFeatures(
        even_exact_minus_control_log_likelihood=exact_control,
        even_top_minus_second_log_likelihood=top_second,
    )

    decision = choose_causal_likelihood_method(features)

    assert decision.method is method
    assert decision.weak is weak
    assert decision.ambiguous is ambiguous
    assert set(asdict(features)) == {
        "even_exact_minus_control_log_likelihood",
        "even_top_minus_second_log_likelihood",
    }


def test_invalid_order_is_rejected_instead_of_silently_sorted() -> None:
    points = _quadratic_points(2)

    with pytest.raises(ValueError, match="strictly increasing"):
        track_causal_cfo_acceleration(tuple(reversed(points)))
