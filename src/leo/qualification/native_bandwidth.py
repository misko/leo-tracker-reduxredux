"""Qualification authority for enabled native-bandwidth production captures."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.profile import ProfileName
from leo.contracts.radio import RadioIdentityV1
from leo.contracts.recording import HostIdentityV1, RecordingManifestV3, RecordingManifestV4
from leo.contracts.standard_pipeline import resolve_manifest_starlink_tuning
from leo.contracts.starlink_frequency import (
    starlink_channel_if_bounds_hz,
    starlink_edge_if_center_frequency_hz,
    starlink_maximum_coverage_if_center_frequency_hz,
)
from leo.contracts.states import CaptureState, StarlinkEdge

_V1_REFILL_SAMPLES = 4_194_304
_V2_REFILL_SAMPLES = 1_048_576
_METADATA_LADDER_SAMPLES = (4_194_304, 2_097_152, 1_048_576, 524_288)
_KERNEL_BUFFERS = 4
_QUEUE_CAPACITY_REFILLS = 32
_MAXIMUM_QUEUE_HIGH_WATER_REFILLS = 24
_MINIMUM_OBSERVED_PERCENT = 95

_ORDINARY_PROFILE_AUTHORITY_V1 = {
    2_500_000: (
        "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
        "sha256:fd7ebe29c1ed6bb9b85da0d35e2ce348af3f1a885dd53546e68a5f530dac9cba",
    ),
    3_000_000: (
        "starlink-ch4-lower-3m-60s-native-bandwidth-v4",
        "sha256:3964c526cdd6fc6228bedc3f2b066bd0b7aac14d03d9f699e79fb52a0cab4907",
    ),
    5_000_000: (
        "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
        "sha256:37c144b63573556c70fd06bcc5a394a33a7070d6c99b519154b750bcdbd0dcd4",
    ),
}
_MIXED_PROFILE_AUTHORITY_V1 = {
    2_500_000: (
        "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4",
        "sha256:df2a9d8c76f03a8f5e062b6ff62d5fb5650213b5738828b8fa5ae72fef3ee2d2",
    ),
    5_000_000: (
        "starlink-ch4-lower-5m-60s-mixed-device-axis-v4",
        "sha256:ff8cc094a9f692352b354619fe479fd6f0e970304123706f409ff1a4af55d404",
    ),
}
_ORDINARY_PROFILE_AUTHORITY_V2 = {
    2_500_000: (
        "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
        "sha256:140d4f834fd27b94754ea9017f2be45da21af2662dfef8ec97c4487fbf15bc89",
    ),
    3_000_000: (
        "starlink-ch4-lower-3m-60s-native-bandwidth-v4",
        "sha256:523402d005564d97177ee139f1a616c01b6b65d9a6c4ad11a0564c074216865c",
    ),
    5_000_000: (
        "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
        "sha256:6f8ec4a5dec0f6b18d09c0f464c22c143ac363f2088242db830b0757a6316294",
    ),
}
_MIXED_PROFILE_AUTHORITY_V2 = {
    2_500_000: (
        "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4",
        "sha256:e5f088ba153a893eb5f5324c6c411ebe189acc9de5bfa68211a841edc9bbdb44",
    ),
    5_000_000: (
        "starlink-ch4-lower-5m-60s-mixed-device-axis-v4",
        "sha256:e5d593c1711ddb65be6adeb2f3fe620afe99948aed2881dabc142b5737e81afc",
    ),
}

GitRevision = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
RadioId = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class NativeBandwidthCaptureModeV1(StrEnum):
    """Closed capture inventory required before the safe scheduler can run."""

    ORDINARY_2P5 = "ordinary_2p5"
    ORDINARY_3 = "ordinary_3"
    ORDINARY_5 = "ordinary_5"
    MIXED_2P5_5_HIGH_FIRST = "mixed_2p5_5_high_first"
    MIXED_2P5_5_HIGH_SECOND = "mixed_2p5_5_high_second"


_EXPECTED_MODE_RATES: dict[NativeBandwidthCaptureModeV1, tuple[int, int]] = {
    NativeBandwidthCaptureModeV1.ORDINARY_2P5: (2_500_000, 2_500_000),
    NativeBandwidthCaptureModeV1.ORDINARY_3: (3_000_000, 3_000_000),
    NativeBandwidthCaptureModeV1.ORDINARY_5: (5_000_000, 5_000_000),
    NativeBandwidthCaptureModeV1.MIXED_2P5_5_HIGH_FIRST: (5_000_000, 2_500_000),
    NativeBandwidthCaptureModeV1.MIXED_2P5_5_HIGH_SECOND: (2_500_000, 5_000_000),
}


class NativeBandwidthLadderCellV1(ContractModel):
    """One PPU maximum-buffer rate rung."""

    schema_version: Literal[1] = 1
    sample_rate_hz: Annotated[int, Field(gt=0)]
    actual_sample_rate_hz: Annotated[int, Field(gt=0)]
    delivery_fraction: Annotated[float, Field(ge=0)]
    achieved_payload_mbps: Annotated[float, Field(gt=0)]
    kept_pace: Literal[True] = True

    @model_validator(mode="after")
    def _rate_and_delivery_close(self) -> Self:
        if self.actual_sample_rate_hz != self.sample_rate_hz:
            raise ValueError("PPU ladder applied rate differs from requested rate")
        if self.delivery_fraction < 0.9:
            raise ValueError("PPU ladder did not meet the 90% keep-pace floor")
        return self


class NativeBandwidthTransportEvidenceV1(ContractModel):
    """Exact PPU ladder evidence for one production IP radio."""

    EXPECTED_REFILL_SAMPLES: ClassVar[int] = _V1_REFILL_SAMPLES

    schema_version: Literal[1] = 1
    radio_id: RadioId
    endpoint: Literal["192.168.1.20", "192.168.1.21"]
    serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    evidence_sha256: Sha256Digest
    pluto_plus_utils_revision: GitRevision
    samples_per_channel: Annotated[int, Field(gt=0)] = _V1_REFILL_SAMPLES
    frames: Annotated[int, Field(ge=1)]
    warmup_frames: Annotated[int, Field(ge=1)]
    kernel_buffers: Annotated[int, Field(ge=1)] = _KERNEL_BUFFERS
    kernel_buffer_configuration_basis: Literal["setter_accepted", "readback"]
    original_settings_restored: Literal[True] = True
    cells: tuple[
        NativeBandwidthLadderCellV1,
        NativeBandwidthLadderCellV1,
        NativeBandwidthLadderCellV1,
    ]

    @model_validator(mode="after")
    def _ladder_inventory_is_exact(self) -> Self:
        if (
            self.samples_per_channel != self.EXPECTED_REFILL_SAMPLES
            or self.kernel_buffers != _KERNEL_BUFFERS
        ):
            raise ValueError("PPU ladder must use maximum refill and four kernel buffers")
        if tuple(cell.sample_rate_hz for cell in self.cells) != (
            2_500_000,
            3_000_000,
            5_000_000,
        ):
            raise ValueError("PPU ladder must contain ordered 2.5/3/5 MS/s rungs")
        return self


class NativeBandwidthMetadataContinuityCellV1(ContractModel):
    """Counter-authoritative result for one refill-size rung."""

    schema_version: Literal[1] = 1
    samples_per_channel: Annotated[int, Field(gt=0)]
    requested_frames: Annotated[int, Field(ge=2)]
    observed_frames: Annotated[int, Field(ge=2)]
    observed_sample_count: Annotated[int, Field(gt=0)]
    device_span_sample_count: Annotated[int, Field(gt=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    gap_count: Annotated[int, Field(ge=0)]
    overflow_count: Annotated[int, Field(ge=0)]
    observed_fraction: Annotated[float, Field(ge=0, le=1)]
    passed: bool

    @model_validator(mode="after")
    def _counter_closure_is_exact(self) -> Self:
        if self.observed_frames != self.requested_frames:
            raise ValueError("metadata ladder did not return every requested frame")
        if self.observed_sample_count != self.observed_frames * self.samples_per_channel:
            raise ValueError("metadata ladder observed sample count does not close")
        if self.device_span_sample_count != (
            self.observed_sample_count + self.missing_sample_count
        ):
            raise ValueError("metadata ladder device span does not close")
        expected_fraction = self.observed_sample_count / self.device_span_sample_count
        if abs(self.observed_fraction - expected_fraction) > 1e-12:
            raise ValueError("metadata ladder observed fraction does not close")
        expected_pass = self.observed_fraction >= 0.95 and self.overflow_count == 0
        if self.passed is not expected_pass:
            raise ValueError("metadata ladder pass result is non-canonical")
        return self


class NativeBandwidthMetadataLadderEvidenceV1(ContractModel):
    """One rate-specific PPU metadata-continuity ladder and its raw report digest."""

    schema_version: Literal[1] = 1
    report_sha256: Sha256Digest
    metadata_abi: Literal[1] = 1
    sample_rate_hz: Literal[2_500_000, 3_000_000, 5_000_000]
    rf_bandwidth_hz: Literal[2_500_000, 3_000_000, 5_000_000]
    kernel_buffers: Literal[4] = 4
    minimum_observed_fraction: Annotated[float, Field(ge=0.95, le=0.95)] = 0.95
    largest_passing_samples_per_channel: Literal[1_048_576] = 1_048_576
    original_settings_restored: Literal[True] = True
    readback_verified: Literal[True] = True
    failure_count: Literal[0] = 0
    cells: tuple[
        NativeBandwidthMetadataContinuityCellV1,
        NativeBandwidthMetadataContinuityCellV1,
        NativeBandwidthMetadataContinuityCellV1,
        NativeBandwidthMetadataContinuityCellV1,
    ]

    @model_validator(mode="after")
    def _rate_bandwidth_and_ladder_are_exact(self) -> Self:
        if self.rf_bandwidth_hz != self.sample_rate_hz:
            raise ValueError("PPU metadata ladder RF bandwidth must equal native sample rate")
        if tuple(item.samples_per_channel for item in self.cells) != _METADATA_LADDER_SAMPLES:
            raise ValueError("PPU metadata ladder refill inventory is not exact")
        largest = next((item.samples_per_channel for item in self.cells if item.passed), None)
        if largest != self.largest_passing_samples_per_channel:
            raise ValueError("PPU metadata ladder largest passing refill is not canonical")
        return self


class NativeBandwidthTransportEvidenceV2(ContractModel):
    """Counter-authoritative PPU evidence for one exact production IP radio."""

    schema_version: Literal[2] = 2
    radio_id: RadioId
    endpoint: Literal["192.168.1.20", "192.168.1.21"]
    serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    pluto_plus_utils_revision: GitRevision
    ladders: tuple[
        NativeBandwidthMetadataLadderEvidenceV1,
        NativeBandwidthMetadataLadderEvidenceV1,
        NativeBandwidthMetadataLadderEvidenceV1,
    ]

    @model_validator(mode="after")
    def _rate_inventory_is_exact(self) -> Self:
        if tuple(item.sample_rate_hz for item in self.ladders) != (
            2_500_000,
            3_000_000,
            5_000_000,
        ):
            raise ValueError("PPU metadata ladder rate inventory is not exact")
        return self


class NativeBandwidthStreamEvidenceV1(ContractModel):
    """Verified RF, device-axis, and queue closure for one captured stream."""

    EXPECTED_REFILL_SAMPLES: ClassVar[int] = _V1_REFILL_SAMPLES

    schema_version: Literal[1] = 1
    radio: RadioIdentityV1
    profile_name: ProfileName
    profile_revision_digest: Sha256Digest
    sample_rate_hz: Annotated[int, Field(gt=0)]
    rf_bandwidth_hz: Annotated[int, Field(gt=0)]
    center_frequency_hz: Annotated[int, Field(gt=0)]
    starlink_channel: Annotated[int, Field(ge=1, le=4)]
    starlink_edge: StarlinkEdge
    pilot_if_center_frequency_hz: Annotated[int, Field(gt=0)]
    channel_if_start_hz: Annotated[int, Field(gt=0)]
    channel_if_stop_hz: Annotated[int, Field(gt=0)]
    captured_if_start_hz: Annotated[int, Field(gt=0)]
    captured_if_stop_hz: Annotated[int, Field(gt=0)]
    requested_sample_count: Annotated[int, Field(gt=0)]
    logical_sample_count: Annotated[int, Field(gt=0)]
    observed_sample_count: Annotated[int, Field(gt=0)]
    zero_fill_sample_count: Annotated[int, Field(ge=0)]
    refill_samples: Annotated[int, Field(gt=0)] = _V1_REFILL_SAMPLES
    kernel_buffers: Annotated[int, Field(ge=1)] = _KERNEL_BUFFERS
    queue_capacity_refills: Annotated[int, Field(ge=1)] = _QUEUE_CAPACITY_REFILLS
    queue_high_water_refills: Annotated[int, Field(ge=0, le=24)]
    gap_count: Annotated[int, Field(ge=0)]
    overflow_count: Annotated[int, Field(ge=0)] = 0
    enqueue_failure_count: Annotated[int, Field(ge=0)] = 0
    terminal_rejected_gap_count: Annotated[int, Field(ge=0)] = 0
    terminal_rejected_missing_sample_count: Annotated[int, Field(ge=0)] = 0
    terminal_rejected_overflow_count: Annotated[int, Field(ge=0)] = 0
    observed_iq_sha256: Sha256Digest
    logical_iq_sha256: Sha256Digest
    timeline_sha256: Sha256Digest
    gap_map_sha256: Sha256Digest
    validity_inventory_sha256: Sha256Digest

    @model_validator(mode="after")
    def _stream_is_maximum_coverage_and_integrity_closed(self) -> Self:
        if self.sample_rate_hz not in {2_500_000, 3_000_000, 5_000_000}:
            raise ValueError("qualification stream rate is outside the enabled safe pool")
        if self.rf_bandwidth_hz != self.sample_rate_hz:
            raise ValueError("RF analog bandwidth must equal native sample rate")
        if (
            self.refill_samples != self.EXPECTED_REFILL_SAMPLES
            or self.kernel_buffers != _KERNEL_BUFFERS
            or self.queue_capacity_refills != _QUEUE_CAPACITY_REFILLS
            or self.queue_high_water_refills > _MAXIMUM_QUEUE_HIGH_WATER_REFILLS
        ):
            raise ValueError("qualification stream buffer or queue geometry is not reviewed")
        if any(
            (
                self.overflow_count,
                self.enqueue_failure_count,
                self.terminal_rejected_gap_count,
                self.terminal_rejected_missing_sample_count,
                self.terminal_rejected_overflow_count,
            )
        ):
            raise ValueError("qualification stream observed overflow, enqueue, or rejected data")
        expected_center = starlink_maximum_coverage_if_center_frequency_hz(
            self.starlink_channel,
            self.starlink_edge,
            bandwidth_hz=self.rf_bandwidth_hz,
        )
        channel_start, channel_stop = starlink_channel_if_bounds_hz(self.starlink_channel)
        pilot = starlink_edge_if_center_frequency_hz(
            self.starlink_channel,
            self.starlink_edge,
        )
        captured_start = expected_center - self.rf_bandwidth_hz // 2
        captured_stop = expected_center + self.rf_bandwidth_hz // 2
        if (
            self.center_frequency_hz != expected_center
            or self.pilot_if_center_frequency_hz != pilot
            or (self.channel_if_start_hz, self.channel_if_stop_hz) != (channel_start, channel_stop)
            or (self.captured_if_start_hz, self.captured_if_stop_hz)
            != (captured_start, captured_stop)
            or not channel_start <= captured_start <= pilot <= captured_stop <= channel_stop
        ):
            raise ValueError("stream RF/IF geometry is not exact maximum in-channel coverage")
        if self.requested_sample_count != self.sample_rate_hz * 60:
            raise ValueError("qualification stream is not exactly 60 seconds")
        if self.logical_sample_count != self.requested_sample_count:
            raise ValueError("logical device axis does not close requested capture span")
        if self.observed_sample_count + self.zero_fill_sample_count != self.logical_sample_count:
            raise ValueError("observed and zero-fill samples do not close logical device axis")
        if self.observed_sample_count * 100 < self.logical_sample_count * _MINIMUM_OBSERVED_PERCENT:
            raise ValueError("observed device-time coverage is below 95%")
        return self


class NativeBandwidthStreamEvidenceV2(NativeBandwidthStreamEvidenceV1):
    """V2 stream evidence pinned to the counter-proven production refill."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    EXPECTED_REFILL_SAMPLES: ClassVar[int] = _V2_REFILL_SAMPLES
    refill_samples: Annotated[int, Field(gt=0)] = _V2_REFILL_SAMPLES


class NativeBandwidthCaptureEvidenceV1(ContractModel):
    """One exact verified ordinary or mixed production capture."""

    ORDINARY_PROFILE_AUTHORITY: ClassVar[dict[int, tuple[str, str]]] = (
        _ORDINARY_PROFILE_AUTHORITY_V1
    )
    MIXED_PROFILE_AUTHORITY: ClassVar[dict[int, tuple[str, str]]] = _MIXED_PROFILE_AUTHORITY_V1

    schema_version: Literal[1] = 1
    mode: NativeBandwidthCaptureModeV1
    session_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    manifest_schema_version: Literal[3, 4]
    manifest_sha256: Sha256Digest
    capture_state: Literal[CaptureState.COMMITTED, CaptureState.DEGRADED]
    streams: tuple[NativeBandwidthStreamEvidenceV1, NativeBandwidthStreamEvidenceV1]
    bundle_verified: Literal[True] = True
    physical_zero_verified: Literal[True] = True
    gap_map_verified: Literal[True] = True
    validity_verified: Literal[True] = True

    @model_validator(mode="after")
    def _capture_inventory_matches_mode(self) -> Self:
        expected_rates = _EXPECTED_MODE_RATES[self.mode]
        actual_rates = tuple(stream.sample_rate_hz for stream in self.streams)
        if actual_rates != expected_rates:
            raise ValueError("qualification capture rate order disagrees with its mode")
        ordinary = self.mode.value.startswith("ordinary_")
        if self.manifest_schema_version != (3 if ordinary else 4):
            raise ValueError("qualification capture manifest major disagrees with its mode")
        tuning = {(stream.starlink_channel, stream.starlink_edge) for stream in self.streams}
        if len(tuning) != 1:
            raise ValueError("qualification capture radios must share one channel and edge")
        authority = self.ORDINARY_PROFILE_AUTHORITY if ordinary else self.MIXED_PROFILE_AUTHORITY
        if any(
            (stream.profile_name, stream.profile_revision_digest)
            != authority[stream.sample_rate_hz]
            for stream in self.streams
        ):
            raise ValueError("qualification capture profile identity is not reviewed")
        return self


class NativeBandwidthCaptureEvidenceV2(NativeBandwidthCaptureEvidenceV1):
    """V2 capture evidence bound to V2 stream and profile authorities."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    ORDINARY_PROFILE_AUTHORITY: ClassVar[dict[int, tuple[str, str]]] = (
        _ORDINARY_PROFILE_AUTHORITY_V2
    )
    MIXED_PROFILE_AUTHORITY: ClassVar[dict[int, tuple[str, str]]] = _MIXED_PROFILE_AUTHORITY_V2
    streams: tuple[NativeBandwidthStreamEvidenceV2, NativeBandwidthStreamEvidenceV2]  # type: ignore[assignment]


class NativeBandwidthQualificationReceiptV1(ContractModel):
    """Accepted hardware authority for the enabled safe production pool."""

    kind: Literal["native_bandwidth_qualification"] = "native_bandwidth_qualification"
    schema_version: Literal[1] = 1
    target_revision: GitRevision
    host: HostIdentityV1
    radios: tuple[RadioIdentityV1, RadioIdentityV1]
    pluto_plus_utils_revision: GitRevision
    transport_evidence: tuple[
        NativeBandwidthTransportEvidenceV1,
        NativeBandwidthTransportEvidenceV1,
    ]
    captures: tuple[
        NativeBandwidthCaptureEvidenceV1,
        NativeBandwidthCaptureEvidenceV1,
        NativeBandwidthCaptureEvidenceV1,
        NativeBandwidthCaptureEvidenceV1,
        NativeBandwidthCaptureEvidenceV1,
    ]
    created_utc_ns: Annotated[int, Field(gt=0)]
    receipt_digest: Sha256Digest
    complete: Literal[True] = True
    passed: Literal[True] = True

    @model_validator(mode="after")
    def _receipt_inventory_and_digest_are_exact(self) -> Self:
        radio_ids = tuple(radio.radio_id for radio in self.radios)
        if len(set(radio_ids)) != 2:
            raise ValueError("native-bandwidth receipt requires two unique radios")
        if tuple(item.radio_id for item in self.transport_evidence) != radio_ids:
            raise ValueError("PPU evidence radio order differs from target radios")
        if any(
            item.serial != radio.serial
            or f"ip:{item.endpoint}" != radio.uri
            or radio.transport.value != "iio_ip"
            for item, radio in zip(self.transport_evidence, self.radios, strict=True)
        ):
            raise ValueError("PPU evidence endpoint or serial differs from target radio identity")
        if any(
            item.pluto_plus_utils_revision != self.pluto_plus_utils_revision
            for item in self.transport_evidence
        ):
            raise ValueError("PPU evidence revision differs from receipt authority")
        expected_modes = tuple(NativeBandwidthCaptureModeV1)
        if tuple(item.mode for item in self.captures) != expected_modes:
            raise ValueError("native-bandwidth capture inventory is incomplete or reordered")
        if any(
            tuple(stream.radio for stream in item.streams) != self.radios for item in self.captures
        ):
            raise ValueError("capture radio identity or order differs from receipt authority")
        expected_digest = native_bandwidth_qualification_receipt_digest(self)
        if self.receipt_digest != expected_digest:
            raise ValueError("native-bandwidth receipt digest does not match content")
        return self


class NativeBandwidthQualificationReceiptV2(NativeBandwidthQualificationReceiptV1):
    """Accepted authority using counter-proven refills and exact RF readback."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    transport_evidence: tuple[
        NativeBandwidthTransportEvidenceV2,
        NativeBandwidthTransportEvidenceV2,
    ]  # type: ignore[assignment]
    captures: tuple[
        NativeBandwidthCaptureEvidenceV2,
        NativeBandwidthCaptureEvidenceV2,
        NativeBandwidthCaptureEvidenceV2,
        NativeBandwidthCaptureEvidenceV2,
        NativeBandwidthCaptureEvidenceV2,
    ]  # type: ignore[assignment]


def native_bandwidth_qualification_receipt_digest(
    receipt: NativeBandwidthQualificationReceiptV1 | NativeBandwidthQualificationReceiptV2,
) -> str:
    """Address the complete receipt without its self digest."""

    return canonical_digest(receipt.model_dump(mode="json", exclude={"receipt_digest"}))


def build_native_bandwidth_capture_evidence_v1(
    manifest: RecordingManifestV3 | RecordingManifestV4,
    *,
    mode: NativeBandwidthCaptureModeV1,
    manifest_sha256: str,
) -> NativeBandwidthCaptureEvidenceV1:
    """Project one already storage-verified V3/V4 manifest into qualification evidence."""

    documents = _native_bandwidth_stream_evidence_documents(manifest)
    return NativeBandwidthCaptureEvidenceV1(
        mode=mode,
        session_id=manifest.session_id,
        manifest_schema_version=manifest.schema_version,
        manifest_sha256=manifest_sha256,
        capture_state=manifest.state,
        streams=(
            NativeBandwidthStreamEvidenceV1.model_validate(documents[0]),
            NativeBandwidthStreamEvidenceV1.model_validate(documents[1]),
        ),
    )


def build_native_bandwidth_capture_evidence_v2(
    manifest: RecordingManifestV3 | RecordingManifestV4,
    *,
    mode: NativeBandwidthCaptureModeV1,
    manifest_sha256: str,
) -> NativeBandwidthCaptureEvidenceV2:
    """Project a verified V3/V4 manifest using the counter-proven refill authority."""

    documents = _native_bandwidth_stream_evidence_documents(manifest)
    return NativeBandwidthCaptureEvidenceV2(
        mode=mode,
        session_id=manifest.session_id,
        manifest_schema_version=manifest.schema_version,
        manifest_sha256=manifest_sha256,
        capture_state=manifest.state,
        streams=(
            NativeBandwidthStreamEvidenceV2.model_validate({**documents[0], "schema_version": 2}),
            NativeBandwidthStreamEvidenceV2.model_validate({**documents[1], "schema_version": 2}),
        ),
    )


def _native_bandwidth_stream_evidence_documents(
    manifest: RecordingManifestV3 | RecordingManifestV4,
) -> tuple[dict[str, object], dict[str, object]]:
    """Return storage-verified stream facts shared by immutable V1 and additive V2."""

    tuning = resolve_manifest_starlink_tuning(manifest)
    leg_by_radio = (
        {leg.radio_id: leg for leg in manifest.capture_plan.radio_plans}
        if isinstance(manifest, RecordingManifestV4)
        else {}
    )
    stream_evidence: list[dict[str, object]] = []
    for stream in manifest.streams:
        intent = tuning[stream.stream_id]
        if isinstance(manifest, RecordingManifestV4):
            revision = leg_by_radio[stream.radio.radio_id].profile_revision
        else:
            revision = manifest.capture_plan.profile_revision
        profile = revision.profile
        applied = stream.applied_settings
        continuity = stream.continuity
        center = applied.center_frequency_hz
        bandwidth = applied.bandwidth_hz
        channel_start, channel_stop = starlink_channel_if_bounds_hz(intent.channel)
        pilot = starlink_edge_if_center_frequency_hz(intent.channel, intent.edge)
        stream_evidence.append(
            {
                "radio": stream.radio,
                "profile_name": profile.name,
                "profile_revision_digest": revision.revision_digest,
                "sample_rate_hz": applied.sample_rate_hz,
                "rf_bandwidth_hz": bandwidth,
                "center_frequency_hz": center,
                "starlink_channel": intent.channel,
                "starlink_edge": intent.edge,
                "pilot_if_center_frequency_hz": pilot,
                "channel_if_start_hz": channel_start,
                "channel_if_stop_hz": channel_stop,
                "captured_if_start_hz": center - bandwidth // 2,
                "captured_if_stop_hz": center + bandwidth // 2,
                "requested_sample_count": stream.requested_sample_count,
                "logical_sample_count": stream.logical_sample_count,
                "observed_sample_count": stream.observed_sample_count,
                "zero_fill_sample_count": stream.zero_fill_sample_count,
                "refill_samples": profile.refill_samples,
                "kernel_buffers": continuity.kernel_buffers,
                "queue_capacity_refills": continuity.queue_capacity_refills,
                "queue_high_water_refills": continuity.queue_high_water_refills,
                "gap_count": continuity.gap_count,
                "overflow_count": continuity.overflow_count,
                "enqueue_failure_count": continuity.enqueue_failure_count,
                "terminal_rejected_gap_count": continuity.terminal_rejected_gap_count,
                "terminal_rejected_missing_sample_count": (
                    continuity.terminal_rejected_missing_sample_count
                ),
                "terminal_rejected_overflow_count": continuity.terminal_rejected_overflow_count,
                "observed_iq_sha256": stream.observed_iq_sha256,
                "logical_iq_sha256": stream.logical_iq_sha256,
                "timeline_sha256": stream.timeline_sha256,
                "gap_map_sha256": stream.gap_map_sha256,
                "validity_inventory_sha256": stream.validity_inventory_sha256,
            }
        )
    if len(stream_evidence) != 2:
        raise ValueError("native-bandwidth qualification requires exactly two streams")
    return stream_evidence[0], stream_evidence[1]
