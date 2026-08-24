"""Versioned manifests for immutable compressed recording bundles."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.profile import CapturePlanV1, CapturePlanV2, Tag
from leo.contracts.radio import IqBlockMetadataV2, RadioIdentityV1, RadioSettingsV1
from leo.contracts.states import (
    CaptureState,
    ContinuityStatus,
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


class TerminalGapEvidenceV1(ContractModel):
    """A validated refill header whose IQ begins beyond the requested device interval."""

    schema_version: Literal[1] = 1
    expected_device_sample_counter: Annotated[int, Field(ge=0)]
    actual_device_sample_counter: Annotated[int, Field(ge=0)]
    actual_missing_sample_count: Annotated[int, Field(gt=0)]
    in_span_missing_sample_count: Annotated[int, Field(gt=0)]
    source_sequence: Annotated[int, Field(ge=0)]
    returned_sample_count: Annotated[int, Field(gt=0)]
    stream_generation: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    metadata_abi_version: Annotated[int, Field(ge=1)]
    metadata_flags: Annotated[int, Field(ge=0)]
    overflow_observed: bool = False
    hardware_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    header: IqBlockMetadataV2

    @model_validator(mode="after")
    def _terminal_gap_is_exact(self) -> Self:
        if self.actual_device_sample_counter - self.expected_device_sample_counter != (
            self.actual_missing_sample_count
        ):
            raise ValueError("terminal gap counters disagree with the exact missing count")
        if self.in_span_missing_sample_count > self.actual_missing_sample_count:
            raise ValueError("in-span terminal gap cannot exceed the observed hardware gap")
        if (
            self.header.device_sample_counter != self.actual_device_sample_counter
            or self.header.missing_samples_before != self.actual_missing_sample_count
            or self.header.source_sequence != self.source_sequence
            or self.header.sample_count != self.returned_sample_count
            or self.header.stream_generation != self.stream_generation
            or self.header.metadata_abi_version != self.metadata_abi_version
            or self.header.metadata_flags != self.metadata_flags
            or self.header.overflow_observed != self.overflow_observed
            or self.header.hardware_metadata != self.hardware_metadata
        ):
            raise ValueError("terminal gap summary disagrees with its exact returned header")
        return self


class ContinuitySummaryV2(ContinuitySummaryV1):
    """Validated device-axis closure and receive-queue telemetry."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    observed_sample_count: Annotated[int, Field(ge=0)]
    device_span_sample_count: Annotated[int, Field(ge=0)]
    kernel_buffers: Annotated[int, Field(ge=2, le=64)]
    metadata_abi_version: Annotated[int, Field(ge=1)] | None = None
    validated_stream_generation: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=128),
    ] = None
    queue_capacity_refills: Annotated[int, Field(ge=1, le=256)]
    queue_high_water_refills: Annotated[int, Field(ge=0)]
    enqueue_failure_count: Annotated[int, Field(ge=0)] = 0
    maximum_refill_service_interval_ns: Annotated[int, Field(ge=0)] = 0
    terminal_gap: TerminalGapEvidenceV1 | None = None
    terminal_enqueue_failure: IqBlockMetadataV2 | None = None
    terminal_rejected_gap_count: Annotated[int, Field(ge=0, le=1)] = 0
    terminal_rejected_missing_sample_count: Annotated[int, Field(ge=0)] = 0
    terminal_rejected_overflow_count: Annotated[int, Field(ge=0, le=1)] = 0

    @model_validator(mode="after")
    def _v2_summary_is_closed(self) -> Self:
        if self.device_span_sample_count != (
            self.observed_sample_count + self.missing_sample_count
        ):
            raise ValueError("device span must equal observed plus exactly missing samples")
        if self.queue_high_water_refills > self.queue_capacity_refills:
            raise ValueError("queue high-water exceeds configured capacity")
        if self.refill_count:
            if not self.sample_loss_observable:
                raise ValueError("non-empty V2 continuity must contain a validated chain")
            if self.validated_stream_generation is None or self.metadata_abi_version is None:
                raise ValueError("validated V2 continuity requires generation and metadata ABI")
        elif self.sample_loss_observable or self.validated_stream_generation is not None:
            raise ValueError("empty V2 continuity cannot claim a validated chain")
        if self.terminal_gap is not None:
            if self.gap_count == 0:
                raise ValueError("terminal gap evidence requires a declared gap")
            if self.terminal_gap.stream_generation != self.validated_stream_generation:
                raise ValueError("terminal gap generation disagrees with validated chain")
        if self.terminal_gap is not None and self.terminal_enqueue_failure is not None:
            raise ValueError("capture cannot end with both terminal-gap and enqueue-failure events")
        if (self.enqueue_failure_count > 0) != (self.terminal_enqueue_failure is not None):
            raise ValueError(
                "enqueue failure count and terminal header evidence must appear together"
            )
        if self.enqueue_failure_count > 1:
            raise ValueError("capture must terminate at the first enqueue failure")
        if self.terminal_enqueue_failure is not None:
            terminal = self.terminal_enqueue_failure
            if (
                terminal.stream_generation != self.validated_stream_generation
                or terminal.metadata_abi_version != self.metadata_abi_version
                or terminal.kernel_buffers != self.kernel_buffers
            ):
                raise ValueError(
                    "terminal enqueue header disagrees with validated capture identity"
                )
            if terminal.session_sample_start != self.observed_sample_count:
                raise ValueError("terminal enqueue header must begin after all stored IQ")
            if self.last_device_sample_counter is None:
                raise ValueError("terminal enqueue header requires a stored device-counter chain")
            expected_counter = self.last_device_sample_counter + 1
            if terminal.device_sample_counter != expected_counter + terminal.missing_samples_before:
                raise ValueError("terminal enqueue header does not follow stored device time")
            expected_status = (
                ContinuityStatus.GAP_BEFORE
                if terminal.missing_samples_before
                else (
                    ContinuityStatus.OVERFLOW
                    if terminal.overflow_observed
                    else ContinuityStatus.CONTIGUOUS
                )
            )
            if terminal.continuity is not expected_status:
                raise ValueError("terminal enqueue header has an inconsistent continuity status")
            expected_rejected = (
                int(terminal.missing_samples_before > 0),
                terminal.missing_samples_before,
                int(terminal.overflow_observed),
            )
        else:
            expected_rejected = (0, 0, 0)
        declared_rejected = (
            self.terminal_rejected_gap_count,
            self.terminal_rejected_missing_sample_count,
            self.terminal_rejected_overflow_count,
        )
        if declared_rejected != expected_rejected:
            raise ValueError("terminal rejected-refill aggregates disagree with its header")
        return self

    @property
    def total_observed_gap_count(self) -> int:
        """All proven counter gaps, including the terminal refill rejected by the queue."""

        return self.gap_count + self.terminal_rejected_gap_count

    @property
    def total_observed_missing_sample_count(self) -> int:
        """All counter-proven missing samples, including evidence beyond stored IQ."""

        return self.missing_sample_count + self.terminal_rejected_missing_sample_count

    @property
    def total_observed_overflow_count(self) -> int:
        """All observed overflow flags, including the terminal rejected refill."""

        return self.overflow_count + self.terminal_rejected_overflow_count


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
        if self.schema_version != 1:
            return self
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


class RecordingStreamV2(RecordingStreamV1):
    """Observed IQ inventory whose requested duration is on the device axis."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    continuity: ContinuitySummaryV2
    gap_map_relative_path: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=512),
    ] = None
    gap_map_sha256: Sha256Digest | None = None

    @field_validator("gap_map_relative_path")
    @classmethod
    def _gap_map_path_is_relative(cls, value: str | None) -> str | None:
        return None if value is None else _relative_bundle_path(value)

    @model_validator(mode="after")
    def _v2_stream_state_is_truthful(self) -> Self:
        if (self.gap_map_relative_path is None) != (self.gap_map_sha256 is None):
            raise ValueError("gap-map path and digest must appear together")
        if self.continuity.observed_sample_count != self.captured_sample_count:
            raise ValueError("observed sample summary disagrees with stored IQ inventory")
        integrity_loss = (
            self.continuity.gap_count > 0
            or self.continuity.overflow_count > 0
            or self.continuity.enqueue_failure_count > 0
            or self.continuity.device_span_sample_count != self.requested_sample_count
        )
        if self.state is StreamState.COMPLETE:
            if (
                self.applied_settings is None
                or self.captured_sample_count != self.requested_sample_count
                or self.timing is None
                or self.error is not None
                or integrity_loss
                or self.gap_map_relative_path is None
            ):
                raise ValueError("complete V2 stream requires a validated lossless device span")
        elif self.state is StreamState.PARTIAL:
            if self.captured_sample_count <= 0:
                raise ValueError("partial V2 stream must preserve observed IQ")
            if (
                self.applied_settings is None
                or self.timing is None
                or self.error is None
                or self.gap_map_relative_path is None
            ):
                raise ValueError("partial V2 stream requires timing and an error explanation")
            if not integrity_loss and self.captured_sample_count == self.requested_sample_count:
                raise ValueError("partial V2 stream requires incomplete or degraded integrity")
        elif (
            self.captured_sample_count
            or self.chunks
            or self.timing is not None
            or self.gap_map_relative_path is not None
        ):
            raise ValueError("failed V2 stream cannot publish normal IQ chunks or timing")
        elif self.error is None:
            raise ValueError("failed V2 stream requires an error explanation")
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


class RecordingManifestV2(RecordingManifestV1):
    """Recording bundle rooted in a persisted counter-authoritative capture plan."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    capture_plan: CapturePlanV2
    streams: tuple[RecordingStreamV2, ...]


RecordingManifestContract = Annotated[
    RecordingManifestV1 | RecordingManifestV2,
    Field(discriminator="schema_version"),
]
_RECORDING_MANIFEST_ADAPTER: TypeAdapter[RecordingManifestContract] = TypeAdapter(
    RecordingManifestContract
)


def parse_recording_manifest_json(payload: bytes | str) -> RecordingManifestV1:
    """Decode every supported immutable recording-manifest major version."""

    return _RECORDING_MANIFEST_ADAPTER.validate_json(payload)


def parse_recording_manifest(value: object) -> RecordingManifestV1:
    """Validate a Python document against every supported manifest version."""

    return _RECORDING_MANIFEST_ADAPTER.validate_python(value)
