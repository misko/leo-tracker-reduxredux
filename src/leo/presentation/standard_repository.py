"""Read-only port for the Standard-GLRT64 subject presentation."""

from __future__ import annotations

from typing import Protocol

from leo.presentation.standard_pipeline import (
    StandardPlotViewV2,
    StandardSubjectDetailV2,
    StandardSubjectHierarchyV2,
    StandardViewKindV2,
)


class StandardPresentationRepository(Protocol):
    """Bounded projection port; implementations must never read raw IQ."""

    def subject_hierarchy(self, session_id: str) -> StandardSubjectHierarchyV2 | None: ...

    def subject_detail(
        self, session_id: str, subject_id: str
    ) -> StandardSubjectDetailV2 | None: ...

    def subject_view(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        maximum_points: int,
    ) -> StandardPlotViewV2 | None: ...


class FixtureStandardPresentationRepository:
    """Deterministic test/UI repository with bounded lazy-view behavior."""

    def __init__(
        self,
        hierarchy: StandardSubjectHierarchyV2,
        details: tuple[StandardSubjectDetailV2, ...],
        views: tuple[StandardPlotViewV2, ...],
    ) -> None:
        self._hierarchy = hierarchy
        self._details = {item.subject.subject_id: item for item in details}
        self._views = {(item.subject_id, item.view_kind): item for item in views}
        if len(self._details) != len(details) or len(self._views) != len(views):
            raise ValueError("fixture Standard subject/view identities must be unique")
        if any(item.subject.session_id != hierarchy.session_id for item in details):
            raise ValueError("fixture Standard details must belong to the hierarchy session")

    def subject_hierarchy(self, session_id: str) -> StandardSubjectHierarchyV2 | None:
        return self._hierarchy if session_id == self._hierarchy.session_id else None

    def subject_detail(self, session_id: str, subject_id: str) -> StandardSubjectDetailV2 | None:
        if session_id != self._hierarchy.session_id:
            return None
        return self._details.get(subject_id)

    def subject_view(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        maximum_points: int,
    ) -> StandardPlotViewV2 | None:
        if session_id != self._hierarchy.session_id:
            return None
        view = self._views.get((subject_id, view_kind))
        if view is None:
            return None
        return _bound_view(view, maximum_points)


def _bound_view(view: StandardPlotViewV2, maximum_points: int) -> StandardPlotViewV2:
    if not 1 <= maximum_points <= 2048:
        raise ValueError("maximum_points must be between 1 and 2,048")
    if view.returned_point_count <= maximum_points:
        return view

    remaining = maximum_points
    series = []
    for item in view.series:
        selected = _evenly_spaced(item.points, min(len(item.points), remaining))
        remaining -= len(selected)
        series.append(
            item.model_copy(
                update={
                    "points": selected,
                    "truncated": item.source_point_count > len(selected),
                }
            )
        )
        if remaining == 0:
            break
    waterfall = _evenly_spaced(view.waterfall_cells, min(len(view.waterfall_cells), remaining))
    remaining -= len(waterfall)
    observations = _evenly_spaced(view.cfo_observations, min(len(view.cfo_observations), remaining))
    remaining -= len(observations)
    curves = []
    for curve in view.trajectory_curves:
        if remaining == 0:
            break
        selected = _evenly_spaced(curve.points, min(len(curve.points), remaining))
        remaining -= len(selected)
        curves.append(curve.model_copy(update={"points": selected}))
    returned = (
        sum(len(item.points) for item in series)
        + len(waterfall)
        + len(observations)
        + sum(len(item.points) for item in curves)
    )
    return view.model_copy(
        update={
            "returned_point_count": returned,
            "truncated": view.source_point_count > returned,
            "series": tuple(series),
            "waterfall_cells": waterfall,
            "cfo_observations": observations,
            "trajectory_curves": tuple(curves),
        }
    )


def _evenly_spaced(values: tuple, maximum_points: int) -> tuple:
    if maximum_points <= 0 or not values:
        return ()
    if len(values) <= maximum_points:
        return values
    if maximum_points == 1:
        return (values[0],)
    last = len(values) - 1
    indexes = tuple(round(index * last / (maximum_points - 1)) for index in range(maximum_points))
    return tuple(values[index] for index in indexes)
