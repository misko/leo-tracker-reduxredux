from __future__ import annotations

from decimal import Decimal

import pytest

from leo.contracts.mixed_rate_schedule import ProductionDwellClass
from leo.contracts.profile import CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    ContinuitySummaryV2,
    DeviceAxisRecordingChunkV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV4,
    RecordingStreamV3,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
    parse_recording_manifest,
    parse_recording_manifest_json,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    GainMode,
    PeerFailurePolicy,
    RadioTransport,
    SourceType,
    StarlinkEdge,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.contracts.validity import DeviceAxisContentKind
from leo.domain.mixed_rate_capture import compile_mixed_rate_capture_plan_v3
from leo.station.authority import (
    CaptureHardwareBindingV4,
    VerifiedRecordingManifestSnapshotV4,
    parse_capture_hardware_binding,
)
from tests.station.manifest_examples import topology_for_manifest, verified_digest

_A = "sha256:" + "a" * 64
_B = "sha256:" + "b" * 64


def _revision(rate: int) -> CaptureProfileRevisionV2:
    return CaptureProfileRevisionV2.from_profile(
        CaptureProfileV2(
            name=f"mixed-{rate}",
            center_frequency_hz=1_709_687_500,
            sample_rate_hz=rate,
            bandwidth_hz=rate,
            receivers=(0, 1),
            gain_mode=GainMode.MANUAL,
            gains=(
                ReceiverGainV1(receiver_id=0, gain_db=30),
                ReceiverGainV1(receiver_id=1, gain_db=30),
            ),
            duration_seconds=Decimal("60"),
            continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
            synchronization_mode=SynchronizationMode.BEST_EFFORT,
            peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
            kernel_buffers=8,
            refill_queue_capacity=32,
            storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
            tags=("DEVICE_AXIS_ZERO_FILL", "MIXED_RATE", "TEST"),
        )
    )


def _stream(
    *, index: int, radio_id: str, settings: RadioSettingsV1, count: int
) -> RecordingStreamV3:
    return RecordingStreamV3(
        stream_id=f"stream-{index}",
        radio=RadioIdentityV1(
            radio_id=radio_id,
            serial=f"serial-{index}",
            uri=f"fake://{radio_id}",
            transport=RadioTransport.FAKE,
        ),
        requested_settings=settings,
        applied_settings=settings,
        state=StreamState.COMPLETE,
        requested_sample_count=count,
        logical_sample_count=count,
        observed_sample_count=count,
        zero_fill_sample_count=0,
        timing=StreamTimingV1(
            release_target_monotonic_ns=10,
            release_observed_monotonic_ns=11,
            first_sample=TimingEstimateV1(
                estimate_utc_ns=100,
                earliest_utc_ns=99,
                latest_utc_ns=101,
                method=TimingMethod.DEVICE_COUNTER_ANCHORED,
            ),
            last_sample=TimingEstimateV1(
                estimate_utc_ns=60_000_000_099,
                earliest_utc_ns=60_000_000_098,
                latest_utc_ns=60_000_000_100,
                method=TimingMethod.DEVICE_COUNTER_ANCHORED,
            ),
        ),
        chunks=(
            DeviceAxisRecordingChunkV1(
                chunk_index=0,
                content_kind=DeviceAxisContentKind.OBSERVED,
                continuity_segment_index=0,
                relative_path=f"radio-{index}/iq-000000.ci16.zst",
                device_sample_start=0,
                sample_count=count,
                uncompressed_bytes=count * 8,
                compressed_bytes=max(1, count * 4),
                uncompressed_sha256=_A,
                compressed_sha256=_B,
            ),
        ),
        observed_iq_sha256=_A,
        logical_iq_sha256=_A,
        timeline_relative_path=f"radio-{index}/timeline.jsonl.zst",
        timeline_sha256=_A,
        gap_map_relative_path=f"radio-{index}/gap-map.json",
        gap_map_sha256=_A,
        validity_inventory_relative_path=f"radio-{index}/validity-inventory.json",
        validity_inventory_sha256=_A,
        continuity=ContinuitySummaryV2(
            refill_count=1,
            segment_count=1,
            sample_loss_observable=True,
            first_source_sequence=0,
            last_source_sequence=0,
            first_device_sample_counter=0,
            last_device_sample_counter=count - 1,
            observed_sample_count=count,
            device_span_sample_count=count,
            kernel_buffers=8,
            metadata_abi_version=1,
            validated_stream_generation=f"generation-{index}",
            queue_capacity_refills=32,
            queue_high_water_refills=1,
        ),
    )


def _manifest(*, source_type: SourceType = SourceType.TEST) -> RecordingManifestV4:
    plan = compile_mixed_rate_capture_plan_v3(
        dwell_class=ProductionDwellClass.MIXED_2P5_5,
        radio_ids=("radio-20", "radio-21"),
        profile_revisions_by_radio={
            "radio-20": _revision(2_500_000),
            "radio-21": _revision(5_000_000),
        },
        starlink_channel=4,
        starlink_edge=StarlinkEdge.LOWER,
        source_type=source_type,
    )
    streams = tuple(
        _stream(
            index=index,
            radio_id=leg.radio_id,
            settings=leg.requested_settings,
            count=leg.resolved_sample_count,
        )
        for index, leg in enumerate(plan.radio_plans)
    )
    return RecordingManifestV4(
        session_id="mixed-session",
        state=CaptureState.COMMITTED,
        source_type=source_type,
        created_utc_ns=1,
        finalized_utc_ns=2,
        capture_plan=plan,
        tags=(
            "DEVICE_AXIS_ZERO_FILL",
            "MIXED_RATE",
            "TEST",
            "mixed_rate_class:mixed_2p5_5",
            "tuning_policy:same:4:lower",
        ),
        streams=streams,
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=SynchronizationMode.BEST_EFFORT,
            grade=SynchronizationGrade.BEST_EFFORT_OBSERVED,
            stream_ids=("stream-0", "stream-1"),
            release_target_monotonic_ns=10,
        ),
        compression=CompressionSettingsV1(policy_id=DEVICE_AXIS_STORAGE_POLICY_V1),
        host=HostIdentityV1(hostname="mixed-test"),
        producer=ProducerV1(name="leo-mixed-test", version="1"),
    )


def test_v4_round_trips_without_reinterpreting_v3() -> None:
    manifest = _manifest()
    assert parse_recording_manifest_json(manifest.model_dump_json()) == manifest
    assert parse_recording_manifest(manifest.model_dump(mode="json")) == manifest
    assert tuple(stream.logical_sample_count for stream in manifest.streams) == (
        150_000_000,
        300_000_000,
    )


def test_v4_rejects_cross_radio_span_or_setting_tamper() -> None:
    manifest = _manifest()
    wrong = manifest.model_dump(mode="json")
    wrong["streams"][1]["requested_sample_count"] = 150_000_000
    wrong["streams"][1]["logical_sample_count"] = 150_000_000
    wrong["streams"][1]["observed_sample_count"] = 150_000_000
    wrong["streams"][1]["chunks"][0]["sample_count"] = 150_000_000
    wrong["streams"][1]["chunks"][0]["uncompressed_bytes"] = 1_200_000_000
    wrong["streams"][1]["continuity"]["observed_sample_count"] = 150_000_000
    wrong["streams"][1]["continuity"]["device_span_sample_count"] = 150_000_000
    with pytest.raises(ValueError, match="span disagrees"):
        RecordingManifestV4.model_validate(wrong)

    wrong = manifest.model_dump(mode="json")
    wrong["streams"][1]["requested_settings"]["center_frequency_hz"] += 1
    with pytest.raises(ValueError, match="requested settings"):
        RecordingManifestV4.model_validate(wrong)

    wrong = manifest.model_dump(mode="json")
    wrong["streams"][1]["applied_settings"]["bandwidth_hz"] -= 1
    with pytest.raises(ValueError, match="applied RF/IF geometry"):
        RecordingManifestV4.model_validate(wrong)

    wrong = manifest.model_dump(mode="json")
    wrong["streams"][1]["applied_settings"]["center_frequency_hz"] += 1
    with pytest.raises(ValueError, match="applied RF/IF geometry"):
        RecordingManifestV4.model_validate(wrong)


def test_v4_station_authority_round_trips_complete_unequal_rate_manifest() -> None:
    manifest = _manifest(source_type=SourceType.IMPORT)
    digest = verified_digest(manifest)
    topology = topology_for_manifest(manifest)

    snapshot = VerifiedRecordingManifestSnapshotV4.from_verified_manifest(
        manifest,
        observed_manifest_file_digest=digest,
    )
    binding = CaptureHardwareBindingV4.create(
        manifest,
        observed_manifest_file_digest=digest,
        topology=topology,
    )

    assert snapshot.recording_manifest == manifest
    assert tuple(
        item.requested_settings.sample_rate_hz
        for item in snapshot.recording_manifest.capture_plan.radio_plans
    ) == (2_500_000, 5_000_000)
    assert parse_capture_hardware_binding(binding.model_dump(mode="json")) == binding
