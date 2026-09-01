"""Versioned device-buffer intent and evidence inside existing profile/timeline ports.

The canonical profile tag is part of the profile digest.  Runtime evidence lives
in the timeline's extensible hardware_metadata envelope, itself manifest-hashed.
No published profile, plan, or recording schema is widened.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.profile import CaptureProfileV1, CaptureProfileV2

DDR_RING_PROFILE_TAG_V1 = "DEVICE_BUFFER:DDR_RING_FINITE_200M_V1"
DDR_RING_EVIDENCE_KEY_V1 = "device_buffer_evidence_v1"
DDR_RING_BYTES_V1 = 200_000_000
DDR_RING_REFILL_SAMPLES_V1 = 1_000_000
DIRECT_ASYNC_PROFILE_TAG_V1 = "DEVICE_BUFFER:DIRECT_ASYNC_SEGMENTED_V1"
DIRECT_ASYNC_EVIDENCE_KEY_V1 = "direct_async_evidence_v1"
DIRECT_ASYNC_FRAME_SAMPLES_V1 = 1_048_576
DIRECT_ASYNC_SEGMENT_FRAMES_V1 = 64
DIRECT_ASYNC_KERNEL_BUFFERS_V1 = 15
DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V2 = "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V2"
DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V2 = "direct_async_ram_drop_evidence_v2"
DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V3 = "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V3"
DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V3 = "direct_async_ram_drop_evidence_v3"
DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V4 = "DEVICE_BUFFER:DIRECT_ASYNC_RAM_DROP_V4"
DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V4 = "direct_async_ram_drop_evidence_v4"
DIRECT_ASYNC_EXACT_DMA_DROP_PROFILE_TAG_V5 = "DEVICE_BUFFER:DIRECT_ASYNC_EXACT_DMA_DROP_V5"
DIRECT_ASYNC_EXACT_DMA_DROP_EVIDENCE_KEY_V5 = "direct_async_exact_dma_drop_evidence_v5"
DIRECT_ASYNC_FRAME_SAMPLES_V2 = 1_048_576
DIRECT_ASYNC_MAXIMUM_SEGMENT_FRAMES_V2 = 4_096
DIRECT_ASYNC_KERNEL_BUFFERS_V2 = 12
DIRECT_ASYNC_RAM_REQUESTED_BYTES_V2 = 200_000_000
DIRECT_ASYNC_KERNEL_BUFFERS_V3 = 11
DIRECT_ASYNC_RAM_REQUESTED_BYTES_V3 = 134_217_728
DIRECT_ASYNC_MAXIMUM_SEGMENT_FRAMES_V4 = 64
DIRECT_ASYNC_FRAME_SAMPLES_V5 = 1_000_000
DIRECT_ASYNC_MAXIMUM_SEGMENT_FRAMES_V5 = 4_096
DIRECT_ASYNC_KERNEL_BUFFERS_V5 = 50
DIRECT_ASYNC_DMA_BYTES_V5 = 200_000_000


class DeviceBufferRequestV1(ContractModel):
    schema_version: Literal[1] = 1
    mode: Literal["finite_ddr_ring"] = "finite_ddr_ring"
    requested_bytes: Annotated[int, Field(gt=0)]
    target_frames: Annotated[int, Field(gt=0)]
    frame_samples: Annotated[int, Field(gt=0)]
    receiver_count: Literal[1] = 1
    requested_device_samples: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _geometry_closes(self) -> Self:
        if self.requested_bytes % (self.frame_samples * 4):
            raise ValueError("ring byte budget must contain an exact number of whole frames")
        if self.target_frames * self.frame_samples != self.requested_device_samples:
            raise ValueError("finite ring target must exactly cover the requested nominal samples")
        return self

    @property
    def capacity_frames(self) -> int:
        return self.requested_bytes // (self.frame_samples * 4)


class DdrRingStatusV1(ContractModel):
    schema_version: Literal[1] = 1
    state: str
    terminal_reason: str
    error_code: int
    requested_capacity_iq_bytes: Annotated[int, Field(gt=0)]
    admitted_capacity_iq_bytes: Annotated[int, Field(gt=0)]
    target_frames: Annotated[int, Field(gt=0)]
    produced_frames: Annotated[int, Field(ge=0)]
    consumed_frames: Annotated[int, Field(ge=0)]
    high_water_frames: Annotated[int, Field(ge=0)]
    wrap_count: Annotated[int, Field(ge=0)]
    producer_position: Annotated[int, Field(ge=0)]
    consumer_position: Annotated[int, Field(ge=0)]
    last_contiguous_sample_sequence: Annotated[int, Field(ge=0)] | None = None
    first_unavailable_sample_sequence: Annotated[int, Field(ge=0)] | None = None

    def require_complete(self, request: DeviceBufferRequestV1) -> None:
        if (self.state, self.terminal_reason, self.error_code) != (
            "complete",
            "target_complete",
            0,
        ):
            raise ValueError("DDR ring did not reach clean target_complete")
        if not (
            self.produced_frames
            == self.consumed_frames
            == self.target_frames
            == request.target_frames
        ):
            raise ValueError("DDR ring target/producer/consumer frame counts disagree")
        if (
            self.requested_capacity_iq_bytes != request.requested_bytes
            or self.admitted_capacity_iq_bytes != request.requested_bytes
            or not 1 <= self.high_water_frames <= request.capacity_frames
        ):
            raise ValueError("DDR ring admission or high-water disagrees with request")


class DeviceBufferEvidenceV1(ContractModel):
    schema_version: Literal[1] = 1
    request: DeviceBufferRequestV1
    status: DdrRingStatusV1
    returned_frames: Annotated[int, Field(gt=0)]
    returned_device_span_samples: Annotated[int, Field(gt=0)]
    protected_prefix_frames: Annotated[int, Field(gt=0)]
    protected_prefix_bytes: Annotated[int, Field(gt=0)]
    protected_prefix_contiguous: Literal[True] = True
    stored_observed_samples: Annotated[int, Field(gt=0)]
    drained_outside_window_samples: Annotated[int, Field(ge=0)]
    host_ingestion: Literal["bounded_queue_raw_spool_v1"] = "bounded_queue_raw_spool_v1"

    @model_validator(mode="after")
    def _evidence_closes(self) -> Self:
        self.status.require_complete(self.request)
        if self.returned_frames != self.request.target_frames:
            raise ValueError("returned frame count disagrees with ring target")
        expected_prefix = min(self.request.capacity_frames, self.request.target_frames)
        if (
            self.protected_prefix_frames != expected_prefix
            or self.protected_prefix_bytes != expected_prefix * self.request.frame_samples * 4
        ):
            raise ValueError("protected ring prefix geometry disagrees with request")
        if self.stored_observed_samples + self.drained_outside_window_samples != (
            self.returned_frames * self.request.frame_samples
        ):
            raise ValueError("stored window and deliberately drained tail do not close")
        if self.returned_device_span_samples < self.returned_frames * self.request.frame_samples:
            raise ValueError("returned device span is shorter than observed samples")
        return self


class DirectAsyncRequestV1(ContractModel):
    """One complete dwell carried by bounded direct-async DMA segments."""

    schema_version: Literal[1] = 1
    mode: Literal["segmented_direct_async"] = "segmented_direct_async"
    frame_samples: Literal[1_048_576] = 1_048_576
    maximum_segment_frames: Literal[64] = 64
    target_frames: Annotated[int, Field(gt=0)]
    receiver_count: Literal[1] = 1
    requested_device_samples: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _geometry_closes(self) -> Self:
        if not (
            (self.target_frames - 1) * self.frame_samples
            < self.requested_device_samples
            <= self.target_frames * self.frame_samples
        ):
            raise ValueError("direct-async frame target does not cover the requested dwell")
        return self

    @property
    def segment_count(self) -> int:
        return (self.target_frames + self.maximum_segment_frames - 1) // (
            self.maximum_segment_frames
        )

    def next_segment_frames(self, returned_frames: int) -> int:
        if not 0 <= returned_frames < self.target_frames:
            raise ValueError("direct-async returned-frame cursor is outside the request")
        return min(self.maximum_segment_frames, self.target_frames - returned_frames)


class DirectAsyncEvidenceV1(ContractModel):
    """Counter-derived closure for every segment of one direct-async dwell."""

    schema_version: Literal[1] = 1
    request: DirectAsyncRequestV1
    returned_frames: Annotated[int, Field(gt=0)]
    returned_device_span_samples: Annotated[int, Field(gt=0)]
    segment_count: Annotated[int, Field(gt=0)]
    upstream_stream_generations: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...]
    counter_missing_sample_count: Annotated[int, Field(ge=0)]
    inter_segment_skipped_samples: Annotated[int, Field(ge=0)]
    stored_observed_samples: Annotated[int, Field(gt=0)]
    drained_outside_window_samples: Annotated[int, Field(ge=0)]
    host_ingestion: Literal["bounded_queue_raw_spool_v1"] = "bounded_queue_raw_spool_v1"

    @model_validator(mode="after")
    def _evidence_closes(self) -> Self:
        if self.returned_frames != self.request.target_frames:
            raise ValueError("direct-async returned frame count disagrees with the request")
        if (
            self.segment_count != self.request.segment_count
            or len(self.upstream_stream_generations) != self.segment_count
            or len(set(self.upstream_stream_generations)) != self.segment_count
        ):
            raise ValueError("direct-async segment generation inventory does not close")
        returned_samples = self.returned_frames * self.request.frame_samples
        if self.stored_observed_samples + self.drained_outside_window_samples != returned_samples:
            raise ValueError("direct-async stored window and drained tail do not close")
        if self.inter_segment_skipped_samples > self.counter_missing_sample_count:
            raise ValueError("direct-async inter-segment loss exceeds total counter loss")
        if self.returned_device_span_samples != (
            returned_samples + self.counter_missing_sample_count
        ):
            raise ValueError("direct-async device span does not close returned and missing samples")
        return self


class DirectAsyncRamDropRequestV2(ContractModel):
    """One bounded direct-async dwell with finite RAM overflow and fresh-data priority."""

    schema_version: Literal[2] = 2
    mode: Literal["direct_async_ram_drop"] = "direct_async_ram_drop"
    frame_samples: Literal[1_048_576] = 1_048_576
    maximum_segment_frames: Literal[4_096] = 4_096
    target_frames: Annotated[int, Field(gt=0, le=4_096)]
    receiver_count: Literal[1] = 1
    requested_device_samples: Annotated[int, Field(gt=0)]
    requested_ram_bytes: Literal[200_000_000] = 200_000_000
    drop_backlog_on_overrun: Literal[True] = True

    @model_validator(mode="after")
    def _geometry_closes(self) -> Self:
        if not (
            (self.target_frames - 1) * self.frame_samples
            < self.requested_device_samples
            <= self.target_frames * self.frame_samples
        ):
            raise ValueError("direct-async RAM/drop frame target does not cover the dwell")
        return self

    @property
    def segment_count(self) -> int:
        return (self.target_frames + self.maximum_segment_frames - 1) // (
            self.maximum_segment_frames
        )

    @property
    def capacity_frames(self) -> int:
        return self.requested_ram_bytes // (self.frame_samples * 4)

    @property
    def admitted_ram_bytes(self) -> int:
        return self.capacity_frames * self.frame_samples * 4

    def next_segment_frames(self, returned_frames: int) -> int:
        if not 0 <= returned_frames < self.target_frames:
            raise ValueError("direct-async RAM/drop frame cursor is outside the request")
        return min(self.maximum_segment_frames, self.target_frames - returned_frames)


class DirectAsyncRamDropRequestV3(ContractModel):
    """Hardware-qualified RAM/drop geometry for the existing direct-async path."""

    schema_version: Literal[3] = 3
    mode: Literal["direct_async_ram_drop"] = "direct_async_ram_drop"
    frame_samples: Literal[1_048_576] = 1_048_576
    maximum_segment_frames: Literal[4_096] = 4_096
    target_frames: Annotated[int, Field(gt=0, le=4_096)]
    receiver_count: Literal[1] = 1
    requested_device_samples: Annotated[int, Field(gt=0)]
    requested_ram_bytes: Literal[134_217_728] = 134_217_728
    drop_backlog_on_overrun: Literal[True] = True

    @model_validator(mode="after")
    def _geometry_closes(self) -> Self:
        if not (
            (self.target_frames - 1) * self.frame_samples
            < self.requested_device_samples
            <= self.target_frames * self.frame_samples
        ):
            raise ValueError("direct-async RAM/drop frame target does not cover the dwell")
        return self

    @property
    def segment_count(self) -> int:
        return (self.target_frames + self.maximum_segment_frames - 1) // (
            self.maximum_segment_frames
        )

    @property
    def capacity_frames(self) -> int:
        return self.requested_ram_bytes // (self.frame_samples * 4)

    @property
    def admitted_ram_bytes(self) -> int:
        return self.capacity_frames * self.frame_samples * 4

    def next_segment_frames(self, returned_frames: int) -> int:
        if not 0 <= returned_frames < self.target_frames:
            raise ValueError("direct-async RAM/drop frame cursor is outside the request")
        return min(self.maximum_segment_frames, self.target_frames - returned_frames)


class DirectAsyncRamDropRequestV4(ContractModel):
    """Bounded-session RAM/drop geometry for sustained 20/25 MS/s capture."""

    schema_version: Literal[4] = 4
    mode: Literal["direct_async_ram_drop"] = "direct_async_ram_drop"
    frame_samples: Literal[1_048_576] = 1_048_576
    maximum_segment_frames: Literal[64] = 64
    target_frames: Annotated[int, Field(gt=0, le=4_096)]
    receiver_count: Literal[1] = 1
    requested_device_samples: Annotated[int, Field(gt=0)]
    requested_ram_bytes: Literal[134_217_728] = 134_217_728
    drop_backlog_on_overrun: Literal[True] = True

    @model_validator(mode="after")
    def _geometry_closes(self) -> Self:
        if not (
            (self.target_frames - 1) * self.frame_samples
            < self.requested_device_samples
            <= self.target_frames * self.frame_samples
        ):
            raise ValueError("direct-async RAM/drop frame target does not cover the dwell")
        return self

    @property
    def segment_count(self) -> int:
        return (self.target_frames + self.maximum_segment_frames - 1) // (
            self.maximum_segment_frames
        )

    @property
    def capacity_frames(self) -> int:
        return self.requested_ram_bytes // (self.frame_samples * 4)

    @property
    def admitted_ram_bytes(self) -> int:
        return self.capacity_frames * self.frame_samples * 4

    def next_segment_frames(self, returned_frames: int) -> int:
        if not 0 <= returned_frames < self.target_frames:
            raise ValueError("direct-async RAM/drop frame cursor is outside the request")
        return min(self.maximum_segment_frames, self.target_frames - returned_frames)


class DirectAsyncExactDmaDropRequestV5(ContractModel):
    """Released v0.49 exact-DMA geometry with fresh-data priority."""

    schema_version: Literal[5] = 5
    mode: Literal["direct_async_exact_dma_drop"] = "direct_async_exact_dma_drop"
    frame_samples: Literal[1_000_000] = 1_000_000
    maximum_segment_frames: Literal[4_096] = 4_096
    target_frames: Annotated[int, Field(gt=0, le=4_096)]
    receiver_count: Literal[1] = 1
    requested_device_samples: Annotated[int, Field(gt=0)]
    requested_kernel_buffers: Literal[50] = 50
    requested_dma_iq_bytes: Literal[200_000_000] = 200_000_000
    requested_ram_bytes: Literal[0] = 0
    drop_backlog_on_overrun: Literal[True] = True

    @model_validator(mode="after")
    def _geometry_closes(self) -> Self:
        if not (
            (self.target_frames - 1) * self.frame_samples
            < self.requested_device_samples
            <= self.target_frames * self.frame_samples
        ):
            raise ValueError("direct-async exact-DMA frame target does not cover the dwell")
        if (
            self.frame_samples * self.receiver_count * 4 * self.requested_kernel_buffers
            != self.requested_dma_iq_bytes
        ):
            raise ValueError("direct-async exact-DMA byte geometry does not close")
        return self

    @property
    def segment_count(self) -> int:
        return (self.target_frames + self.maximum_segment_frames - 1) // (
            self.maximum_segment_frames
        )

    def next_segment_frames(self, returned_frames: int) -> int:
        if not 0 <= returned_frames < self.target_frames:
            raise ValueError("direct-async exact-DMA frame cursor is outside the request")
        return min(self.maximum_segment_frames, self.target_frames - returned_frames)


class DirectAsyncRamStatusV2(ContractModel):
    """Terminal RAM-queue counters returned by the released ABI-3 runtime."""

    version: Literal[1] = 1
    state: str
    terminal_reason: str
    error_code: int
    requested_capacity_iq_bytes: Annotated[int, Field(gt=0)]
    admitted_capacity_iq_bytes: Annotated[int, Field(gt=0)]
    target_frames: Literal[0] = 0
    produced_frames: Annotated[int, Field(ge=0)]
    consumed_frames: Annotated[int, Field(ge=0)]
    high_water_frames: Annotated[int, Field(ge=0)]
    wrap_count: Annotated[int, Field(ge=0)]
    producer_position: Annotated[int, Field(ge=0)]
    consumer_position: Annotated[int, Field(ge=0)]
    last_contiguous_sample_sequence: Annotated[int, Field(ge=0)] | None = None
    first_unavailable_sample_sequence: Annotated[int, Field(ge=0)] | None = None
    failure_frame_index: None = None
    failure_sample_sequence: None = None

    def require_complete(
        self,
        request: (
            DirectAsyncRamDropRequestV2 | DirectAsyncRamDropRequestV3 | DirectAsyncRamDropRequestV4
        ),
    ) -> None:
        if (self.state, self.terminal_reason, self.error_code) != (
            "complete",
            "target_complete",
            0,
        ):
            raise ValueError("direct-async RAM queue did not reach clean target_complete")
        if (
            self.requested_capacity_iq_bytes != request.requested_ram_bytes
            or self.admitted_capacity_iq_bytes != request.admitted_ram_bytes
            or self.consumed_frames > self.produced_frames
            or self.high_water_frames > request.capacity_frames
        ):
            raise ValueError("direct-async RAM queue admission or counters disagree")


class DirectAsyncRamDropEvidenceV2(ContractModel):
    """Counter and RAM-queue closure for one fresh-data-priority direct session."""

    schema_version: Literal[2] = 2
    request: DirectAsyncRamDropRequestV2
    status: DirectAsyncRamStatusV2
    returned_frames: Annotated[int, Field(gt=0)]
    returned_device_span_samples: Annotated[int, Field(gt=0)]
    segment_count: Annotated[int, Field(gt=0)]
    upstream_stream_generations: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...]
    counter_missing_sample_count: Annotated[int, Field(ge=0)]
    inter_segment_skipped_samples: Annotated[int, Field(ge=0)]
    stored_observed_samples: Annotated[int, Field(gt=0)]
    drained_outside_window_samples: Annotated[int, Field(ge=0)]
    host_ingestion: Literal["bounded_queue_raw_spool_v1"] = "bounded_queue_raw_spool_v1"

    @model_validator(mode="after")
    def _evidence_closes(self) -> Self:
        self.status.require_complete(self.request)
        if self.returned_frames != self.request.target_frames:
            raise ValueError("direct-async RAM/drop returned frames disagree with request")
        if (
            self.segment_count != self.request.segment_count
            or len(self.upstream_stream_generations) != self.segment_count
            or len(set(self.upstream_stream_generations)) != self.segment_count
        ):
            raise ValueError("direct-async RAM/drop session inventory does not close")
        returned_samples = self.returned_frames * self.request.frame_samples
        if self.stored_observed_samples + self.drained_outside_window_samples != returned_samples:
            raise ValueError("direct-async RAM/drop stored window and tail do not close")
        if self.inter_segment_skipped_samples > self.counter_missing_sample_count:
            raise ValueError("direct-async RAM/drop inter-session loss exceeds total loss")
        if self.returned_device_span_samples != (
            returned_samples + self.counter_missing_sample_count
        ):
            raise ValueError("direct-async RAM/drop returned span does not close")
        return self

    @property
    def ram_spilled_frames(self) -> int:
        return self.status.produced_frames

    @property
    def ram_drained_frames(self) -> int:
        return self.status.consumed_frames

    @property
    def ram_dropped_frames(self) -> int:
        return self.status.produced_frames - self.status.consumed_frames


class DirectAsyncRamDropEvidenceV3(ContractModel):
    """V3 evidence binds the qualified 32-frame RAM/drop request."""

    schema_version: Literal[3] = 3
    request: DirectAsyncRamDropRequestV3
    status: DirectAsyncRamStatusV2
    returned_frames: Annotated[int, Field(gt=0)]
    returned_device_span_samples: Annotated[int, Field(gt=0)]
    segment_count: Annotated[int, Field(gt=0)]
    upstream_stream_generations: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...]
    counter_missing_sample_count: Annotated[int, Field(ge=0)]
    inter_segment_skipped_samples: Annotated[int, Field(ge=0)]
    stored_observed_samples: Annotated[int, Field(gt=0)]
    drained_outside_window_samples: Annotated[int, Field(ge=0)]
    host_ingestion: Literal["bounded_queue_raw_spool_v1"] = "bounded_queue_raw_spool_v1"

    @model_validator(mode="after")
    def _evidence_closes(self) -> Self:
        self.status.require_complete(self.request)
        if self.returned_frames != self.request.target_frames:
            raise ValueError("direct-async RAM/drop returned frames disagree with request")
        if (
            self.segment_count != self.request.segment_count
            or len(self.upstream_stream_generations) != self.segment_count
            or len(set(self.upstream_stream_generations)) != self.segment_count
        ):
            raise ValueError("direct-async RAM/drop session inventory does not close")
        returned_samples = self.returned_frames * self.request.frame_samples
        if self.stored_observed_samples + self.drained_outside_window_samples != returned_samples:
            raise ValueError("direct-async RAM/drop stored window and tail do not close")
        if self.inter_segment_skipped_samples > self.counter_missing_sample_count:
            raise ValueError("direct-async RAM/drop inter-session loss exceeds total loss")
        if self.returned_device_span_samples != (
            returned_samples + self.counter_missing_sample_count
        ):
            raise ValueError("direct-async RAM/drop returned span does not close")
        return self

    @property
    def ram_spilled_frames(self) -> int:
        return self.status.produced_frames

    @property
    def ram_drained_frames(self) -> int:
        return self.status.consumed_frames

    @property
    def ram_dropped_frames(self) -> int:
        return self.status.produced_frames - self.status.consumed_frames


class DirectAsyncRamDropEvidenceV4(ContractModel):
    """Per-session RAM status and counter closure for a bounded segmented dwell."""

    schema_version: Literal[4] = 4
    request: DirectAsyncRamDropRequestV4
    segment_statuses: tuple[DirectAsyncRamStatusV2, ...]
    returned_frames: Annotated[int, Field(gt=0)]
    returned_device_span_samples: Annotated[int, Field(gt=0)]
    segment_count: Annotated[int, Field(gt=0)]
    upstream_stream_generations: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...]
    counter_missing_sample_count: Annotated[int, Field(ge=0)]
    inter_segment_skipped_samples: Annotated[int, Field(ge=0)]
    stored_observed_samples: Annotated[int, Field(gt=0)]
    drained_outside_window_samples: Annotated[int, Field(ge=0)]
    host_ingestion: Literal["bounded_queue_raw_spool_v1"] = "bounded_queue_raw_spool_v1"

    @model_validator(mode="after")
    def _evidence_closes(self) -> Self:
        if self.returned_frames != self.request.target_frames:
            raise ValueError("direct-async RAM/drop returned frames disagree with request")
        if (
            self.segment_count != self.request.segment_count
            or len(self.upstream_stream_generations) != self.segment_count
            or len(set(self.upstream_stream_generations)) != self.segment_count
            or len(self.segment_statuses) != self.segment_count
        ):
            raise ValueError("direct-async RAM/drop session inventory does not close")
        for status in self.segment_statuses:
            status.require_complete(self.request)
        returned_samples = self.returned_frames * self.request.frame_samples
        if self.stored_observed_samples + self.drained_outside_window_samples != returned_samples:
            raise ValueError("direct-async RAM/drop stored window and tail do not close")
        if self.inter_segment_skipped_samples > self.counter_missing_sample_count:
            raise ValueError("direct-async RAM/drop inter-session loss exceeds total loss")
        if self.returned_device_span_samples != (
            returned_samples + self.counter_missing_sample_count
        ):
            raise ValueError("direct-async RAM/drop returned span does not close")
        return self

    @property
    def ram_spilled_frames(self) -> int:
        return sum(status.produced_frames for status in self.segment_statuses)

    @property
    def ram_drained_frames(self) -> int:
        return sum(status.consumed_frames for status in self.segment_statuses)

    @property
    def ram_dropped_frames(self) -> int:
        return self.ram_spilled_frames - self.ram_drained_frames

    @property
    def ram_high_water_frames(self) -> int:
        return max(status.high_water_frames for status in self.segment_statuses)


class DirectAsyncExactDmaDropEvidenceV5(ContractModel):
    """Counter closure plus exact v0.49 kernel-DMA allocation attestation."""

    schema_version: Literal[5] = 5
    request: DirectAsyncExactDmaDropRequestV5
    allocated_kernel_buffers: Literal[50] = 50
    allocated_dma_iq_bytes: Literal[200_000_000] = 200_000_000
    returned_frames: Annotated[int, Field(gt=0)]
    returned_device_span_samples: Annotated[int, Field(gt=0)]
    segment_count: Annotated[int, Field(gt=0)]
    upstream_stream_generations: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...]
    counter_missing_sample_count: Annotated[int, Field(ge=0)]
    inter_segment_skipped_samples: Annotated[int, Field(ge=0)]
    stored_observed_samples: Annotated[int, Field(gt=0)]
    drained_outside_window_samples: Annotated[int, Field(ge=0)]
    host_ingestion: Literal["bounded_queue_raw_spool_v1"] = "bounded_queue_raw_spool_v1"

    @model_validator(mode="after")
    def _evidence_closes(self) -> Self:
        if (
            self.allocated_kernel_buffers != self.request.requested_kernel_buffers
            or self.allocated_dma_iq_bytes != self.request.requested_dma_iq_bytes
        ):
            raise ValueError("direct-async exact-DMA allocation disagrees with request")
        if self.returned_frames != self.request.target_frames:
            raise ValueError("direct-async exact-DMA returned frames disagree with request")
        if (
            self.segment_count != self.request.segment_count
            or len(self.upstream_stream_generations) != self.segment_count
            or len(set(self.upstream_stream_generations)) != self.segment_count
        ):
            raise ValueError("direct-async exact-DMA session inventory does not close")
        returned_samples = self.returned_frames * self.request.frame_samples
        if self.stored_observed_samples + self.drained_outside_window_samples != returned_samples:
            raise ValueError("direct-async exact-DMA stored window and tail do not close")
        if self.inter_segment_skipped_samples > self.counter_missing_sample_count:
            raise ValueError("direct-async exact-DMA inter-session loss exceeds total loss")
        if self.returned_device_span_samples != (
            returned_samples + self.counter_missing_sample_count
        ):
            raise ValueError("direct-async exact-DMA returned span does not close")
        return self


type DirectAsyncRequest = (
    DirectAsyncRequestV1
    | DirectAsyncRamDropRequestV2
    | DirectAsyncRamDropRequestV3
    | DirectAsyncRamDropRequestV4
    | DirectAsyncExactDmaDropRequestV5
)
type DirectAsyncEvidence = (
    DirectAsyncEvidenceV1
    | DirectAsyncRamDropEvidenceV2
    | DirectAsyncRamDropEvidenceV3
    | DirectAsyncRamDropEvidenceV4
    | DirectAsyncExactDmaDropEvidenceV5
)
type DdrRingStatus = DdrRingStatusV1 | DirectAsyncRamStatusV2
type DeviceBufferRequest = DeviceBufferRequestV1 | DirectAsyncRequest
type DeviceBufferEvidence = DeviceBufferEvidenceV1 | DirectAsyncEvidence


def device_buffer_request_v1(
    profile: CaptureProfileV1, resolved_sample_count: int
) -> DeviceBufferRequestV1 | None:
    tags = tuple(tag for tag in profile.tags if tag.startswith("DEVICE_BUFFER:"))
    if not tags:
        return None
    if tags != (DDR_RING_PROFILE_TAG_V1,):
        raise ValueError("unsupported or ambiguous device-buffer profile policy")
    if (
        not isinstance(profile, CaptureProfileV2)
        or profile.sample_rate_hz not in (10_000_000, 15_000_000, 20_000_000)
        or len(profile.receivers) != 1
        or profile.refill_samples != DDR_RING_REFILL_SAMPLES_V1
        or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
        or profile.continuity_policy.value != "allow_segments"
        or resolved_sample_count % profile.refill_samples
    ):
        raise ValueError("DDR ring V1 requires reviewed single-RX native device-axis geometry")
    return DeviceBufferRequestV1(
        requested_bytes=DDR_RING_BYTES_V1,
        target_frames=resolved_sample_count // profile.refill_samples,
        frame_samples=profile.refill_samples,
        requested_device_samples=resolved_sample_count,
    )


def device_buffer_request(
    profile: CaptureProfileV1, resolved_sample_count: int
) -> DeviceBufferRequest | None:
    """Resolve the one canonical device-buffer policy named by a profile."""

    tags = tuple(tag for tag in profile.tags if tag.startswith("DEVICE_BUFFER:"))
    if not tags:
        return None
    if tags == (DDR_RING_PROFILE_TAG_V1,):
        return device_buffer_request_v1(profile, resolved_sample_count)
    if tags == (DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V2,):
        if (
            not isinstance(profile, CaptureProfileV2)
            or profile.sample_rate_hz not in (10_000_000, 15_000_000, 20_000_000, 25_000_000)
            or len(profile.receivers) != 1
            or profile.refill_samples != DIRECT_ASYNC_FRAME_SAMPLES_V2
            or profile.kernel_buffers != DIRECT_ASYNC_KERNEL_BUFFERS_V2
            or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
            or profile.continuity_policy.value != "allow_segments"
        ):
            raise ValueError(
                "direct-async RAM/drop V2 requires reviewed single-RX device-axis geometry"
            )
        target_frames = int(
            (Decimal(resolved_sample_count) / Decimal(profile.refill_samples)).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        return DirectAsyncRamDropRequestV2(
            target_frames=target_frames,
            requested_device_samples=resolved_sample_count,
        )
    if tags == (DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V3,):
        if (
            not isinstance(profile, CaptureProfileV2)
            or profile.sample_rate_hz not in (10_000_000, 15_000_000, 20_000_000, 25_000_000)
            or len(profile.receivers) != 1
            or profile.refill_samples != DIRECT_ASYNC_FRAME_SAMPLES_V2
            or profile.kernel_buffers != DIRECT_ASYNC_KERNEL_BUFFERS_V3
            or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
            or profile.continuity_policy.value != "allow_segments"
        ):
            raise ValueError(
                "direct-async RAM/drop V3 requires reviewed single-RX device-axis geometry"
            )
        target_frames = int(
            (Decimal(resolved_sample_count) / Decimal(profile.refill_samples)).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        return DirectAsyncRamDropRequestV3(
            target_frames=target_frames,
            requested_device_samples=resolved_sample_count,
        )
    if tags == (DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V4,):
        if (
            not isinstance(profile, CaptureProfileV2)
            or profile.sample_rate_hz not in (20_000_000, 25_000_000)
            or len(profile.receivers) != 1
            or profile.refill_samples != DIRECT_ASYNC_FRAME_SAMPLES_V2
            or profile.kernel_buffers != DIRECT_ASYNC_KERNEL_BUFFERS_V3
            or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
            or profile.continuity_policy.value != "allow_segments"
        ):
            raise ValueError(
                "direct-async RAM/drop V4 requires reviewed 20/25 MS/s single-RX geometry"
            )
        target_frames = int(
            (Decimal(resolved_sample_count) / Decimal(profile.refill_samples)).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        return DirectAsyncRamDropRequestV4(
            target_frames=target_frames,
            requested_device_samples=resolved_sample_count,
        )
    if tags == (DIRECT_ASYNC_EXACT_DMA_DROP_PROFILE_TAG_V5,):
        if (
            not isinstance(profile, CaptureProfileV2)
            or profile.sample_rate_hz not in (10_000_000, 15_000_000, 20_000_000, 25_000_000)
            or len(profile.receivers) != 1
            or profile.refill_samples != DIRECT_ASYNC_FRAME_SAMPLES_V5
            or profile.kernel_buffers != DIRECT_ASYNC_KERNEL_BUFFERS_V5
            or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
            or profile.continuity_policy.value != "allow_segments"
        ):
            raise ValueError("direct-async exact-DMA/drop V5 requires reviewed single-RX geometry")
        target_frames = int(
            (Decimal(resolved_sample_count) / Decimal(profile.refill_samples)).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        return DirectAsyncExactDmaDropRequestV5(
            target_frames=target_frames,
            requested_device_samples=resolved_sample_count,
        )
    if tags != (DIRECT_ASYNC_PROFILE_TAG_V1,):
        raise ValueError("unsupported or ambiguous device-buffer profile policy")
    if (
        not isinstance(profile, CaptureProfileV2)
        or profile.sample_rate_hz not in (10_000_000, 15_000_000, 25_000_000)
        or len(profile.receivers) != 1
        or profile.refill_samples != DIRECT_ASYNC_FRAME_SAMPLES_V1
        or profile.kernel_buffers != DIRECT_ASYNC_KERNEL_BUFFERS_V1
        or profile.storage_policy != "zstd-128m-device-axis-zero-v1"
        or profile.continuity_policy.value != "allow_segments"
    ):
        raise ValueError("direct-async V1 requires reviewed single-RX device-axis geometry")
    target_frames = int(
        (Decimal(resolved_sample_count) / Decimal(profile.refill_samples)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    return DirectAsyncRequestV1(
        target_frames=target_frames,
        requested_device_samples=resolved_sample_count,
    )
