"""Small manifest-only examples for capability-bound rate-analysis tests."""

from __future__ import annotations

from pathlib import Path

from leo.contracts.continuity import IqContinuityBoundaryV1, IqGapMapV1
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    ContinuitySummaryV2,
    HostIdentityV1,
    ProducerV1,
    RecordingChunkV1,
    RecordingManifestV2,
    RecordingStreamV2,
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
from leo.domain.profiles import compile_capture_plan, load_profile_revision

_DIGEST = "sha256:" + "a" * 64
_ROOT = Path(__file__).parents[1]


def rate_manifest(sample_rate_hz: int) -> RecordingManifestV2:
    if sample_rate_hz == 3_000_000:
        profile_name = "starlink-ch4-lower-3m-60s-capture-v2.yaml"
        missing_by_stream = (0, 0)
        capture_state = CaptureState.COMMITTED
    elif sample_rate_hz == 5_000_000:
        profile_name = "starlink-ch4-lower-5m-60s-segmented-v2.yaml"
        missing_by_stream = (10, 20)
        capture_state = CaptureState.DEGRADED
    else:
        raise ValueError("test rate must be 3 or 5 MS/s")
    revision = load_profile_revision(_ROOT / "profiles" / profile_name)
    profile = revision.profile
    plan = compile_capture_plan(revision, ("radio-a", "radio-b"), source_type=SourceType.LIVE)
    requested_count = sample_rate_hz * 60
    centers = (959_687_500, 1_940_312_500)
    gain_modes = (GainMode.MANUAL, GainMode.SLOW_ATTACK)
    streams = []
    for ordinal, (missing, center, gain_mode) in enumerate(
        zip(missing_by_stream, centers, gain_modes, strict=True)
    ):
        observed = requested_count - missing
        requested = RadioSettingsV1(
            center_frequency_hz=center,
            sample_rate_hz=sample_rate_hz,
            bandwidth_hz=2_500_000,
            receiver_ids=(0, 1),
            gain_mode=gain_mode,
            gains=profile.gains if gain_mode is GainMode.MANUAL else (),
        )
        applied = requested.model_copy(update={"center_frequency_hz": center - 2})
        chunks = (
            RecordingChunkV1(
                chunk_index=0,
                segment_index=0,
                relative_path=f"streams/stream-{ordinal}/iq-000000.ci16.zst",
                sample_start=0,
                sample_count=observed if missing == 0 else 100,
                uncompressed_bytes=(observed if missing == 0 else 100) * 8,
                compressed_bytes=16,
                uncompressed_sha256=_DIGEST,
                compressed_sha256=_DIGEST,
            ),
        )
        if missing:
            chunks += (
                RecordingChunkV1(
                    chunk_index=1,
                    segment_index=1,
                    relative_path=f"streams/stream-{ordinal}/iq-000001.ci16.zst",
                    sample_start=100,
                    sample_count=observed - 100,
                    uncompressed_bytes=(observed - 100) * 8,
                    compressed_bytes=16,
                    uncompressed_sha256=_DIGEST,
                    compressed_sha256=_DIGEST,
                ),
            )
        streams.append(
            RecordingStreamV2(
                stream_id=f"stream-{ordinal}",
                radio=RadioIdentityV1(
                    radio_id=f"radio-{'ab'[ordinal]}",
                    serial=f"serial-{ordinal}",
                    uri=f"ip:192.0.2.{10 + ordinal}",
                    transport=RadioTransport.IIO_IP,
                ),
                requested_settings=requested,
                applied_settings=applied,
                state=StreamState.COMPLETE if missing == 0 else StreamState.PARTIAL,
                requested_sample_count=requested_count,
                captured_sample_count=observed,
                timing=_timing(ordinal),
                chunks=chunks,
                timeline_relative_path=f"streams/stream-{ordinal}/timeline.jsonl.zst",
                timeline_sha256=_DIGEST,
                gap_map_relative_path=f"streams/stream-{ordinal}/gap-map.json",
                gap_map_sha256=_DIGEST,
                continuity=ContinuitySummaryV2(
                    refill_count=1 if missing == 0 else 2,
                    segment_count=1 if missing == 0 else 2,
                    gap_count=int(missing > 0),
                    missing_sample_count=missing,
                    overflow_count=0,
                    sample_loss_observable=True,
                    first_source_sequence=0,
                    last_source_sequence=0 if missing == 0 else 1,
                    first_device_sample_counter=0,
                    last_device_sample_counter=requested_count - 1,
                    observed_sample_count=observed,
                    device_span_sample_count=requested_count,
                    kernel_buffers=8,
                    metadata_abi_version=1,
                    validated_stream_generation=f"generation-{ordinal}",
                    queue_capacity_refills=32,
                    queue_high_water_refills=1,
                ),
                error=None if missing == 0 else "counter gap preserved in gap map",
            )
        )
    runtime_tags = (
        "gain_mode:stream-0:manual",
        "gain_mode:stream-1:slow_attack",
        "tuning:stream-0:ch1:lower",
        "tuning:stream-1:ch4:upper",
        "tuning_policy:independent",
    )
    return RecordingManifestV2(
        session_id=f"rate-{sample_rate_hz}-session",
        state=capture_state,
        source_type=SourceType.LIVE,
        created_utc_ns=1_000,
        finalized_utc_ns=61_000_000_000,
        capture_plan=plan,
        tags=tuple(sorted((*profile.tags, *runtime_tags))),
        streams=tuple(streams),
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=SynchronizationMode.BEST_EFFORT,
            grade=SynchronizationGrade.BEST_EFFORT_OBSERVED,
            stream_ids=("stream-0", "stream-1"),
            release_target_monotonic_ns=500,
            estimated_start_skew_ns=1_000,
            start_skew_uncertainty_ns=100,
            estimated_overlap_ns=59_000_000_000,
            estimated_overlap_start_utc_ns=2_000,
            estimated_overlap_end_utc_ns=59_000_002_000,
            guaranteed_overlap_ns=58_000_000_000,
            overlap_fraction=0.98,
        ),
        compression=CompressionSettingsV1(policy_id=profile.storage_policy),
        host=HostIdentityV1(hostname="rate-analysis-test"),
        producer=ProducerV1(name="leo-acquisition", version="test"),
    )


def gap_map_for_stream(manifest: RecordingManifestV2, stream_id: str) -> IqGapMapV1:
    stream = next(item for item in manifest.streams if item.stream_id == stream_id)
    missing = stream.continuity.missing_sample_count
    boundaries = ()
    if missing:
        boundaries = (
            IqContinuityBoundaryV1(
                segment_index=1,
                stored_sample_offset=100,
                device_sample_offset=100,
                expected_device_sample_counter=100,
                actual_device_sample_counter=100 + missing,
                header_evidence_sha256=_DIGEST,
                observed_counter_gap_sample_count=missing,
                missing_sample_count=missing,
                reason="counter_gap",
            ),
        )
    assert stream.timeline_sha256 is not None
    return IqGapMapV1(
        stream_id=stream_id,
        timeline_sha256=stream.timeline_sha256,
        first_device_sample_counter=0,
        observed_sample_count=stream.captured_sample_count,
        device_span_sample_count=stream.continuity.device_span_sample_count,
        segment_count=len(boundaries) + 1,
        boundaries=boundaries,
    )


def mixed_five_m_manifest() -> RecordingManifestV2:
    """A degraded pair with one lossless path and one gap-backed partial path."""

    manifest = rate_manifest(5_000_000)
    first = manifest.streams[0]
    requested = first.requested_sample_count
    continuity = first.continuity.model_copy(
        update={
            "refill_count": 1,
            "segment_count": 1,
            "gap_count": 0,
            "missing_sample_count": 0,
            "first_source_sequence": 0,
            "last_source_sequence": 0,
            "observed_sample_count": requested,
            "device_span_sample_count": requested,
        }
    )
    chunk = first.chunks[0].model_copy(
        update={
            "sample_count": requested,
            "uncompressed_bytes": requested * 8,
        }
    )
    complete = RecordingStreamV2.model_validate(
        {
            **first.model_dump(mode="json"),
            "state": "complete",
            "captured_sample_count": requested,
            "chunks": [chunk.model_dump(mode="json")],
            "continuity": continuity.model_dump(mode="json"),
            "error": None,
        }
    )
    return RecordingManifestV2.model_validate(
        {
            **manifest.model_dump(mode="json"),
            "streams": [
                complete.model_dump(mode="json"),
                manifest.streams[1].model_dump(mode="json"),
            ],
        }
    )


def _timing(ordinal: int) -> StreamTimingV1:
    start = 1_000_000 + ordinal * 1_000
    return StreamTimingV1(
        release_target_monotonic_ns=500,
        release_observed_monotonic_ns=600 + ordinal,
        first_sample=TimingEstimateV1(
            estimate_utc_ns=start,
            earliest_utc_ns=start - 10,
            latest_utc_ns=start + 10,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
        last_sample=TimingEstimateV1(
            estimate_utc_ns=start + 60_000_000_000,
            earliest_utc_ns=start + 59_999_999_990,
            latest_utc_ns=start + 60_000_000_010,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
    )
