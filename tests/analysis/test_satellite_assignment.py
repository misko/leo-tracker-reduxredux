from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.research.satellite_assignment import (
    AssignmentState,
    FrequencyProbe,
    RateProbe,
    SatelliteAssignmentConfig,
    SatellitePrediction,
    assign_duration_constrained,
    find_cross_lane_conflicts,
    interval_support,
    score_frequency_interval,
    score_rate_interval,
)


def _prediction(
    catalog_number: int = 100,
    *,
    linear: bool = False,
) -> SatellitePrediction:
    times = np.linspace(-1.0, 5.0, 1201)
    if linear:
        doppler = -3_000.0 * times
        rate = np.full_like(times, -3_000.0)
    else:
        doppler = -3_000.0 * times + 50.0 * times**2 + 10.0 * times**3
        rate = -3_000.0 + 100.0 * times + 30.0 * times**2
    return SatellitePrediction(
        object_name=f"STARLINK-{catalog_number}",
        catalog_number=catalog_number,
        time_s=tuple(times),
        doppler_hz=tuple(doppler),
        doppler_rate_hz_s=tuple(rate),
    )


def _doppler(time_s: float) -> float:
    return -3_000.0 * time_s + 50.0 * time_s**2 + 10.0 * time_s**3


def _rate(time_s: float) -> float:
    return -3_000.0 + 100.0 * time_s + 30.0 * time_s**2


def _config(**updates: object) -> SatelliteAssignmentConfig:
    base = SatelliteAssignmentConfig(
        tau_min_s=-0.4,
        tau_max_s=0.4,
        tau_step_s=0.1,
        minimum_span_s=1.0,
        minimum_distinct_source_groups=6,
        expected_probe_interval_s=0.2,
        minimum_coverage_fraction=0.8,
        maximum_gap_s=0.25,
        satellite_activation_penalty_per_segment=1.0,
        segment_penalty=1.0,
        unassigned_cost_per_group=5.0,
        maximum_identifiable_tau_width_s=0.2,
    )
    return replace(base, **updates)


def _frequency_probes(
    times: np.ndarray,
    *,
    tau_s: float = 0.2,
    offset_hz: float = 100_000.0,
    lane_id: str = "lane-a",
    prefix: str = "g",
) -> tuple[FrequencyProbe, ...]:
    return tuple(
        FrequencyProbe(
            observation_id=f"{prefix}-o-{index}",
            lane_id=lane_id,
            source_group_id=f"{prefix}-{index}",
            source_time_s=float(time_s),
            time_s=float(time_s),
            cfo_hz=_doppler(float(time_s) + tau_s) + offset_hz,
            sigma_hz=2.0,
        )
        for index, time_s in enumerate(times)
    )


def test_interval_support_enforces_span_distinct_coverage_and_gap() -> None:
    probes = _frequency_probes(np.asarray((0.0, 0.2, 0.4, 1.0, 1.2, 1.4)))
    support = interval_support(probes, _config())

    assert support.eligible is False
    assert support.span_s == pytest.approx(1.4)
    assert support.maximum_gap_s == pytest.approx(0.6)
    assert "coverage_below_minimum" in support.reasons
    assert "gap_above_maximum" in support.reasons

    too_short = interval_support(probes[:5], _config())
    assert "too_few_distinct_source_groups" in too_short.reasons
    assert "span_below_minimum" not in too_short.reasons


def test_frequency_profile_recovers_cfo_and_delay_and_reports_information() -> None:
    probes = _frequency_probes(np.linspace(0.0, 2.0, 11))
    result = score_frequency_interval(probes, _prediction(), _config())

    assert result.fitted_tau_s == pytest.approx(0.2)
    assert result.fitted_cfo_offset_hz == pytest.approx(100_000.0, abs=0.02)
    assert result.residual_rms < 0.02
    assert result.identifiability.tau_at_boundary is False
    assert result.identifiability.conditional_delay_information > 0.0
    assert result.identifiability.data_cost_span > 1.0


def test_linear_doppler_exposes_delay_cfo_nonidentifiability() -> None:
    times = np.linspace(0.0, 2.0, 11)
    probes = tuple(
        FrequencyProbe(
            observation_id=f"o-{index}",
            lane_id="lane-a",
            source_group_id=f"g-{index}",
            source_time_s=float(time_s),
            time_s=float(time_s),
            cfo_hz=-3_000.0 * (float(time_s) + 0.2) + 100_000.0,
            sigma_hz=2.0,
        )
        for index, time_s in enumerate(times)
    )

    result = score_frequency_interval(probes, _prediction(linear=True), _config())

    assert result.identifiability.data_flat is True
    assert result.identifiability.identifiable is False
    assert "delay_profile_too_flat" in result.identifiability.reasons
    assert "insufficient_conditional_delay_information" in result.identifiability.reasons
    assert abs(result.identifiability.tau_nuisance_correlation) == pytest.approx(1.0)


def test_nested_measurements_have_bounded_total_source_group_weight() -> None:
    base = list(_frequency_probes(np.linspace(0.0, 1.0, 6)))
    base[-1] = replace(base[-1], cfo_hz=base[-1].cfo_hz + 50.0)
    duplicated = tuple(base[:-1]) + tuple(
        replace(base[-1], observation_id=f"duplicate-{index}") for index in range(20)
    )

    ordinary = score_frequency_interval(tuple(base), _prediction(), _config())
    nested = score_frequency_interval(duplicated, _prediction(), _config())

    assert nested.data_cost == pytest.approx(ordinary.data_cost, rel=1e-12, abs=1e-12)
    assert nested.fitted_cfo_offset_hz == pytest.approx(ordinary.fitted_cfo_offset_hz)
    assert len(nested.observation_ids) == len(base) - 1 + 20


def test_rate_profile_recovers_delay_and_bounded_rate_nuisance() -> None:
    times = np.linspace(0.0, 2.0, 11)
    probes = tuple(
        RateProbe(
            observation_id=f"r-{index}",
            lane_id="lane-rate",
            source_group_id=f"g-{index}",
            source_time_s=float(time_s),
            time_s=float(time_s),
            rate_hz_s=_rate(float(time_s) + 0.2) + 125.0,
            sigma_hz_s=2.0,
        )
        for index, time_s in enumerate(times)
    )

    result = score_rate_interval(probes, _prediction(), _config())

    assert result.fitted_tau_s == pytest.approx(0.2)
    assert result.fitted_rate_nuisance_hz_s == pytest.approx(125.0, abs=0.02)
    assert result.fitted_cfo_offset_hz is None
    assert result.profile[result.best_index].nuisance_at_bound is False


def test_duration_dp_uses_explicit_unassigned_and_shared_delay_refit() -> None:
    times = np.linspace(0.0, 3.0, 31)
    probes = []
    for index, time_s in enumerate(times):
        if index <= 10:
            value = _doppler(float(time_s) + 0.2) + 100_000.0
        elif index >= 20:
            value = _doppler(float(time_s) + 0.2) + 150_000.0
        else:
            value = _doppler(float(time_s)) + 500_000.0
        probes.append(
            FrequencyProbe(
                observation_id=f"o-{index}",
                lane_id="lane-a",
                source_group_id=f"capture-probe-{index}",
                source_time_s=float(time_s),
                time_s=float(time_s),
                cfo_hz=value,
                sigma_hz=2.0,
            )
        )
    config = _config(
        minimum_distinct_source_groups=11,
        expected_probe_interval_s=0.1,
        maximum_gap_s=0.11,
    )

    result = assign_duration_constrained(tuple(probes), (_prediction(),), config)

    assert [item.state for item in result.segments] == [
        AssignmentState.SATELLITE,
        AssignmentState.UNASSIGNED,
        AssignmentState.SATELLITE,
    ]
    assert [len(item.source_group_ids) for item in result.segments] == [11, 9, 11]
    assert result.global_cross_lane_exclusivity_enforced is False
    assert len(result.shared_satellite_refits) == 1
    shared = result.shared_satellite_refits[0]
    assert shared.fitted_tau_s == pytest.approx(0.2)
    assert [item.fitted_nuisance for item in shared.episode_nuisances] == pytest.approx(
        [100_000.0, 150_000.0], abs=0.02
    )
    assert result.objective.unassigned_cost == pytest.approx(45.0)


def test_null_can_win_and_assignment_rejects_mixed_lanes() -> None:
    probes = _frequency_probes(np.linspace(0.0, 1.0, 6))
    null_result = assign_duration_constrained(
        probes,
        (_prediction(),),
        _config(
            satellite_activation_penalty_per_segment=100.0,
            segment_penalty=100.0,
            unassigned_cost_per_group=0.1,
        ),
    )
    assert len(null_result.segments) == 1
    assert null_result.segments[0].state is AssignmentState.UNASSIGNED

    mixed = probes[:-1] + (replace(probes[-1], lane_id="lane-b"),)
    with pytest.raises(ValueError, match="exactly one frozen lane"):
        assign_duration_constrained(mixed, (_prediction(),), _config())


def test_cross_lane_audit_detects_same_source_group_assigned_to_different_norads() -> None:
    probes_a = _frequency_probes(np.linspace(0.0, 1.0, 6), lane_id="lane-a")
    probes_b = tuple(
        replace(item, observation_id=f"b-{item.observation_id}", lane_id="lane-b")
        for item in probes_a
    )
    config = _config()
    result_a = assign_duration_constrained(probes_a, (_prediction(100),), config)
    result_b = assign_duration_constrained(probes_b, (_prediction(200),), config)

    conflicts = find_cross_lane_conflicts((result_a, result_b))

    assert len(conflicts) == 6
    assert conflicts[0].owners == (("lane-a", 100), ("lane-b", 200))
