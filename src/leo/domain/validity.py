"""Deterministic validity inventory derivation from counter-authoritative gap maps."""

from __future__ import annotations

from leo.contracts.continuity import IqContinuityBoundaryV1, IqGapMapV1
from leo.contracts.digests import canonical_digest
from leo.contracts.validity import (
    ContinuitySegmentV1,
    DeviceAxisContentKind,
    ValidityInventoryV1,
    ValidityRunV1,
)
from leo.domain.gap_map import IqContinuityEvidenceError


def build_validity_inventory_v1(gap_map: IqGapMapV1) -> ValidityInventoryV1:
    """Expand one verified gap map into its canonical compact validity inventory."""

    segments: list[ContinuitySegmentV1] = []
    stored_cursor = 0
    device_cursor = 0
    segment_index = 0
    preceding_boundary = None

    for boundary in gap_map.boundaries:
        if boundary.segment_index != segment_index + 1:
            raise IqContinuityEvidenceError("gap-map segment indexes are not contiguous")
        observed_count = boundary.stored_sample_offset - stored_cursor
        if observed_count < 0:
            raise IqContinuityEvidenceError("gap-map stored coordinates regressed")
        if boundary.device_sample_offset != device_cursor + observed_count:
            raise IqContinuityEvidenceError(
                "gap-map stored and device coordinates disagree while deriving validity"
            )
        segments.append(
            _segment(
                segment_index=segment_index,
                device_sample_start=device_cursor,
                stored_sample_start=stored_cursor,
                observed_sample_count=observed_count,
                preceding_boundary=preceding_boundary,
            )
        )
        stored_cursor = boundary.stored_sample_offset
        device_cursor = boundary.device_sample_offset + boundary.missing_sample_count
        segment_index = boundary.segment_index
        preceding_boundary = boundary

    final_observed_count = gap_map.observed_sample_count - stored_cursor
    if final_observed_count < 0:
        raise IqContinuityEvidenceError("gap map exceeds its observed sample inventory")
    segments.append(
        _segment(
            segment_index=segment_index,
            device_sample_start=device_cursor,
            stored_sample_start=stored_cursor,
            observed_sample_count=final_observed_count,
            preceding_boundary=preceding_boundary,
        )
    )
    if device_cursor + final_observed_count != gap_map.device_span_sample_count:
        raise IqContinuityEvidenceError("gap-map validity segments do not close the device span")

    runs: list[ValidityRunV1] = []
    device_cursor = 0
    for segment in segments:
        if segment.device_sample_start > device_cursor:
            runs.append(
                ValidityRunV1(
                    run_index=len(runs),
                    device_sample_start=device_cursor,
                    sample_count=segment.device_sample_start - device_cursor,
                    content_kind=DeviceAxisContentKind.ZERO_FILL,
                )
            )
        if segment.observed_sample_count:
            runs.append(
                ValidityRunV1(
                    run_index=len(runs),
                    device_sample_start=segment.device_sample_start,
                    sample_count=segment.observed_sample_count,
                    content_kind=DeviceAxisContentKind.OBSERVED,
                    stored_sample_start=segment.stored_sample_start,
                    continuity_segment_index=segment.segment_index,
                )
            )
        device_cursor = segment.device_sample_stop

    return ValidityInventoryV1(
        stream_id=gap_map.stream_id,
        timeline_sha256=gap_map.timeline_sha256,
        gap_map_content_digest=canonical_digest(gap_map.model_dump(mode="json")),
        first_device_sample_counter=gap_map.first_device_sample_counter,
        logical_sample_count=gap_map.device_span_sample_count,
        observed_sample_count=gap_map.observed_sample_count,
        missing_sample_count=gap_map.missing_sample_count,
        continuity_boundary_count=len(gap_map.boundaries),
        runs=tuple(runs),
        segments=tuple(segments),
    )


def _segment(
    *,
    segment_index: int,
    device_sample_start: int,
    stored_sample_start: int,
    observed_sample_count: int,
    preceding_boundary: IqContinuityBoundaryV1 | None,
) -> ContinuitySegmentV1:
    if preceding_boundary is None:
        return ContinuitySegmentV1(
            segment_index=segment_index,
            device_sample_start=device_sample_start,
            device_sample_stop=device_sample_start + observed_sample_count,
            stored_sample_start=stored_sample_start,
            stored_sample_stop=stored_sample_start + observed_sample_count,
        )

    return ContinuitySegmentV1(
        segment_index=segment_index,
        device_sample_start=device_sample_start,
        device_sample_stop=device_sample_start + observed_sample_count,
        stored_sample_start=stored_sample_start,
        stored_sample_stop=stored_sample_start + observed_sample_count,
        preceding_missing_sample_count=preceding_boundary.missing_sample_count,
        preceding_boundary_reason=preceding_boundary.reason,
        preceding_boundary_header_sha256=preceding_boundary.header_evidence_sha256,
    )
