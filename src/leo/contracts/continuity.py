"""Additive contracts for counter-authoritative IQ continuity evidence."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest

StreamIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class IqContinuityBoundaryV1(ContractModel):
    """One validated continuity break before the next observed refill."""

    schema_version: Literal[1] = 1
    segment_index: Annotated[int, Field(ge=1)]
    stored_sample_offset: Annotated[int, Field(ge=1)]
    device_sample_offset: Annotated[int, Field(ge=1)]
    expected_device_sample_counter: Annotated[int, Field(ge=0)]
    actual_device_sample_counter: Annotated[int, Field(ge=0)]
    header_evidence_sha256: Sha256Digest
    observed_counter_gap_sample_count: Annotated[int, Field(ge=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    reason: Literal[
        "counter_gap",
        "overflow_flag",
        "counter_gap_and_overflow",
        "terminal_counter_gap",
        "terminal_counter_gap_and_overflow",
    ]

    @model_validator(mode="after")
    def _counter_delta_matches_reason(self) -> Self:
        if self.actual_device_sample_counter < self.expected_device_sample_counter:
            raise ValueError("continuity boundary device counter regressed")
        delta = self.actual_device_sample_counter - self.expected_device_sample_counter
        if delta != self.observed_counter_gap_sample_count:
            raise ValueError("continuity boundary counter delta disagrees with observed gap")
        has_gap = self.missing_sample_count > 0
        gap_reasons = {
            "counter_gap",
            "counter_gap_and_overflow",
            "terminal_counter_gap",
            "terminal_counter_gap_and_overflow",
        }
        if has_gap != (self.reason in gap_reasons):
            raise ValueError("continuity boundary reason disagrees with its counter gap")
        if not has_gap and self.reason != "overflow_flag":
            raise ValueError("zero-length continuity boundary must name an overflow flag")
        is_terminal = self.reason.startswith("terminal_")
        if is_terminal:
            if not 0 < self.missing_sample_count <= self.observed_counter_gap_sample_count:
                raise ValueError("terminal logical gap must fit inside the observed counter gap")
        elif self.missing_sample_count != self.observed_counter_gap_sample_count:
            raise ValueError("interior logical and observed counter gaps must match")
        return self


class IqTerminalRejectedRefillV1(ContractModel):
    """Header-bound discontinuity evidence for IQ rejected by a full host queue.

    This event is deliberately outside ``boundaries``: no rejected IQ bytes are
    part of the reconstructable device span.  Its counter gap and overflow flag
    remain first-class evidence and must still be reported operationally.
    """

    schema_version: Literal[1] = 1
    stored_sample_offset: Annotated[int, Field(ge=1)]
    device_sample_offset: Annotated[int, Field(ge=1)]
    expected_device_sample_counter: Annotated[int, Field(ge=0)]
    actual_device_sample_counter: Annotated[int, Field(ge=0)]
    source_sequence: Annotated[int, Field(ge=0)]
    returned_sample_count: Annotated[int, Field(gt=0)]
    header_evidence_sha256: Sha256Digest
    observed_counter_gap_sample_count: Annotated[int, Field(ge=0)]
    overflow_observed: bool = False
    reason: Literal[
        "queue_full_contiguous",
        "queue_full_counter_gap",
        "queue_full_overflow",
        "queue_full_counter_gap_and_overflow",
    ]

    @model_validator(mode="after")
    def _header_classification_is_exact(self) -> Self:
        delta = self.actual_device_sample_counter - self.expected_device_sample_counter
        if delta < 0 or delta != self.observed_counter_gap_sample_count:
            raise ValueError("terminal rejected refill counter gap is inconsistent")
        if delta and self.overflow_observed:
            expected_reason = "queue_full_counter_gap_and_overflow"
        elif delta:
            expected_reason = "queue_full_counter_gap"
        elif self.overflow_observed:
            expected_reason = "queue_full_overflow"
        else:
            expected_reason = "queue_full_contiguous"
        if self.reason != expected_reason:
            raise ValueError("terminal rejected refill reason is inconsistent")
        return self


class IqGapMapV1(ContractModel):
    """Hash-bound mapping from immutable stored IQ onto the FPGA sample axis."""

    schema_version: Literal[1] = 1
    stream_id: StreamIdentifier
    timeline_sha256: Sha256Digest
    first_device_sample_counter: Annotated[int, Field(ge=0)]
    capture_start_overflow: bool = False
    capture_start_header_evidence_sha256: Sha256Digest | None = None
    observed_sample_count: Annotated[int, Field(gt=0)]
    device_span_sample_count: Annotated[int, Field(gt=0)]
    segment_count: Annotated[int, Field(gt=0)]
    boundaries: tuple[IqContinuityBoundaryV1, ...] = ()
    terminal_rejected_refill: IqTerminalRejectedRefillV1 | None = None

    @property
    def missing_sample_count(self) -> int:
        return sum(item.missing_sample_count for item in self.boundaries)

    @model_validator(mode="after")
    def _inventory_is_consistent(self) -> Self:
        if self.capture_start_overflow != (
            self.capture_start_header_evidence_sha256 is not None
        ):
            raise ValueError("capture-start overflow and header digest must appear together")
        if self.device_span_sample_count != self.observed_sample_count + self.missing_sample_count:
            raise ValueError("device span must equal observed plus missing samples")
        if self.segment_count != len(self.boundaries) + 1:
            raise ValueError("segment count must equal continuity boundaries plus one")
        previous_stored = 0
        previous_device = 0
        for expected_segment, boundary in enumerate(self.boundaries, start=1):
            if boundary.segment_index != expected_segment:
                raise ValueError("continuity boundary segment indexes must be contiguous")
            if boundary.stored_sample_offset < previous_stored:
                raise ValueError("continuity boundary stored offsets regressed")
            if boundary.device_sample_offset < previous_device:
                raise ValueError("continuity boundary device offsets regressed")
            if boundary.stored_sample_offset > self.observed_sample_count:
                raise ValueError("continuity boundary exceeds observed IQ")
            if boundary.device_sample_offset >= self.device_span_sample_count:
                raise ValueError("continuity boundary exceeds device-time span")
            expected_counter = self.first_device_sample_counter + boundary.device_sample_offset
            if boundary.expected_device_sample_counter != expected_counter:
                raise ValueError("continuity boundary device offset disagrees with its counter")
            previous_stored = boundary.stored_sample_offset
            previous_device = boundary.device_sample_offset
        terminal = self.terminal_rejected_refill
        if terminal is not None:
            if terminal.stored_sample_offset != self.observed_sample_count:
                raise ValueError("terminal rejected refill must follow all stored IQ")
            if terminal.device_sample_offset != self.device_span_sample_count:
                raise ValueError("terminal rejected refill must follow the stored device span")
            expected_counter = self.first_device_sample_counter + self.device_span_sample_count
            if terminal.expected_device_sample_counter != expected_counter:
                raise ValueError("terminal rejected refill offset disagrees with its counter")
        return self
