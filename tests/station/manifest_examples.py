"""Small canonical manifest inventories for station-authority tests."""

from __future__ import annotations

from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    ContinuitySummaryV1,
    HostIdentityV1,
    ProducerV1,
    RecordingChunkV1,
    RecordingManifestV1,
    RecordingStreamV1,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    GainMode,
    RadioTransport,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.domain.profiles import compile_capture_plan
from leo.station.authority import (
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
    recording_manifest_canonical_digest,
)

_DIGEST = f"sha256:{'a' * 64}"


def manifest_example(
    *,
    radio_count: int,
    applied_receiver_ids: tuple[int, ...],
    requested_receiver_ids: tuple[int, ...] | None = None,
    source_type: SourceType = SourceType.TEST,
) -> RecordingManifestV1:
    requested = requested_receiver_ids or applied_receiver_ids
    radio_ids = tuple(f"radio-{index}" for index in range(radio_count))
    profile = CaptureProfileV1(
        name="station-authority-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=requested,
        gain_mode=GainMode.MANUAL,
        gains=tuple(
            ReceiverGainV1(receiver_id=item, gain_db=30.0) for item in requested
        ),
        sample_count=1,
        storage_policy="test-zstd-v1",
        tags=("TEST",) if source_type is SourceType.TEST else (),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        radio_ids,
        source_type=source_type,
    )
    requested_settings = RadioSettingsV1(
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receiver_ids=requested,
        gain_mode=GainMode.MANUAL,
        gains=tuple(
            ReceiverGainV1(receiver_id=item, gain_db=30.0) for item in requested
        ),
    )
    applied_settings = RadioSettingsV1(
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receiver_ids=applied_receiver_ids,
        gain_mode=GainMode.MANUAL,
        gains=tuple(
            ReceiverGainV1(receiver_id=item, gain_db=30.0)
            for item in applied_receiver_ids
        ),
    )
    streams: list[RecordingStreamV1] = []
    for ordinal, radio_id in enumerate(radio_ids):
        start = 100_000 + ordinal * 1_000
        streams.append(
            RecordingStreamV1(
                stream_id=f"stream-{ordinal}",
                radio=RadioIdentityV1(
                    radio_id=radio_id,
                    serial=f"serial-{ordinal}",
                    uri=f"ip:192.0.2.{10 + ordinal}",
                    transport=RadioTransport.IIO_IP,
                ),
                requested_settings=requested_settings,
                applied_settings=applied_settings,
                state=StreamState.COMPLETE,
                requested_sample_count=1,
                captured_sample_count=1,
                timing=StreamTimingV1(
                    first_sample=TimingEstimateV1(
                        estimate_utc_ns=start + 10,
                        earliest_utc_ns=start,
                        latest_utc_ns=start + 20,
                        method=TimingMethod.DEVICE_COUNTER_ANCHORED,
                    ),
                    last_sample=TimingEstimateV1(
                        estimate_utc_ns=start + 1_010,
                        earliest_utc_ns=start + 1_000,
                        latest_utc_ns=start + 1_020,
                        method=TimingMethod.DEVICE_COUNTER_ANCHORED,
                    ),
                ),
                chunks=(
                    RecordingChunkV1(
                        chunk_index=0,
                        relative_path=f"streams/stream-{ordinal}/iq-000000.ci16.zst",
                        sample_start=0,
                        sample_count=1,
                        uncompressed_bytes=4 * len(applied_receiver_ids),
                        compressed_bytes=16,
                        uncompressed_sha256=_DIGEST,
                        compressed_sha256=_DIGEST,
                    ),
                ),
                timeline_relative_path=f"streams/stream-{ordinal}/timeline.jsonl.zst",
                timeline_sha256=_DIGEST,
                continuity=ContinuitySummaryV1(refill_count=1, segment_count=1),
            )
        )
    paired = radio_count == 2
    compression = CompressionSettingsV1(policy_id="test-zstd-v1")
    return RecordingManifestV1(
        session_id=f"session-{radio_count}r-{len(applied_receiver_ids)}rx",
        state=CaptureState.COMMITTED,
        source_type=source_type,
        created_utc_ns=90_000,
        finalized_utc_ns=200_000,
        capture_plan=plan,
        tags=("TEST",) if source_type is SourceType.TEST else (),
        streams=tuple(streams),
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=(
                SynchronizationMode.BEST_EFFORT if paired else SynchronizationMode.NONE
            ),
            grade=(
                SynchronizationGrade.BEST_EFFORT_OBSERVED
                if paired
                else SynchronizationGrade.NOT_REQUESTED
            ),
            stream_ids=tuple(item.stream_id for item in streams),
        ),
        compression=compression,
        host=HostIdentityV1(hostname="station-authority-test"),
        producer=ProducerV1(name="station-authority-test", version="1"),
    )


def topology_for_manifest(manifest: RecordingManifestV1) -> StationReceiverTopologyV1:
    radios = tuple(
        StationRadioTopologyV1.create(
            radio_id=stream.radio.radio_id,
            radio_serial=stream.radio.serial,
            endpoint_evidence=RadioEndpointEvidenceV1(
                transport=stream.radio.transport,
                endpoint=stream.radio.uri,
                evidence_uri=f"authority/{stream.radio.radio_id}.json",
                evidence_digest=_DIGEST,
            ),
            receiver_assignments=tuple(
                StationReceiverAssignmentV1(
                    receiver_id=receiver_id,
                    physical_receiver_id=(
                        f"physical-{stream.radio.radio_id}-rx{receiver_id}"
                    ),
                    hardware_epoch_external_id=(
                        f"hardware-{stream.radio.radio_id}-rx{receiver_id}-v1"
                    ),
                    valid_from_utc_ns=0,
                    valid_until_utc_ns=1_000_000,
                )
                for receiver_id in (0, 1)
            ),
        )
        for stream in manifest.streams
    )
    return StationReceiverTopologyV1.create(
        station_id="station-gauss",
        topology_revision="gauss-receiver-map-v1",
        valid_from_utc_ns=0,
        valid_until_utc_ns=1_000_000,
        radios=radios,
    )


def verified_digest(manifest: RecordingManifestV1) -> str:
    return recording_manifest_canonical_digest(manifest)
