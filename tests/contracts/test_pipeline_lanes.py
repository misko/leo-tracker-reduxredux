from __future__ import annotations

import pytest

from leo.contracts.digests import canonical_digest
from leo.contracts.pipeline_lanes import (
    DISABLED_AUTOMATIC_LANE_SELECTION_V1,
    PRODUCTION_AUTOMATIC_LANE_SELECTION_V1,
    RESEARCH_PROBE_PATTERN_V2,
    STANDARD_PROBE_PATTERN_V2,
    AutomaticLaneSelectionPolicyV1,
    PipelineDefinitionV1,
    PipelineLane,
    ProbePatternV2,
    assign_dwell_pipeline_lane,
)


def test_standard_and_research_probe_patterns_are_exact_and_independent() -> None:
    assert STANDARD_PROBE_PATTERN_V2.sample_geometry(2_500_000) == (
        125_000,
        50_000,
        (0, 62_500),
    )
    assert RESEARCH_PROBE_PATTERN_V2.sample_geometry(2_500_000) == (
        125_000,
        50_000,
        (0, 37_500, 75_000),
    )
    assert STANDARD_PROBE_PATTERN_V2.probe_count(1) == 40
    assert RESEARCH_PROBE_PATTERN_V2.probe_count(1) == 60
    assert STANDARD_PROBE_PATTERN_V2.probe_count(60) == 2_400
    assert RESEARCH_PROBE_PATTERN_V2.probe_count(60) == 3_600
    assert STANDARD_PROBE_PATTERN_V2.digest != RESEARCH_PROBE_PATTERN_V2.digest


@pytest.mark.parametrize(
    "values",
    (
        {"subwindow_ms": 50, "probe_ms": 20, "start_offsets_ms": (-1,)},
        {"subwindow_ms": 50, "probe_ms": 20, "start_offsets_ms": (0, 0)},
        {"subwindow_ms": 50, "probe_ms": 20, "start_offsets_ms": (25, 0)},
        {"subwindow_ms": 50, "probe_ms": 20, "start_offsets_ms": (0, 31)},
        {"subwindow_ms": 60, "probe_ms": 20, "start_offsets_ms": (0,)},
    ),
)
def test_invalid_probe_patterns_fail_closed(values: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ProbePatternV2.model_validate(values)


def test_fractional_sample_coordinates_reject() -> None:
    pattern = ProbePatternV2(subwindow_ms=50, probe_ms=20, start_offsets_ms=(0, 25))
    with pytest.raises(ValueError, match="integral"):
        pattern.sample_geometry(44_101)


def test_research_definition_cannot_be_automatic_or_promote() -> None:
    values = {
        "schema_version": 1,
        "lane": PipelineLane.RESEARCH,
        "executable_git_sha": "1" * 40,
        "graph_digest": canonical_digest({"graph": "research"}),
        "configuration_digest": canonical_digest({"configuration": "research"}),
        "product_namespace": "research",
        "automatic_eligible": False,
        "promotion_allowed": False,
    }
    definition = PipelineDefinitionV1(
        **values,
        definition_id=canonical_digest(values),
    )
    assert definition.lane is PipelineLane.RESEARCH
    with pytest.raises(ValueError, match="manual"):
        PipelineDefinitionV1.model_validate(
            {
                **values,
                "automatic_eligible": True,
                "definition_id": canonical_digest({**values, "automatic_eligible": True}),
            }
        )


def test_dwell_lane_assignment_is_stable_and_closed() -> None:
    manifest_digest = canonical_digest({"manifest": "stable"})

    first = assign_dwell_pipeline_lane(
        manifest_digest,
        PRODUCTION_AUTOMATIC_LANE_SELECTION_V1,
    )
    second = assign_dwell_pipeline_lane(
        manifest_digest,
        PRODUCTION_AUTOMATIC_LANE_SELECTION_V1,
    )

    assert first == second
    assert first.denominator == 8
    assert first.bucket in range(8)
    assert first.selected_lane is (
        PipelineLane.RESEARCH if first.bucket == 0 else PipelineLane.STANDARD
    )
    assert first.policy_digest == PRODUCTION_AUTOMATIC_LANE_SELECTION_V1.digest


def test_disabled_dwell_lane_assignment_always_selects_standard() -> None:
    assignments = {
        assign_dwell_pipeline_lane(
            canonical_digest({"manifest": index}),
            DISABLED_AUTOMATIC_LANE_SELECTION_V1,
        ).selected_lane
        for index in range(64)
    }

    assert assignments == {PipelineLane.STANDARD}


def test_production_assignment_is_one_of_eight_uniform_digest_buckets() -> None:
    counts = {bucket: 0 for bucket in range(8)}
    for index in range(8_192):
        assignment = assign_dwell_pipeline_lane(
            canonical_digest({"manifest": index}),
            PRODUCTION_AUTOMATIC_LANE_SELECTION_V1,
        )
        counts[assignment.bucket] += 1

    assert sum(counts.values()) == 8_192
    assert all(850 <= count <= 1_200 for count in counts.values())


def test_invalid_automatic_lane_policy_fails_closed() -> None:
    with pytest.raises(ValueError, match="numerator"):
        AutomaticLaneSelectionPolicyV1(
            enabled=True,
            allocation_epoch="bad",
            research_numerator=9,
            denominator=8,
        )
    with pytest.raises(ValueError, match="disabled"):
        AutomaticLaneSelectionPolicyV1(
            enabled=False,
            allocation_epoch="bad",
            research_numerator=1,
            denominator=8,
        )
