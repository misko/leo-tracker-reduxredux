"""Read-only port for the Standard-GLRT64 subject presentation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from leo.presentation.standard_pipeline import (
    StandardPlotViewV2,
    StandardReplayAuditV1,
    StandardSourceExtremaProofV2,
    StandardSubjectDetailV2,
    StandardSubjectHierarchyV2,
    StandardViewKindV2,
    standard_source_extrema_proof_v2,
)
from leo.presentation.standard_png import StandardPngSource

type StandardSourceDigestBinding = tuple[str, str]


class StandardPresentationRepository(Protocol):
    """Bounded projection port; implementations must never read raw IQ."""

    def subject_hierarchy(self, session_id: str) -> StandardSubjectHierarchyV2 | None: ...

    def subject_detail(
        self, session_id: str, subject_id: str
    ) -> StandardSubjectDetailV2 | None: ...

    def subject_replay_audit(
        self, session_id: str, subject_id: str
    ) -> StandardReplayAuditV1 | None: ...

    def subject_view(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        maximum_points: int,
    ) -> StandardPlotViewV2 | None: ...

    def subject_png_source(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
    ) -> StandardPngSource | None: ...

    def subject_png_cache_identity(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
    ) -> str | None: ...

    def verify_source_extrema(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        proof: StandardSourceExtremaProofV2,
    ) -> bool: ...


class FixtureStandardPresentationRepository:
    """Deterministic test/UI repository with bounded lazy-view behavior."""

    def __init__(
        self,
        hierarchy: StandardSubjectHierarchyV2,
        details: tuple[StandardSubjectDetailV2, ...],
        views: tuple[StandardPlotViewV2, ...],
        *,
        source_bindings: dict[tuple[str, StandardViewKindV2], StandardSourceDigestBinding],
        replay_audits: tuple[StandardReplayAuditV1, ...] = (),
    ) -> None:
        self._hierarchy = hierarchy
        self._details = {item.subject.subject_id: item for item in details}
        self._views = {(item.subject_id, item.view_kind): item for item in views}
        self._source_bindings = dict(source_bindings)
        self._replay_audits = {item.subject_id: item for item in replay_audits}
        if len(self._details) != len(details) or len(self._views) != len(views):
            raise ValueError("fixture Standard subject/view identities must be unique")
        if set(self._source_bindings) != set(self._views):
            raise ValueError(
                "every fixture Standard view requires one authoritative source binding"
            )
        if any(item.subject.session_id != hierarchy.session_id for item in details):
            raise ValueError("fixture Standard details must belong to the hierarchy session")
        for view in views:
            detail = self._details.get(view.subject_id)
            if detail is None:
                raise ValueError("fixture Standard view requires a registered subject detail")
            validate_standard_view_binding(detail, view)
            artifact_digest, content_digest = self._source_bindings[
                (view.subject_id, view.view_kind)
            ]
            if (
                _recompute_source_extrema(
                    view,
                    source_artifact_digest=artifact_digest,
                    source_content_digest=content_digest,
                )
                != view.source_extrema
            ):
                raise ValueError("fixture source-extrema proof does not match full source data")

    def subject_hierarchy(self, session_id: str) -> StandardSubjectHierarchyV2 | None:
        return self._hierarchy if session_id == self._hierarchy.session_id else None

    def subject_detail(self, session_id: str, subject_id: str) -> StandardSubjectDetailV2 | None:
        if session_id != self._hierarchy.session_id:
            return None
        return self._details.get(subject_id)

    def subject_replay_audit(
        self, session_id: str, subject_id: str
    ) -> StandardReplayAuditV1 | None:
        if session_id != self._hierarchy.session_id:
            return None
        return self._replay_audits.get(subject_id)

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

    def subject_png_source(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
    ) -> StandardPngSource | None:
        del session_id, subject_id, view_kind
        return None

    def subject_png_cache_identity(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
    ) -> str | None:
        del session_id, subject_id, view_kind
        return None

    def verify_source_extrema(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        proof: StandardSourceExtremaProofV2,
    ) -> bool:
        if session_id != self._hierarchy.session_id:
            return False
        full_view = self._views.get((subject_id, view_kind))
        source_binding = self._source_bindings.get((subject_id, view_kind))
        return (
            full_view is not None
            and source_binding is not None
            and _recompute_source_extrema(
                full_view,
                source_artifact_digest=source_binding[0],
                source_content_digest=source_binding[1],
            )
            == proof
        )


def _bound_view(view: StandardPlotViewV2, maximum_points: int) -> StandardPlotViewV2:
    minimum_points = len(view.source_extrema.lanes)
    if not minimum_points <= maximum_points <= 2048:
        raise ValueError(
            "maximum_points must cover every source-backed receiver-path lane and be at most 2,048"
        )
    if view.returned_point_count <= maximum_points:
        return view
    if view.view_kind is StandardViewKindV2.WATERFALL:
        waterfall = _lane_extrema_preserving(
            view.waterfall_cells,
            maximum_points,
            lambda item: item.receiver_path_id,
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


def _recompute_source_extrema(
    view: StandardPlotViewV2,
    *,
    source_artifact_digest: str,
    source_content_digest: str,
) -> StandardSourceExtremaProofV2:
    return standard_source_extrema_proof_v2(
        view_kind=view.view_kind,
        receiver_path_ids=view.receiver_path_ids,
        source_artifact_digest=source_artifact_digest,
        source_content_digest=source_content_digest,
        series=view.series,
        waterfall_cells=view.waterfall_cells,
        cfo_observations=view.cfo_observations,
        trajectory_curves=view.trajectory_curves,
    )


def _bound_cfo_view(view: StandardPlotViewV2, maximum_points: int) -> StandardPlotViewV2:
    flattened = tuple(
        (
            "observation",
            index,
            -1,
            item,
            item.baseband_cfo_hz,
            item.receiver_path_id,
        )
        for index, item in enumerate(view.cfo_observations)
    ) + tuple(
        (
            "curve",
            curve_index,
            point_index,
            point,
            point.value,
            curve.receiver_path_id,
        )
        for curve_index, curve in enumerate(view.trajectory_curves)
        for point_index, point in enumerate(curve.points)
    )
    selected = _lane_extrema_preserving(
        flattened,
        maximum_points,
        lambda item: item[5],
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
    flattened = tuple(
        (
            series_index,
            point_index,
            point,
            series.receiver_path_id,
            point.value,
        )
        for series_index, series in enumerate(view.series)
        for point_index, point in enumerate(series.points)
    )
    if not flattened:
        return _validated_bound_copy(view, returned_point_count=0, series=())
    selected = _lane_extrema_preserving(
        flattened,
        maximum_points,
        lambda item: item[3],
        (lambda item: item[4],),
    )
    selected_indexes = {(item[0], item[1]) for item in selected}
    series_projection = tuple(
        series.model_copy(
            update={
                "points": tuple(
                    point
                    for point_index, point in enumerate(series.points)
                    if (series_index, point_index) in selected_indexes
                ),
                "truncated": series.source_point_count
                > sum(1 for index, _ in selected_indexes if index == series_index),
            }
        )
        for series_index, series in enumerate(view.series)
        if any(index == series_index for index, _ in selected_indexes)
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


def _lane_extrema_preserving[ValueT](
    values: tuple[ValueT, ...],
    maximum_points: int,
    lane: Callable[[ValueT], str],
    projections: tuple[Callable[[ValueT], float], ...],
) -> tuple[ValueT, ...]:
    if not values or len(values) <= maximum_points:
        return values
    mandatory_indexes: set[int] = set()
    for projection in projections:
        mandatory_indexes.add(min(range(len(values)), key=lambda index: projection(values[index])))
        mandatory_indexes.add(max(range(len(values)), key=lambda index: projection(values[index])))
    lane_ids = tuple(dict.fromkeys(lane(value) for value in values))
    lane_indexes = {
        next(
            (index for index in sorted(mandatory_indexes) if lane(values[index]) == lane_id),
            next(index for index, value in enumerate(values) if lane(value) == lane_id),
        )
        for lane_id in lane_ids
    }
    if len(lane_indexes) > maximum_points:
        raise ValueError("point budget cannot represent every source-backed receiver-path lane")
    selected_indexes = set(lane_indexes)
    for index in sorted(mandatory_indexes - selected_indexes):
        if len(selected_indexes) == maximum_points:
            break
        selected_indexes.add(index)
    available_indexes = tuple(
        index for index in range(len(values)) if index not in selected_indexes
    )
    extra_indexes = _evenly_spaced(
        available_indexes,
        maximum_points - len(selected_indexes),
    )
    final_indexes = sorted(selected_indexes | set(extra_indexes))
    return tuple(values[index] for index in final_indexes)


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
