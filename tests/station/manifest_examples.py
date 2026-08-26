"""Small canonical manifest inventories for station-authority tests."""

from __future__ import annotations

from leo.contracts.profile import (
    CapturePlanV2,
    CaptureProfileRevisionV1,
    CaptureProfileRevisionV2,
    CaptureProfileV1,
    CaptureProfileV2,
)
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    ContinuitySummaryV1,
    ContinuitySummaryV2,
    DeviceAxisRecordingChunkV1,
    HostIdentityV1,
    ProducerV1,
    RecordingChunkV1,
    RecordingManifestV1,
    RecordingManifestV2,
    RecordingManifestV3,
    RecordingStreamV1,
    RecordingStreamV2,
    RecordingStreamV3,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    GainMode,
    PeerFailurePolicy,
    RadioTransport,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.contracts.validity import DeviceAxisContentKind
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
        gains=tuple(ReceiverGainV1(receiver_id=item, gain_db=30.0) for item in requested),
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
        gains=tuple(ReceiverGainV1(receiver_id=item, gain_db=30.0) for item in requested),
    )
    applied_settings = RadioSettingsV1(
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receiver_ids=applied_receiver_ids,
        gain_mode=GainMode.MANUAL,
        gains=tuple(
            ReceiverGainV1(receiver_id=item, gain_db=30.0) for item in applied_receiver_ids
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


def manifest_example_v2(
    *,
    radio_count: int,
    applied_receiver_ids: tuple[int, ...],
    requested_receiver_ids: tuple[int, ...] | None = None,
    source_type: SourceType = SourceType.IMPORT,
) -> RecordingManifestV2:
    """Small V2 manifest whose V2-only fields are digest-significant."""

    base = manifest_example(
        radio_count=radio_count,
        applied_receiver_ids=applied_receiver_ids,
        requested_receiver_ids=requested_receiver_ids,
        source_type=source_type,
    )
    profile_document = base.capture_plan.profile_revision.profile.model_dump(mode="json")
    profile_document.update(
        {
            "schema_version": 2,
            "refill_samples": 1,
            "prime_refills": 0,
            "kernel_buffers": 8,
            "refill_queue_capacity": 32,
            "require_device_metadata": True,
        }
    )
    profile = CaptureProfileV2.model_validate(profile_document)
    plan = compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        base.capture_plan.radio_ids,
        source_type=source_type,
    )
    assert isinstance(plan, CapturePlanV2)
    streams: list[RecordingStreamV2] = []
    for ordinal, stream in enumerate(base.streams):
        stream_document = {
            **stream.model_dump(mode="json"),
            "schema_version": 2,
            "continuity": ContinuitySummaryV2(
                refill_count=1,
                segment_count=1,
                sample_loss_observable=True,
                first_source_sequence=ordinal,
                last_source_sequence=ordinal,
                first_device_sample_counter=0,
                last_device_sample_counter=0,
                observed_sample_count=1,
                device_span_sample_count=1,
                kernel_buffers=8,
                metadata_abi_version=1,
                validated_stream_generation=f"generation-{ordinal}",
                queue_capacity_refills=32,
                queue_high_water_refills=1,
            ).model_dump(mode="json"),
        }
        if "gap_map_relative_path" in RecordingStreamV2.model_fields:
            stream_document.update(
                {
                    "gap_map_relative_path": f"streams/stream-{ordinal}/gap-map.json",
                    "gap_map_sha256": _DIGEST,
                }
            )
        streams.append(RecordingStreamV2.model_validate(stream_document))
    return RecordingManifestV2.model_validate(
        {
            **base.model_dump(mode="json"),
            "schema_version": 2,
            "session_id": f"session-v2-{radio_count}r-{len(applied_receiver_ids)}rx",
            "capture_plan": plan.model_dump(mode="json"),
            "streams": tuple(item.model_dump(mode="json") for item in streams),
            "producer": ProducerV1(
                name="station-authority-test",
                version="2",
            ).model_dump(mode="json"),
        }
    )


def manifest_example_v3(
    *,
    radio_count: int,
    applied_receiver_ids: tuple[int, ...],
    source_type: SourceType = SourceType.IMPORT,
) -> RecordingManifestV3:
    """Small lossless V3 manifest with digest-significant device-axis fields."""

    base = manifest_example_v2(
        radio_count=radio_count,
        applied_receiver_ids=applied_receiver_ids,
        source_type=source_type,
    )
    profile = base.capture_plan.profile_revision.profile.model_copy(
        update={
            "storage_policy": DEVICE_AXIS_STORAGE_POLICY_V1,
            "peer_failure_policy": PeerFailurePolicy.FAIL_SESSION,
        }
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        base.capture_plan.radio_ids,
        source_type=source_type,
    )
    assert isinstance(plan, CapturePlanV2)
    streams: list[RecordingStreamV3] = []
    for stream in base.streams:
        assert stream.applied_settings is not None
        assert stream.timing is not None
        assert stream.timeline_relative_path is not None
        assert stream.timeline_sha256 is not None
        assert stream.gap_map_relative_path is not None
        assert stream.gap_map_sha256 is not None
        old_chunk = stream.chunks[0]
        streams.append(
            RecordingStreamV3(
                stream_id=stream.stream_id,
                radio=stream.radio,
                requested_settings=stream.requested_settings,
                applied_settings=stream.applied_settings,
                state=StreamState.COMPLETE,
                requested_sample_count=1,
                logical_sample_count=1,
                observed_sample_count=1,
                zero_fill_sample_count=0,
                timing=stream.timing,
                chunks=(
                    DeviceAxisRecordingChunkV1(
                        chunk_index=0,
                        relative_path=old_chunk.relative_path,
                        device_sample_start=0,
                        sample_count=1,
                        content_kind=DeviceAxisContentKind.OBSERVED,
                        continuity_segment_index=0,
                        uncompressed_bytes=old_chunk.uncompressed_bytes,
                        compressed_bytes=old_chunk.compressed_bytes,
                        uncompressed_sha256=old_chunk.uncompressed_sha256,
                        compressed_sha256=old_chunk.compressed_sha256,
                    ),
                ),
                observed_iq_sha256=old_chunk.uncompressed_sha256,
                logical_iq_sha256=old_chunk.uncompressed_sha256,
                timeline_relative_path=stream.timeline_relative_path,
                timeline_sha256=stream.timeline_sha256,
                gap_map_relative_path=stream.gap_map_relative_path,
                gap_map_sha256=stream.gap_map_sha256,
                validity_inventory_relative_path=(
                    f"streams/{stream.stream_id}/validity-inventory.json"
                ),
                validity_inventory_sha256=_DIGEST,
                continuity=stream.continuity,
            )
        )
    return RecordingManifestV3(
        session_id=f"session-v3-{radio_count}r-{len(applied_receiver_ids)}rx",
        state=CaptureState.COMMITTED,
        source_type=source_type,
        created_utc_ns=base.created_utc_ns,
        finalized_utc_ns=base.finalized_utc_ns,
        capture_plan=plan,
        tags=base.tags,
        streams=tuple(streams),
        synchronization=base.synchronization,
        compression=CompressionSettingsV1(policy_id=DEVICE_AXIS_STORAGE_POLICY_V1),
        host=base.host,
        producer=ProducerV1(name="station-authority-test", version="3"),
    )


def topology_for_manifest(
    manifest: RecordingManifestV1 | RecordingManifestV2 | RecordingManifestV3,
) -> StationReceiverTopologyV1:
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
                    physical_receiver_id=(f"physical-{stream.radio.radio_id}-rx{receiver_id}"),
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


def verified_digest(
    manifest: RecordingManifestV1 | RecordingManifestV2 | RecordingManifestV3,
) -> str:
    return recording_manifest_canonical_digest(manifest)
