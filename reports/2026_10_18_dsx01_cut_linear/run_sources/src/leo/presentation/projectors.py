"""Pure presentation-v1 projectors with explicit payload bounds."""

from __future__ import annotations

from collections.abc import Sequence

from leo.presentation.models import (
    PlotPointV1,
    ProductContentV1,
    RecordingDetailV1,
    RecordingSummaryV1,
)


def recording_summary_v1(detail: RecordingDetailV1) -> RecordingSummaryV1:
    """Project the detail contract into its stable search-row representation."""

    return RecordingSummaryV1(
        session_id=detail.session_id,
        title=detail.title,
        started_at=detail.started_at,
        duration_seconds=detail.duration_seconds,
        source_type=detail.source_type,
        tags=detail.tags,
        hold=detail.hold,
        capture_health=detail.capture_health,
        storage_state=detail.storage_state,
        profile_name=detail.profile.name,
        radio_count=len(detail.radios),
        analysis=detail.analysis,
    )


def decimate_product_points_v1(
    product_id: str,
    kind: str,
    raw_points: Sequence[object],
    metadata: dict[str, object],
    maximum_points: int,
) -> ProductContentV1:
    """Bound a registered plot artifact while retaining its endpoints."""

    if not 1 <= maximum_points <= 2048:
        raise ValueError("maximum_points must be between 1 and 2048")
    points = tuple(PlotPointV1.model_validate(item) for item in raw_points)
    run_id = metadata.get("run_id")
    if not isinstance(run_id, str):
        raise ValueError("plot metadata requires its analysis run ID")
    selected = _evenly_spaced(points, maximum_points)
    return ProductContentV1(
        product_id=product_id,
        analysis_run_id=run_id,
        kind=kind,
        source_point_count=len(points),
        returned_point_count=len(selected),
        truncated=len(selected) < len(points),
        points=selected,
        metadata=metadata,
    )


def _evenly_spaced(values: tuple[PlotPointV1, ...], maximum_points: int) -> tuple[PlotPointV1, ...]:
    if len(values) <= maximum_points:
        return values
    if maximum_points == 1:
        return (values[0],)
    last = len(values) - 1
    indexes = tuple(round(index * last / (maximum_points - 1)) for index in range(maximum_points))
    return tuple(values[index] for index in indexes)
