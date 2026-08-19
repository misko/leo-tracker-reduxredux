"""Versioned manifests for immutable compressed recording bundles."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.profile import CapturePlanV1, Tag
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1
from leo.contracts.states import (
    CaptureState,
    SampleFormat,
    SampleLayout,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)

Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


def _relative_bundle_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("bundle paths must be normalized relative POSIX paths")
    if str(path) != value:
        raise ValueError("bundle paths must use canonical POSIX spelling")
    return value


class TimingEstimateV1(ContractModel):
    """An honest time estimate with inclusive uncertainty bounds."""

    schema_version: Literal[1] = 1
    estimate_utc_ns: Annotated[int, Field(ge=0)]
    earliest_utc_ns: Annotated[int, Field(ge=0)]
    latest_utc_ns: Annotated[int, Field(ge=0)]
    method: TimingMethod

    @model_validator(mode="after")
    def _estimate_is_bounded(self) -> Self:
        if not self.earliest_utc_ns <= self.estimate_utc_ns <= self.latest_utc_ns:
            raise ValueError("timing estimate must lie inside its uncertainty interval")
        return self


class StreamTimingV1(ContractModel):
    schema_version: Literal[1] = 1
    release_target_monotonic_ns: Annotated[int, Field(ge=0)] | None = None
    release_observed_monotonic_ns: Annotated[int, Field(ge=0)] | None = None
    first_sample: TimingEstimateV1
    last_sample: TimingEstimateV1

    @model_validator(mode="after")
    def _times_are_ordered(self) -> Self:
        if self.first_sample.estimate_utc_ns > self.last_sample.estimate_utc_ns:
            raise ValueError("stream last-sample estimate precedes first sample")
        if (self.release_target_monotonic_ns is None) != (
            self.release_observed_monotonic_ns is None
        ):
            raise ValueError("release target and observation must appear together")
        return self


class RecordingChunkV1(ContractModel):
    schema_version: Literal[1] = 1
    chunk_index: Annotated[int, Field(ge=0)]
    segment_index: Annotated[int, Field(ge=0)] = 0
    relative_path: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    sample_start: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(gt=0)]
    uncompressed_bytes: Annotated[int, Field(gt=0)]
    compressed_bytes: Annotated[int, Field(gt=0)]
    uncompressed_sha256: Sha256Digest
    compressed_sha256: Sha256Digest
    sample_format: Literal[SampleFormat.CI16_LE] = SampleFormat.CI16_LE
    sample_layout: Literal[SampleLayout.SAMPLE_RECEIVER_IQ] = SampleLayout.SAMPLE_RECEIVER_IQ

    @field_validator("relative_path")
    @classmethod
    def _path_is_relative(cls, value: str) -> str:
        return _relative_bundle_path(value)


class ContinuitySummaryV1(ContractModel):
    schema_version: Literal[1] = 1
    refill_count: Annotated[int, Field(ge=0)]
    segment_count: Annotated[int, Field(ge=0)]
    gap_count: Annotated[int, Field(ge=0)] = 0
    missing_sample_count: Annotated[int, Field(ge=0)] = 0
    overflow_count: Annotated[int, Field(ge=0)] = 0
    sample_loss_observable: bool = False
    first_source_sequence: Annotated[int, Field(ge=0)] | None = None
    last_source_sequence: Annotated[int, Field(ge=0)] | None = None
    first_device_sample_counter: Annotated[int, Field(ge=0)] | None = None
    last_device_sample_counter: Annotated[int, Field(ge=0)] | None = None
    constant_iq_refill_count: Annotated[int, Field(ge=0)] = 0
    clipped_sample_count: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _summary_is_consistent(self) -> Self:
        if (self.first_source_sequence is None) != (self.last_source_sequence is None):
            raise ValueError("source sequence endpoints must appear together")
        if (self.first_device_sample_counter is None) != (self.last_device_sample_counter is None):
            raise ValueError("device-counter endpoints must appear together")
        if (
            self.first_source_sequence is not None
            and self.last_source_sequence is not None
            and self.first_source_sequence > self.last_source_sequence
        ):
            raise ValueError("source sequence regressed")
        if self.segment_count == 0 and self.refill_count:
            raise ValueError("non-empty continuity evidence requires a segment")
        if self.segment_count > self.refill_count:
            raise ValueError("continuity segments cannot exceed refill count")
        if self.sample_loss_observable and self.first_device_sample_counter is None:
            raise ValueError("observable sample loss requires device-counter evidence")
        return self


class RecordingStreamV1(ContractModel):
    schema_version: Literal[1] = 1
    stream_id: Identifier
    radio: RadioIdentityV1
    requested_settings: RadioSettingsV1
    applied_settings: RadioSettingsV1 | None = None
    state: StreamState
    requested_sample_count: Annotated[int, Field(gt=0)]
    captured_sample_count: Annotated[int, Field(ge=0)]
    timing: StreamTimingV1 | None = None
    chunks: tuple[RecordingChunkV1, ...] = ()
    timeline_relative_path: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=512),
    ] = None
    timeline_sha256: Sha256Digest | None = None
    continuity: ContinuitySummaryV1
    error: Annotated[str | None, StringConstraints(min_length=1, max_length=2048)] = None

    @field_validator("timeline_relative_path")
    @classmethod
    def _timeline_path_is_relative(cls, value: str | None) -> str | None:
        return None if value is None else _relative_bundle_path(value)

    @model_validator(mode="after")
    def _stream_is_consistent(self) -> Self:
        if (self.timeline_relative_path is None) != (self.timeline_sha256 is None):
            raise ValueError("timeline path and digest must appear together")
        geometry_settings = self.applied_settings or self.requested_settings
        receiver_count = len(geometry_settings.receiver_ids)
        expected_start = 0
        previous_segment = -1
        for expected_index, chunk in enumerate(self.chunks):
            if chunk.chunk_index != expected_index:
                raise ValueError("chunk indexes must be contiguous from zero")
            if chunk.sample_start != expected_start:
                raise ValueError("stored chunk sample ranges must be contiguous")
            if chunk.segment_index < previous_segment:
                raise ValueError("chunk continuity segments cannot regress")
            expected_bytes = chunk.sample_count * receiver_count * 4
            if chunk.uncompressed_bytes != expected_bytes:
                raise ValueError("chunk byte count disagrees with CI16 sample geometry")
            expected_start += chunk.sample_count
            previous_segment = chunk.segment_index
        if expected_start != self.captured_sample_count:
            raise ValueError("captured sample count disagrees with chunk inventory")
        if self.continuity.segment_count != (0 if not self.chunks else previous_segment + 1):
            raise ValueError("continuity segment count disagrees with chunks")
        if self.captured_sample_count > self.requested_sample_count:
            raise ValueError("captured sample count exceeds the request")
        if self.state is StreamState.COMPLETE:
            if (
                self.applied_settings is None
                or self.captured_sample_count != self.requested_sample_count
                or self.timing is None
            ):
                raise ValueError("complete stream must contain the full requested interval")
            if self.error is not None:
                raise ValueError("complete stream cannot contain an error")
        elif self.state is StreamState.PARTIAL:
            if not 0 < self.captured_sample_count < self.requested_sample_count:
                raise ValueError("partial stream must contain a strict subset of samples")
            if self.applied_settings is None or self.timing is None or self.error is None:
                raise ValueError("partial stream requires timing and an error explanation")
        elif self.captured_sample_count or self.chunks or self.timing is not None:
            raise ValueError("failed stream cannot publish normal IQ chunks or timing")
        elif self.error is None:
            raise ValueError("failed stream requires an error explanation")
        return self


class SynchronizationSummaryV1(ContractModel):
    schema_version: Literal[1] = 1
    requested_mode: SynchronizationMode
    effective_mode: SynchronizationMode
    grade: SynchronizationGrade
    stream_ids: tuple[Identifier, ...]
    release_target_monotonic_ns: Annotated[int, Field(ge=0)] | None = None
    estimated_start_skew_ns: Annotated[int, Field(ge=0)] | None = None
    start_skew_uncertainty_ns: Annotated[int, Field(ge=0)] | None = None
    estimated_overlap_ns: Annotated[int, Field(ge=0)] | None = None
    estimated_overlap_start_utc_ns: Annotated[int, Field(ge=0)] | None = None
    estimated_overlap_end_utc_ns: Annotated[int, Field(ge=0)] | None = None
    guaranteed_overlap_ns: Annotated[int, Field(ge=0)] | None = None
    overlap_fraction: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    phase_coherent: Literal[False] = False

    @model_validator(mode="after")
    def _summary_is_honest(self) -> Self:
        if not 1 <= len(self.stream_ids) <= 2 or len(set(self.stream_ids)) != len(self.stream_ids):
            raise ValueError("synchronization summary requires one or two unique streams")
        paired = self.effective_mode is SynchronizationMode.BEST_EFFORT
        if paired and len(self.stream_ids) != 2:
            raise ValueError("best-effort synchronization requires two requested streams")
        observations = (
            self.estimated_start_skew_ns,
            self.start_skew_uncertainty_ns,
            self.estimated_overlap_ns,
            self.estimated_overlap_start_utc_ns,
            self.estimated_overlap_end_utc_ns,
            self.guaranteed_overlap_ns,
            self.overlap_fraction,
        )
        if not paired and any(value is not None for value in observations):
            raise ValueError("single-radio summaries cannot claim cross-radio observations")
        if paired and self.grade is SynchronizationGrade.NOT_REQUESTED:
            raise ValueError("paired synchronization cannot be graded not-requested")
        if not paired and self.grade is not SynchronizationGrade.NOT_REQUESTED:
            raise ValueError("single-radio synchronization grade must be not-requested")
        if (self.estimated_overlap_start_utc_ns is None) != (
            self.estimated_overlap_end_utc_ns is None
        ):
            raise ValueError("estimated overlap endpoints must appear together")
        if (
            self.estimated_overlap_start_utc_ns is not None
            and self.estimated_overlap_end_utc_ns is not None
            and self.estimated_overlap_start_utc_ns > self.estimated_overlap_end_utc_ns
        ):
            raise ValueError("estimated overlap interval is reversed")
        if (
            self.guaranteed_overlap_ns is not None
            and self.estimated_overlap_ns is not None
            and self.guaranteed_overlap_ns > self.estimated_overlap_ns
        ):
            raise ValueError("guaranteed overlap cannot exceed estimated overlap")
        return self


class ProducerV1(ContractModel):
    schema_version: Literal[1] = 1
    name: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    version: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    source_revision: Annotated[str | None, StringConstraints(min_length=1, max_length=128)] = None


class HostIdentityV1(ContractModel):
    schema_version: Literal[1] = 1
    hostname: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    machine_id: Annotated[str | None, StringConstraints(min_length=1, max_length=128)] = None
    operating_system: Annotated[str | None, StringConstraints(min_length=1, max_length=256)] = None


class CompressionSettingsV1(ContractModel):
    schema_version: Literal[1] = 1
    policy_id: Annotated[
        str,
        StringConstraints(min_length=1, max_length=96, pattern=r"^[a-z0-9][a-z0-9._-]*$"),
    ]
    codec: Literal["zstd"] = "zstd"
    level: Annotated[int, Field(ge=-10, le=22)] = 3
    target_uncompressed_bytes: Annotated[int, Field(gt=0)] = 128 * 1024 * 1024


class CalibrationReferenceV1(ContractModel):
    schema_version: Literal[1] = 1
    calibration_id: Identifier
    kind: Annotated[str, StringConstraints(min_length=1, max_length=96)]
    digest: Sha256Digest


class RecordingManifestV1(ContractModel):
    """Filesystem reconstruction contract written last when a bundle commits."""

    schema_version: Literal[1] = 1
    session_id: Identifier
    state: Literal[CaptureState.COMMITTED, CaptureState.DEGRADED]
    source_type: SourceType
    created_utc_ns: Annotated[int, Field(ge=0)]
    finalized_utc_ns: Annotated[int, Field(ge=0)]
    capture_plan: CapturePlanV1
    tags: tuple[Tag, ...]
    streams: tuple[RecordingStreamV1, ...]
    synchronization: SynchronizationSummaryV1
    compression: CompressionSettingsV1
    calibrations: tuple[CalibrationReferenceV1, ...] = ()
    host: HostIdentityV1
    producer: ProducerV1

    @field_validator("tags")
    @classmethod
    def _tags_are_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("manifest tags must be unique and sorted")
        return value

    @model_validator(mode="after")
    def _manifest_is_consistent(self) -> Self:
        if self.finalized_utc_ns < self.created_utc_ns:
            raise ValueError("manifest finalization precedes creation")
        if self.source_type is not self.capture_plan.source_type:
            raise ValueError("manifest source type disagrees with capture plan")
        if not set(self.capture_plan.profile_revision.profile.tags).issubset(self.tags):
            raise ValueError("manifest must retain every default profile tag")
        if self.compression.policy_id != self.capture_plan.profile_revision.profile.storage_policy:
            raise ValueError("manifest compression policy disagrees with capture plan")
        if not self.streams:
            raise ValueError("a committed or degraded manifest requires stream outcomes")
        stream_ids = tuple(stream.stream_id for stream in self.streams)
        if len(set(stream_ids)) != len(stream_ids):
            raise ValueError("manifest stream IDs must be unique")
        if stream_ids != self.synchronization.stream_ids:
            raise ValueError("synchronization stream order must match manifest streams")
        if (
            self.synchronization.requested_mode
            is not self.capture_plan.requested_synchronization_mode
            or self.synchronization.effective_mode
            is not self.capture_plan.effective_synchronization_mode
        ):
            raise ValueError("synchronization summary disagrees with capture plan")
        radio_ids = tuple(stream.radio.radio_id for stream in self.streams)
        if radio_ids != self.capture_plan.radio_ids:
            raise ValueError("stream radio order must match capture plan")
        all_complete = all(stream.state is StreamState.COMPLETE for stream in self.streams)
        if self.state is CaptureState.COMMITTED and not all_complete:
            raise ValueError("committed manifest requires all streams to complete")
        if self.state is CaptureState.DEGRADED and all_complete:
            raise ValueError("degraded manifest requires at least one incomplete stream")
        if not any(stream.captured_sample_count for stream in self.streams):
            raise ValueError("a published manifest requires at least one captured sample")
        return self
