from __future__ import annotations

from pathlib import Path

import pytest

from leo.contracts.mixed_rate_capture import CapturePlanV3
from leo.contracts.mixed_rate_schedule import ProductionDwellClass
from leo.contracts.states import StarlinkEdge
from leo.domain.mixed_rate_capture import compile_mixed_rate_capture_plan_v3
from leo.domain.profiles import load_profile_revision

_ROOT = Path(__file__).parents[2]


def _revision(rate: str):
    return load_profile_revision(
        _ROOT / "profiles" / f"starlink-ch4-lower-{rate}-60s-mixed-device-axis-v4.yaml"
    )


@pytest.mark.parametrize(
    ("dwell_class", "high_rate", "expected_count"),
    (
        (ProductionDwellClass.MIXED_2P5_5, "5m", 300_000_000),
        (ProductionDwellClass.MIXED_2P5_10, "10m", 600_000_000),
        (ProductionDwellClass.MIXED_2P5_15, "15m", 900_000_000),
    ),
)
def test_compile_mixed_plan_closes_per_radio_geometry(
    dwell_class: ProductionDwellClass,
    high_rate: str,
    expected_count: int,
) -> None:
    low = _revision("2p5m")
    high = _revision(high_rate)
    plan = compile_mixed_rate_capture_plan_v3(
        dwell_class=dwell_class,
        radio_ids=("radio-20", "radio-21"),
        profile_revisions_by_radio={"radio-20": low, "radio-21": high},
        starlink_channel=2,
        starlink_edge=StarlinkEdge.UPPER,
    )

    assert tuple(item.resolved_sample_count for item in plan.radio_plans) == (
        150_000_000,
        expected_count,
    )
    expected_centers = (
        {1_440_312_500}
        if high_rate == "5m"
        else {1_437_500_000 if high_rate == "15m" else 1_440_000_000, 1_440_312_500}
    )
    assert {item.requested_settings.center_frequency_hz for item in plan.radio_plans} == (
        expected_centers
    )
    assert all(
        item.captured_if_stop_hz - item.captured_if_start_hz
        == item.requested_settings.sample_rate_hz
        for item in plan.radio_plans
    )
    assert all(
        item.channel_if_start_hz <= item.captured_if_start_hz
        and item.captured_if_stop_hz <= item.channel_if_stop_hz
        for item in plan.radio_plans
    )
    assert CapturePlanV3.model_validate_json(plan.model_dump_json()) == plan


def test_plan_rejects_rate_class_or_maximum_coverage_geometry_tamper() -> None:
    plan = compile_mixed_rate_capture_plan_v3(
        dwell_class=ProductionDwellClass.MIXED_2P5_5,
        radio_ids=("radio-20", "radio-21"),
        profile_revisions_by_radio={"radio-20": _revision("2p5m"), "radio-21": _revision("5m")},
        starlink_channel=4,
        starlink_edge=StarlinkEdge.LOWER,
    )
    wrong = plan.model_dump(mode="json")
    wrong["radio_plans"][1]["requested_settings"]["center_frequency_hz"] += 1
    with pytest.raises(ValueError, match="maximize in-channel"):
        CapturePlanV3.model_validate(wrong)

    wrong = plan.model_dump(mode="json")
    wrong["radio_plans"][1]["requested_settings"]["center_frequency_hz"] += 1
    wrong["radio_plans"][1]["captured_if_start_hz"] += 1
    wrong["radio_plans"][1]["captured_if_stop_hz"] += 1
    with pytest.raises(ValueError, match="exact maximum-coverage"):
        CapturePlanV3.model_validate(wrong)

    wrong = plan.model_dump(mode="json")
    wrong["starlink_channel"] = 3
    with pytest.raises(ValueError, match="exact maximum-coverage"):
        CapturePlanV3.model_validate(wrong)

    wrong = plan.model_dump(mode="json")
    wrong["starlink_edge"] = StarlinkEdge.UPPER.value
    with pytest.raises(ValueError, match="exact maximum-coverage"):
        CapturePlanV3.model_validate(wrong)

    wrong = plan.model_dump(mode="json")
    wrong["dwell_class"] = ProductionDwellClass.MIXED_2P5_15.value
    with pytest.raises(ValueError, match="geometry"):
        CapturePlanV3.model_validate(wrong)
