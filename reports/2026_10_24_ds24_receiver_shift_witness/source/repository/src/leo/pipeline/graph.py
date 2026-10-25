"""Deterministic validation and topological planning for stage DAGs."""

from __future__ import annotations

import heapq
from collections.abc import Iterable

from leo.pipeline.contracts import StageSpec


class PipelineGraphError(ValueError):
    """Base class for invalid pipeline declarations."""


class DuplicateStageError(PipelineGraphError):
    pass


class MissingDependencyError(PipelineGraphError):
    pass


class PipelineCycleError(PipelineGraphError):
    pass


class PipelineGraph:
    """Validated immutable stage graph with a deterministic execution plan."""

    def __init__(self, stages: Iterable[StageSpec]) -> None:
        declared = tuple(stages)
        by_key: dict[str, StageSpec] = {}
        for stage in declared:
            if stage.key in by_key:
                raise DuplicateStageError(f"duplicate pipeline stage: {stage.key}")
            by_key[stage.key] = stage

        missing = sorted(
            {
                dependency
                for stage in declared
                for dependency in stage.dependencies
                if dependency not in by_key
            }
        )
        if missing:
            raise MissingDependencyError(f"missing pipeline dependencies: {', '.join(missing)}")

        self._by_key = by_key
        self._plan = self._topological_plan()

    @property
    def stage_keys(self) -> tuple[str, ...]:
        return tuple(self._by_key)

    def stage(self, key: str) -> StageSpec:
        return self._by_key[key]

    def plan(self) -> tuple[StageSpec, ...]:
        return self._plan

    def _topological_plan(self) -> tuple[StageSpec, ...]:
        indegree = {key: len(stage.dependencies) for key, stage in self._by_key.items()}
        dependents: dict[str, list[str]] = {key: [] for key in self._by_key}
        for stage in self._by_key.values():
            for dependency in stage.dependencies:
                dependents[dependency].append(stage.key)

        ready = [key for key, degree in indegree.items() if degree == 0]
        heapq.heapify(ready)
        ordered: list[StageSpec] = []
        while ready:
            key = heapq.heappop(ready)
            ordered.append(self._by_key[key])
            for dependent in sorted(dependents[key]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heapq.heappush(ready, dependent)

        if len(ordered) != len(self._by_key):
            cyclic = sorted(key for key, degree in indegree.items() if degree > 0)
            raise PipelineCycleError(f"pipeline cycle includes: {', '.join(cyclic)}")
        return tuple(ordered)
