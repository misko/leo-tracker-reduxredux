from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from leo.contracts.profile import CapturePlanV2, CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    ContinuitySummaryV2,
    DeviceAxisRecordingChunkV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV3,
    RecordingStreamV3,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
    parse_recording_manifest,
    parse_recording_manifest_json,
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

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _profile(*, peer_failure_policy: PeerFailurePolicy = PeerFailurePolicy.FAIL_SESSION):
    return CaptureProfileV2(
        name="device-axis-v3",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=5_000_000,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30),
            ReceiverGainV1(receiver_id=1, gain_db=30),
        ),
        sample_count=4,
        kernel_buffers=8,
        peer_failure_policy=peer_failure_policy,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
        tags=("TEST",),
    )


def _manifest(
    *,
    peer_failure_policy: PeerFailurePolicy = PeerFailurePolicy.FAIL_SESSION,
) -> RecordingManifestV3:
    profile = _profile(peer_failure_policy=peer_failure_policy)
    plan = cast(
        CapturePlanV2,
        compile_capture_plan(
            CaptureProfileRevisionV2.from_profile(profile),
            ["radio-a"],
            source_type=SourceType.TEST,
        ),
    )
    settings = RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=profile.receivers,
        gain_mode=profile.gain_mode,
        gains=profile.gains,
    )
    stream = RecordingStreamV3(
        stream_id="stream-a",
        radio=RadioIdentityV1(
            radio_id="radio-a",
            serial="serial-a",
            uri="fake://radio-a",
            transport=RadioTransport.FAKE,
        ),
        requested_settings=settings,
        applied_settings=settings,
        state=StreamState.COMPLETE,
        requested_sample_count=4,
        logical_sample_count=4,
        observed_sample_count=4,
        zero_fill_sample_count=0,
        timing=StreamTimingV1(
            first_sample=TimingEstimateV1(
                estimate_utc_ns=1_000,
                earliest_utc_ns=999,
                latest_utc_ns=1_001,
                method=TimingMethod.DEVICE_COUNTER_ANCHORED,
            ),
            last_sample=TimingEstimateV1(
                estimate_utc_ns=2_000,
                earliest_utc_ns=1_999,
                latest_utc_ns=2_001,
                method=TimingMethod.DEVICE_COUNTER_ANCHORED,
            ),
        ),
        chunks=(
            DeviceAxisRecordingChunkV1(
                chunk_index=0,
                content_kind=DeviceAxisContentKind.OBSERVED,
                continuity_segment_index=0,
                relative_path="radio-serial-a/iq-000000.ci16.zst",
                device_sample_start=0,
                sample_count=4,
                uncompressed_bytes=32,
                compressed_bytes=20,
                uncompressed_sha256=DIGEST_A,
                compressed_sha256=DIGEST_B,
            ),
        ),
        observed_iq_sha256=DIGEST_A,
        logical_iq_sha256=DIGEST_A,
        timeline_relative_path="radio-serial-a/timeline.jsonl.zst",
        timeline_sha256=DIGEST_A,
        gap_map_relative_path="radio-serial-a/gap-map.json",
        gap_map_sha256=DIGEST_A,
        validity_inventory_relative_path="radio-serial-a/validity-inventory.json",
        validity_inventory_sha256=DIGEST_A,
        continuity=ContinuitySummaryV2(
            refill_count=1,
            segment_count=1,
            sample_loss_observable=True,
            first_source_sequence=0,
            last_source_sequence=0,
            first_device_sample_counter=100,
            last_device_sample_counter=103,
            observed_sample_count=4,
            device_span_sample_count=4,
            kernel_buffers=8,
            metadata_abi_version=1,
            validated_stream_generation="generation-a",
            queue_capacity_refills=32,
            queue_high_water_refills=1,
        ),
    )
    return RecordingManifestV3(
        session_id="session-v3",
        state=CaptureState.COMMITTED,
        source_type=SourceType.TEST,
        created_utc_ns=900,
        finalized_utc_ns=2_100,
        capture_plan=plan,
        tags=("TEST",),
        streams=(stream,),
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=SynchronizationMode.NONE,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=("stream-a",),
        ),
        compression=CompressionSettingsV1(policy_id=DEVICE_AXIS_STORAGE_POLICY_V1),
        host=HostIdentityV1(hostname="v3-test"),
        producer=ProducerV1(name="leo-v3-test", version="1"),
    )


def test_v3_round_trips_through_the_additive_discriminated_parser() -> None:
    manifest = _manifest()

    assert parse_recording_manifest_json(manifest.model_dump_json()) == manifest
    assert parse_recording_manifest(manifest.model_dump(mode="json")) == manifest
    document = manifest.model_dump(mode="json")
    stream = document["streams"][0]
    assert "captured_sample_count" not in stream
    assert stream["logical_sample_count"] == 4
    assert stream["observed_sample_count"] == 4
    assert stream["zero_fill_sample_count"] == 0


def test_v3_chunk_content_cannot_fabricate_segment_identity() -> None:
    chunk = _manifest().streams[0].chunks[0]

    with pytest.raises(ValidationError, match="observed chunks require"):
        DeviceAxisRecordingChunkV1.model_validate(
            {**chunk.model_dump(), "continuity_segment_index": None}
        )
    with pytest.raises(ValidationError, match="zero-fill chunks forbid"):
        DeviceAxisRecordingChunkV1.model_validate(
            {**chunk.model_dump(), "content_kind": DeviceAxisContentKind.ZERO_FILL}
        )


def test_v3_overflow_only_stream_is_partial_despite_complete_physical_axis() -> None:
    stream = _manifest().streams[0]
    chunks = (
        stream.chunks[0].model_copy(update={"sample_count": 2, "uncompressed_bytes": 16}),
        stream.chunks[0].model_copy(
            update={
                "chunk_index": 1,
                "continuity_segment_index": 1,
                "relative_path": "radio-serial-a/iq-000001.ci16.zst",
                "device_sample_start": 2,
                "sample_count": 2,
                "uncompressed_bytes": 16,
            }
        ),
    )
    continuity = stream.continuity.model_copy(
        update={"refill_count": 2, "segment_count": 2, "overflow_count": 1}
    )

    partial = RecordingStreamV3.model_validate(
        {
            **stream.model_dump(),
            "state": StreamState.PARTIAL,
            "chunks": tuple(chunk.model_dump() for chunk in chunks),
            "continuity": continuity.model_dump(),
            "error": "counter overflow observed",
        }
    )

    assert partial.logical_sample_count == partial.observed_sample_count == 4
    assert partial.zero_fill_sample_count == 0
    with pytest.raises(ValidationError, match="complete V3 stream requires lossless"):
        RecordingStreamV3.model_validate(
            {**partial.model_dump(), "state": StreamState.COMPLETE, "error": None}
        )


def test_v3_manifest_requires_fail_session_peer_policy() -> None:
    with pytest.raises(ValidationError, match="fail-session peer semantics"):
        _manifest(peer_failure_policy=PeerFailurePolicy.KEEP_SURVIVOR)


def test_v3_stream_bundle_objects_cannot_alias_one_path() -> None:
    stream = _manifest().streams[0]

    with pytest.raises(ValidationError, match="object paths must be unique"):
        RecordingStreamV3.model_validate(
            {
                **stream.model_dump(),
                "validity_inventory_relative_path": stream.gap_map_relative_path,
            }
        )
