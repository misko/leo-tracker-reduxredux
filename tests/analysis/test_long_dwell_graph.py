from __future__ import annotations

from typing import cast

import pytest

from leo.analysis.graphs import (
    LONG_DWELL_STAGE_SPECS,
    ComputeTier,
    long_dwell_budget,
    long_dwell_graph,
    long_dwell_stage_specs,
    validated_long_dwell_registry,
)
from leo.pipeline import Analyzer, StageSpec


class _DeclaredAnalyzer:
    def __init__(self, spec: StageSpec) -> None:
        self.spec = spec

    def analyze(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("graph contract test does not execute analyzers")


def test_one_semantic_graph_has_dependency_closed_tier_views() -> None:
    quick = long_dwell_stage_specs(ComputeTier.QUICK)
    standard = long_dwell_stage_specs(ComputeTier.STANDARD)
    research = long_dwell_stage_specs(ComputeTier.RESEARCH)

    assert standard == research == LONG_DWELL_STAGE_SPECS
    assert quick == standard[: len(quick)]
    assert quick[-1].key == "candidate-cloud"
    assert tuple(item.key for item in standard) == (
        "raw-validate",
        "quality",
        "power",
        "waterfall",
        "starlink-survey",
        "candidate-cloud",
        "activity-track",
        "dense-refine",
        "doppler",
        "locked-integrate",
        "qam",
        "trajectory-feedback",
        "controls",
        "tle-associate",
        "scientific-summary",
        "presentation-overlays",
    )
    assert tuple(item.key for item in long_dwell_graph(ComputeTier.STANDARD).plan()) == tuple(
        item.key for item in standard
    )


def test_compute_tier_changes_bounds_but_contains_no_confidence_claim() -> None:
    quick = long_dwell_budget(ComputeTier.QUICK)
    standard = long_dwell_budget(ComputeTier.STANDARD)
    research = long_dwell_budget(ComputeTier.RESEARCH)

    assert (
        quick.stage("waterfall").maximum_output_points
        < standard.stage("waterfall").maximum_output_points
    )
    assert (
        standard.stage("waterfall").maximum_output_points
        < research.stage("waterfall").maximum_output_points
    )
    assert quick.stage("dense-refine").enabled is False
    assert standard.stage("dense-refine").enabled is True
    assert research.stage("controls").config_dict()["surrogate_count"] == 9
    for budget in (quick, standard, research):
        assert all("confidence" not in item.config_dict() for item in budget.stages)


def test_registry_binding_rejects_any_stage_contract_drift() -> None:
    specs = long_dwell_stage_specs(ComputeTier.QUICK)
    analyzers = cast(tuple[Analyzer, ...], tuple(_DeclaredAnalyzer(item) for item in specs))

    registry = validated_long_dwell_registry(analyzers, ComputeTier.QUICK)

    assert tuple(item.spec.key for item in registry.plan()) == tuple(item.key for item in specs)
    with pytest.raises(ValueError, match="registry mismatch"):
        validated_long_dwell_registry(analyzers[:-1], ComputeTier.QUICK)

    drifted = StageSpec(
        **{
            **specs[-1].model_dump(),
            "algorithm_version": "drifted",
        }
    )
    with pytest.raises(ValueError, match="StageSpec differs"):
        validated_long_dwell_registry(
            cast(
                tuple[Analyzer, ...],
                tuple(_DeclaredAnalyzer(item) for item in (*specs[:-1], drifted)),
            ),
            ComputeTier.QUICK,
        )
