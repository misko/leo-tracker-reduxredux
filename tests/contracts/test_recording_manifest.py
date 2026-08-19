from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import (
    IqBlockMetadataV1,
    NanosecondIntervalV1,
    RadioIdentityV1,
    RadioSettingsV1,
    ReceiverGainV1,
)
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

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _plan():
    profile = CaptureProfileV1(
        name="test-four-samples",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            {"receiver_id": 0, "gain_db": 30.0},
            {"receiver_id": 1, "gain_db": 30.0},
        ),
        sample_count=4,
        tags=("TEST",),
    )
    return compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        ["radio-a"],
        source_type=SourceType.TEST,
    )


def _timing() -> StreamTimingV1:
    return StreamTimingV1(
        first_sample=TimingEstimateV1(
            estimate_utc_ns=1_010,
            earliest_utc_ns=1_000,
            latest_utc_ns=1_020,
            method=TimingMethod.HOST_BRACKET,
        ),
        last_sample=TimingEstimateV1(
            estimate_utc_ns=2_010,
            earliest_utc_ns=2_000,
            latest_utc_ns=2_020,
            method=TimingMethod.HOST_BRACKET,
        ),
    )


def _stream() -> RecordingStreamV1:
    settings = RadioSettingsV1(
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receiver_ids=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30.0),
            ReceiverGainV1(receiver_id=1, gain_db=30.0),
        ),
    )
    return RecordingStreamV1(
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
        captured_sample_count=4,
        timing=_timing(),
        chunks=(
            RecordingChunkV1(
                chunk_index=0,
                relative_path="radio-serial-a/iq-000000.ci16.zst",
                sample_start=0,
                sample_count=4,
                uncompressed_bytes=32,
                compressed_bytes=20,
                uncompressed_sha256=DIGEST_A,
                compressed_sha256=DIGEST_B,
            ),
        ),
        timeline_relative_path="radio-serial-a/timeline.jsonl.zst",
        timeline_sha256=DIGEST_A,
        continuity=ContinuitySummaryV1(
            refill_count=1,
            segment_count=1,
            first_source_sequence=0,
            last_source_sequence=0,
            first_device_sample_counter=100,
            last_device_sample_counter=103,
        ),
    )


def _manifest() -> RecordingManifestV1:
    plan = _plan()
    return RecordingManifestV1(
        session_id="session-a",
        state=CaptureState.COMMITTED,
        source_type=SourceType.TEST,
        created_utc_ns=900,
        finalized_utc_ns=2_100,
        capture_plan=plan,
        tags=("TEST",),
        streams=(_stream(),),
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=SynchronizationMode.NONE,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=("stream-a",),
        ),
        compression=CompressionSettingsV1(policy_id="zstd-128m-v1"),
        host=HostIdentityV1(hostname="test-host", machine_id="test-machine"),
        producer=ProducerV1(name="leo", version="0.1.0", source_revision="abc123"),
    )


def test_manifest_round_trips_as_a_closed_versioned_contract() -> None:
    manifest = _manifest()
    restored = RecordingManifestV1.model_validate_json(manifest.model_dump_json())

    assert restored == manifest
    with pytest.raises(ValidationError, match="Extra inputs"):
        RecordingManifestV1.model_validate({**manifest.model_dump(), "unknown": 1})


def test_chunk_rejects_escaping_paths_and_wrong_geometry() -> None:
    stream = _stream()
    chunk = stream.chunks[0]
    with pytest.raises(ValidationError, match="relative POSIX"):
        RecordingChunkV1.model_validate(
            {**chunk.model_dump(), "relative_path": "../escape.ci16.zst"}
        )
    with pytest.raises(ValidationError, match="byte count"):
        RecordingStreamV1.model_validate(
            {
                **stream.model_dump(),
                "chunks": ({**chunk.model_dump(), "uncompressed_bytes": 31},),
            }
        )


def test_manifest_cannot_call_an_incomplete_session_committed() -> None:
    stream = _stream()
    partial = RecordingStreamV1.model_validate(
        {
            **stream.model_dump(),
            "state": StreamState.PARTIAL,
            "captured_sample_count": 2,
            "chunks": (
                {
                    **stream.chunks[0].model_dump(),
                    "sample_count": 2,
                    "uncompressed_bytes": 16,
                },
            ),
            "error": "peer transport stopped",
        }
    )
    manifest = _manifest()
    with pytest.raises(ValidationError, match="requires all streams"):
        RecordingManifestV1.model_validate(
            {**manifest.model_dump(), "streams": (partial.model_dump(),)}
        )


def test_iq_metadata_schema_does_not_contain_sample_arrays() -> None:
    metadata = IqBlockMetadataV1(
        radio_id="radio-a",
        receiver_ids=(0,),
        sample_count=4,
        session_sample_start=0,
        host_request_utc_ns=NanosecondIntervalV1(lower_ns=1, upper_ns=2),
        host_request_monotonic_ns=NanosecondIntervalV1(lower_ns=3, upper_ns=4),
    )
    schema_text = str(IqBlockMetadataV1.model_json_schema()).lower()

    assert "ndarray" not in schema_text
    assert "samples" not in metadata.model_dump()
    with pytest.raises(ValidationError, match="Extra inputs"):
        IqBlockMetadataV1.model_validate(
            {**metadata.model_dump(), "samples": np.zeros((4, 1, 2), dtype="<i2")}
        )
