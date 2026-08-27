from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "evaluate_post_refill_edge_switching.py"
    spec = importlib.util.spec_from_file_location("post_refill_edge_switching_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _observation(
    tool: ModuleType,
    *,
    start_ns: int,
    cfo_hz: float,
    path_id: str,
    edge: str,
    duration_ns: int = 1_000_000,
):
    return tool.CfoObservation(
        start_utc_ns=start_ns,
        duration_ns=duration_ns,
        cfo_hz=cfo_hz,
        path_id=path_id,
        stream_id=f"stream-{int(edge == 'upper')}",
        edge=edge,
    )


def test_joint_fit_recovers_edge_difference_with_path_intercepts() -> None:
    tool = _tool()
    common_rate = -3_800.0
    differential_rate = -80.0
    observations = []
    for path_id, edge, intercept in (
        ("lower-rx0", "lower", 120_000.0),
        ("lower-rx1", "lower", -40_000.0),
        ("upper-rx0", "upper", 600_000.0),
        ("upper-rx1", "upper", -220_000.0),
    ):
        sign = 1.0 if edge == "upper" else -1.0
        slope = common_rate + sign * differential_rate / 2.0
        for second in range(8):
            observations.append(
                _observation(
                    tool,
                    start_ns=second * 1_000_000_000,
                    cfo_hz=intercept + slope * second,
                    path_id=path_id,
                    edge=edge,
                )
            )

    result = tool.fit_joint_edge_rate(observations, scale_floor_hz=1.0)

    assert result.common_rate_hz_s == pytest.approx(common_rate, abs=1e-7)
    assert result.differential_rate_hz_s == pytest.approx(differential_rate, abs=1e-7)
    assert result.lower_rate_hz_s == pytest.approx(-3_760.0, abs=1e-7)
    assert result.upper_rate_hz_s == pytest.approx(-3_840.0, abs=1e-7)


def test_strict_mask_requires_the_whole_measurement_after_guard() -> None:
    tool = _tool()
    observations = (
        _observation(
            tool,
            start_ns=1_000,
            duration_ns=1_000,
            cfo_hz=0.0,
            path_id="l-ok",
            edge="lower",
        ),
        _observation(
            tool,
            start_ns=999,
            duration_ns=1_000,
            cfo_hz=0.0,
            path_id="l-guard",
            edge="lower",
        ),
        _observation(
            tool,
            start_ns=9_000,
            duration_ns=1_001,
            cfo_hz=0.0,
            path_id="l-cross",
            edge="lower",
        ),
        _observation(
            tool,
            start_ns=11_000,
            duration_ns=1_000,
            cfo_hz=0.0,
            path_id="u-ok",
            edge="upper",
        ),
        _observation(
            tool,
            start_ns=1_000,
            duration_ns=1_000,
            cfo_hz=0.0,
            path_id="u-wrong",
            edge="upper",
        ),
    )

    retained = tool.strict_schedule_mask(
        observations,
        dwell_ns=10_000,
        guard_ns=1_000,
        phase_ns=0,
    )

    assert [item.path_id for item in retained] == ["l-ok", "u-ok"]


def test_twenty_ms_products_cannot_replay_twelve_or_twenty_two_ms_dwells() -> None:
    tool = _tool()
    observations = []
    for edge, intercept in (("lower", 100_000.0), ("upper", 300_000.0)):
        sign = 1.0 if edge == "upper" else -1.0
        slope = -3_800.0 + sign * -80.0 / 2.0
        for index in range(80):
            start_ns = 1_000_000_000 + index * 25_000_000
            observations.append(
                _observation(
                    tool,
                    start_ns=start_ns,
                    duration_ns=20_000_000,
                    cfo_hz=intercept + slope * start_ns / 1e9,
                    path_id=f"{edge}-rx0",
                    edge=edge,
                )
            )

    result = tool.evaluate_virtual_schedules(
        observations,
        scale_floor_hz=1.0,
        phase_count=8,
    )

    assert [row["status"] for row in result["schedules"][:2]] == [
        "not_resolvable_from_measurement_duration",
        "not_resolvable_from_measurement_duration",
    ]
    assert result["schedules"][0]["valid_start_slack_s"] < 0.0
    assert result["schedules"][1]["valid_start_slack_s"] == 0.0
    assert result["baseline"]["observation_count_by_edge"] == {
        "lower": 80,
        "upper": 80,
    }

    sensitivity = tool.evaluate_relative_timing_sensitivity(
        observations,
        upper_timing_uncertainty_ns=2_000_000,
        scale_floor_hz=1.0,
        phase_count=8,
    )
    assert sensitivity["tested_upper_offsets_ns"] == [
        -2_000_000,
        -1_000_000,
        0,
        1_000_000,
        2_000_000,
    ]
    assert sensitivity["baseline_differential_rates_hz_s"] == pytest.approx(
        [-80.0] * 5,
        abs=1e-7,
    )
    assert (
        sensitivity["schedules"][0]["uncertainty_envelope_status"]
        == "not_resolvable_from_measurement_duration"
    )


def test_observed_count_supports_both_published_stream_shapes() -> None:
    tool = _tool()

    assert tool._stream_observed_sample_count({"captured_sample_count": 123}) == 123
    assert tool._stream_observed_sample_count({"observed_sample_count": 456}) == 456


def test_fine_measurement_support_is_the_pilot_span_not_the_whole_frame() -> None:
    tool = _tool()

    first, final = tool._pilot_support_sample_offsets(2_500_000, 64)

    assert (first, final) == (22, 726)
    assert (final - first) / 2_500_000 == pytest.approx(281.6e-6)
