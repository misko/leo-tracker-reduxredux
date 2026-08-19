"""Read-only port for the Standard-GLRT64 subject presentation."""

from __future__ import annotations

from collections.abc import Callable
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
        for view in views:
            detail = self._details.get(view.subject_id)
            if detail is None:
                raise ValueError("fixture Standard view requires a registered subject detail")
            validate_standard_view_binding(detail, view)

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
    if not 4 <= maximum_points <= 2048:
        raise ValueError("maximum_points must be between 4 and 2,048")
    if view.returned_point_count <= maximum_points:
        return view
    if view.view_kind is StandardViewKindV2.WATERFALL:
        waterfall = _extrema_preserving(
            view.waterfall_cells,
            maximum_points,
            (
                lambda item: item.frequency_hz,
                lambda item: item.power_db,
            ),
        )
        return _validated_bound_copy(
            view,
            returned_point_count=len(waterfall),
            waterfall_cells=waterfall,
        )
    if view.view_kind is StandardViewKindV2.CFO_TRAJECTORY:
        return _bound_cfo_view(view, maximum_points)
    return _bound_metric_view(view, maximum_points)


def validate_standard_view_binding(
    detail: StandardSubjectDetailV2,
    view: StandardPlotViewV2,
) -> None:
    """Reject a plot that is not an exact child of its selected subject detail."""

    expected_lanes = tuple(path.path_id for path in detail.subject.receiver_paths)
    if view.session_id != detail.subject.session_id or view.subject_id != detail.subject.subject_id:
        raise ValueError("Standard plot identity does not match selected subject detail")
    if view.receiver_path_ids != expected_lanes:
        raise ValueError("Standard plot lanes do not exactly match selected subject detail")
    if view.time_domain != detail.time_domain:
        raise ValueError("Standard plot time domain does not match selected subject detail")


def _bound_cfo_view(view: StandardPlotViewV2, maximum_points: int) -> StandardPlotViewV2:
    flattened = tuple(
        ("observation", index, -1, item, item.baseband_cfo_hz)
        for index, item in enumerate(view.cfo_observations)
    ) + tuple(
        ("curve", curve_index, point_index, point, point.value)
        for curve_index, curve in enumerate(view.trajectory_curves)
        for point_index, point in enumerate(curve.points)
    )
    selected = _extrema_preserving(
        flattened,
        maximum_points,
        (lambda item: item[4],),
    )
    observation_indexes = {item[1] for item in selected if item[0] == "observation"}
    observations = tuple(
        item for index, item in enumerate(view.cfo_observations) if index in observation_indexes
    )
    selected_curve_points = {(item[1], item[2]) for item in selected if item[0] == "curve"}
    curves = tuple(
        curve.model_copy(
            update={
                "points": tuple(
                    point
                    for point_index, point in enumerate(curve.points)
                    if (curve_index, point_index) in selected_curve_points
                )
            }
        )
        for curve_index, curve in enumerate(view.trajectory_curves)
        if any(index == curve_index for index, _ in selected_curve_points)
    )
    returned = len(observations) + sum(len(curve.points) for curve in curves)
    return _validated_bound_copy(
        view,
        returned_point_count=returned,
        cfo_observations=observations,
        trajectory_curves=curves,
    )


def _bound_metric_view(view: StandardPlotViewV2, maximum_points: int) -> StandardPlotViewV2:
    populated = tuple(
        (index, series)
        for index, series in enumerate(view.series)
        if series.points and series.source_min is not None and series.source_max is not None
    )
    if not populated:
        return _validated_bound_copy(view, returned_point_count=0, series=())
    global_min = view.vertical_axis.full_source_min
    global_max = view.vertical_axis.full_source_max
    anchor_indexes = {
        next(index for index, series in populated if series.source_min == global_min),
        next(index for index, series in populated if series.source_max == global_max),
    }
    selected_points: dict[int, tuple] = {}
    remaining = maximum_points
    for index in sorted(anchor_indexes):
        extrema = _extrema_preserving(
            view.series[index].points,
            min(2, len(view.series[index].points)),
            (lambda point: point.value,),
        )
        selected_points[index] = extrema
        remaining -= len(extrema)
    if remaining < 0:
        raise ValueError("point budget cannot preserve aggregate metric extrema")
    for index, series in populated:
        if index in selected_points:
            continue
        extrema = _extrema_preserving(
            series.points,
            min(2, len(series.points)),
            (lambda point: point.value,),
        )
        if len(extrema) > remaining:
            continue
        selected_points[index] = extrema
        remaining -= len(extrema)
    candidates = tuple(
        (series_index, point_index, point)
        for series_index in sorted(selected_points)
        for point_index, point in enumerate(view.series[series_index].points)
        if point not in selected_points[series_index]
    )
    for series_index, _, point in _evenly_spaced(candidates, remaining):
        selected_points[series_index] = (*selected_points[series_index], point)
    series_projection = tuple(
        series.model_copy(
            update={
                "points": tuple(
                    point for point in series.points if point in selected_points[series_index]
                ),
                "truncated": series.source_point_count > len(selected_points[series_index]),
            }
        )
        for series_index, series in enumerate(view.series)
        if series_index in selected_points
    )
    returned = sum(len(series.points) for series in series_projection)
    return _validated_bound_copy(
        view,
        returned_point_count=returned,
        series=series_projection,
    )


def _validated_bound_copy(
    view: StandardPlotViewV2,
    *,
    returned_point_count: int,
    **updates: object,
) -> StandardPlotViewV2:
    return StandardPlotViewV2.model_validate(
        view.model_copy(
            update={
                "returned_point_count": returned_point_count,
                "truncated": view.source_point_count > returned_point_count,
                **updates,
            }
        ).model_dump()
    )


def _extrema_preserving[ValueT](
    values: tuple[ValueT, ...],
    maximum_points: int,
    projections: tuple[Callable[[ValueT], float], ...],
) -> tuple[ValueT, ...]:
    if not values or len(values) <= maximum_points:
        return values
    mandatory_indexes: set[int] = set()
    for projection in projections:
        mandatory_indexes.add(min(range(len(values)), key=lambda index: projection(values[index])))
        mandatory_indexes.add(max(range(len(values)), key=lambda index: projection(values[index])))
    if len(mandatory_indexes) > maximum_points:
        raise ValueError("point budget cannot preserve required full-source extrema")
    available_indexes = tuple(
        index for index in range(len(values)) if index not in mandatory_indexes
    )
    extra_indexes = _evenly_spaced(
        available_indexes,
        maximum_points - len(mandatory_indexes),
    )
    selected_indexes = sorted(mandatory_indexes | set(extra_indexes))
    return tuple(values[index] for index in selected_indexes)


def _evenly_spaced[ValueT](values: tuple[ValueT, ...], maximum_points: int) -> tuple[ValueT, ...]:
    if maximum_points <= 0 or not values:
        return ()
    if len(values) <= maximum_points:
        return values
    if maximum_points == 1:
        return (values[0],)
    last = len(values) - 1
    indexes = tuple(round(index * last / (maximum_points - 1)) for index in range(maximum_points))
    return tuple(values[index] for index in indexes)
