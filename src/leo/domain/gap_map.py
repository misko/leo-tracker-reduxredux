"""Derive an immutable device-sample gap map from validated IQ metadata."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from leo.contracts.continuity import IqContinuityBoundaryV1, IqGapMapV1
from leo.contracts.radio import IqBlockMetadataV1
from leo.contracts.recording import ContinuitySummaryV2
from leo.contracts.states import ContinuityStatus

BoundaryReason = Literal[
    "counter_gap",
    "overflow_flag",
    "counter_gap_and_overflow",
    "terminal_counter_gap",
    "terminal_counter_gap_and_overflow",
]


class IqContinuityEvidenceError(ValueError):
    """Persisted or streamed IQ continuity evidence is internally inconsistent."""


def build_iq_gap_map(
    *,
    stream_id: str,
    timeline_sha256: str,
    timeline: Iterable[IqBlockMetadataV1],
    continuity: ContinuitySummaryV2 | None = None,
) -> IqGapMapV1:
    """Validate one stored timeline and derive its exact device-sample gap map."""

    records = tuple(timeline)
    if not records:
        raise IqContinuityEvidenceError("cannot build a gap map from an empty timeline")
    first_counter = records[0].device_sample_counter
    if first_counter is None:
        raise IqContinuityEvidenceError("gap-map construction requires FPGA sample counters")
    if records[0].session_sample_start != 0:
        raise IqContinuityEvidenceError("stored IQ timeline must begin at sample zero")
    if records[0].missing_samples_before:
        raise IqContinuityEvidenceError("the first capture refill cannot declare a prior gap")

    observed_end = 0
    previous_device_end: int | None = None
    boundaries: list[IqContinuityBoundaryV1] = []
    for record in records:
        if record.session_sample_start != observed_end:
            raise IqContinuityEvidenceError("stored IQ timeline is not contiguous")
        counter = record.device_sample_counter
        if counter is None:
            raise IqContinuityEvidenceError("timeline lost FPGA counter observability")
        if previous_device_end is None:
            missing = 0
        else:
            missing = counter - previous_device_end
            if missing < 0:
                raise IqContinuityEvidenceError("FPGA sample counter repeated or regressed")
        if record.missing_samples_before != missing:
            raise IqContinuityEvidenceError(
                "declared missing samples disagree with the FPGA counter delta"
            )
        overflow = record.overflow_observed or record.continuity is ContinuityStatus.OVERFLOW
        if missing and record.continuity is not ContinuityStatus.GAP_BEFORE:
            raise IqContinuityEvidenceError("positive counter gap lacks GAP_BEFORE status")
        if not missing and record.continuity is ContinuityStatus.GAP_BEFORE:
            raise IqContinuityEvidenceError("GAP_BEFORE status lacks a positive counter gap")
        if previous_device_end is not None and (missing or overflow):
            reason: BoundaryReason
            if missing and overflow:
                reason = "counter_gap_and_overflow"
            elif missing:
                reason = "counter_gap"
            else:
                reason = "overflow_flag"
            boundaries.append(
                IqContinuityBoundaryV1(
                    segment_index=len(boundaries) + 1,
                    stored_sample_offset=record.session_sample_start,
                    device_sample_offset=previous_device_end - first_counter,
                    expected_device_sample_counter=previous_device_end,
                    actual_device_sample_counter=counter,
                    observed_counter_gap_sample_count=missing,
                    missing_sample_count=missing,
                    reason=reason,
                )
            )
        observed_end += record.sample_count
        previous_device_end = counter + record.sample_count

    assert previous_device_end is not None
    if continuity is not None and continuity.terminal_gap is not None:
        terminal = continuity.terminal_gap
        expected_counter = previous_device_end
        if terminal.expected_device_sample_counter != expected_counter:
            raise IqContinuityEvidenceError("terminal gap does not begin after observed IQ")
        if terminal.stream_generation != getattr(records[-1], "stream_generation", None):
            raise IqContinuityEvidenceError("terminal gap changed stream generation")
        terminal_reason: BoundaryReason = (
            "terminal_counter_gap_and_overflow"
            if terminal.overflow_observed
            else "terminal_counter_gap"
        )
        boundaries.append(
            IqContinuityBoundaryV1(
                segment_index=len(boundaries) + 1,
                stored_sample_offset=observed_end,
                device_sample_offset=expected_counter - first_counter,
                expected_device_sample_counter=expected_counter,
                actual_device_sample_counter=terminal.actual_device_sample_counter,
                observed_counter_gap_sample_count=terminal.actual_missing_sample_count,
                missing_sample_count=terminal.in_span_missing_sample_count,
                reason=terminal_reason,
            )
        )
        previous_device_end += terminal.in_span_missing_sample_count

    result = IqGapMapV1(
        stream_id=stream_id,
        timeline_sha256=timeline_sha256,
        first_device_sample_counter=first_counter,
        observed_sample_count=observed_end,
        device_span_sample_count=previous_device_end - first_counter,
        segment_count=len(boundaries) + 1,
        boundaries=tuple(boundaries),
    )
    if continuity is not None:
        if continuity.observed_sample_count != result.observed_sample_count:
            raise IqContinuityEvidenceError("continuity summary disagrees with observed IQ")
        if continuity.device_span_sample_count != result.device_span_sample_count:
            raise IqContinuityEvidenceError("continuity summary disagrees with device span")
        if continuity.missing_sample_count != result.missing_sample_count:
            raise IqContinuityEvidenceError("continuity summary disagrees with missing samples")
        gap_count = sum(boundary.missing_sample_count > 0 for boundary in result.boundaries)
        if continuity.gap_count != gap_count:
            raise IqContinuityEvidenceError("continuity summary disagrees with gap count")
        overflow_count = sum(
            boundary.reason
            in {
                "overflow_flag",
                "counter_gap_and_overflow",
                "terminal_counter_gap_and_overflow",
            }
            for boundary in result.boundaries
        )
        if continuity.overflow_count != overflow_count:
            raise IqContinuityEvidenceError("continuity summary disagrees with overflow count")
        if continuity.first_device_sample_counter != result.first_device_sample_counter:
            raise IqContinuityEvidenceError("continuity summary disagrees with first counter")
    return result
