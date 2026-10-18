"""Explicit analyzer registry; no dynamic import or infrastructure discovery."""

from __future__ import annotations

from collections.abc import Iterable

from leo.pipeline.contracts import Analyzer
from leo.pipeline.graph import PipelineGraph


class DuplicateAnalyzerError(ValueError):
    pass


class UnknownAnalyzerError(KeyError):
    pass


class AnalyzerRegistry:
    def __init__(self, analyzers: Iterable[Analyzer] = ()) -> None:
        self._analyzers: dict[str, Analyzer] = {}
        for analyzer in analyzers:
            self.register(analyzer)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._analyzers))

    def register(self, analyzer: Analyzer) -> None:
        key = analyzer.spec.key
        if key in self._analyzers:
            raise DuplicateAnalyzerError(f"analyzer already registered: {key}")
        self._analyzers[key] = analyzer

    def get(self, key: str) -> Analyzer:
        try:
            return self._analyzers[key]
        except KeyError as error:
            raise UnknownAnalyzerError(key) from error

    def graph(self, stage_keys: Iterable[str] | None = None) -> PipelineGraph:
        keys = self.keys if stage_keys is None else tuple(stage_keys)
        analyzers = [self.get(key) for key in keys]
        return PipelineGraph(analyzer.spec for analyzer in analyzers)

    def plan(self, stage_keys: Iterable[str] | None = None) -> tuple[Analyzer, ...]:
        graph = self.graph(stage_keys)
        return tuple(self.get(stage.key) for stage in graph.plan())
