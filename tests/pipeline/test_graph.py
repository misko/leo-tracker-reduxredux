from __future__ import annotations

import pytest

from leo.pipeline import (
    AnalyzerRegistry,
    DuplicateAnalyzerError,
    MissingDependencyError,
    PipelineCycleError,
    PipelineGraph,
    StageSpec,
)


class _Analyzer:
    def __init__(self, spec: StageSpec) -> None:
        self.spec = spec

    def analyze(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("planning must not execute analyzers")


def _spec(key: str, *dependencies: str) -> StageSpec:
    return StageSpec(
        key=key,
        algorithm_version="1.0.0",
        configuration_schema=f"{key}.v1",
        dependencies=dependencies,
    )


def test_graph_rejects_missing_dependency() -> None:
    with pytest.raises(MissingDependencyError, match="missing pipeline dependencies: quality"):
        PipelineGraph((_spec("power", "quality"),))


def test_graph_rejects_cycle_and_identifies_members() -> None:
    with pytest.raises(PipelineCycleError, match=r"pipeline cycle includes: a, b, c"):
        PipelineGraph(
            (
                _spec("a", "c"),
                _spec("b", "a"),
                _spec("c", "b"),
            )
        )


def test_registry_plans_dependencies_deterministically() -> None:
    registry = AnalyzerRegistry(
        (
            _Analyzer(_spec("summary", "power")),
            _Analyzer(_spec("power", "quality")),
            _Analyzer(_spec("quality")),
            _Analyzer(_spec("also-ready")),
        )
    )

    assert registry.keys == ("also-ready", "power", "quality", "summary")
    assert tuple(analyzer.spec.key for analyzer in registry.plan()) == (
        "also-ready",
        "quality",
        "power",
        "summary",
    )

    with pytest.raises(DuplicateAnalyzerError, match="quality"):
        registry.register(_Analyzer(_spec("quality")))
