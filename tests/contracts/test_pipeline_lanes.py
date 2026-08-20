from __future__ import annotations

import pytest

from leo.contracts.digests import canonical_digest
from leo.contracts.pipeline_lanes import (
    RESEARCH_PROBE_PATTERN_V2,
    STANDARD_PROBE_PATTERN_V2,
    PipelineDefinitionV1,
    PipelineLane,
    ProbePatternV2,
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
