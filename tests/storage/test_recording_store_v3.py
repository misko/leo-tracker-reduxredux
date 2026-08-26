from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.profile import CapturePlanV2, CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.radio import IqBlockMetadataV2, RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    DeviceAxisRecordingChunkV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV3,
    RecordingStreamV3,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
    parse_recording_manifest_json,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    GainMode,
    PeerFailurePolicy,
    SourceType,
    StreamState,
    SynchronizationGrade,
    TimingMethod,
)
from leo.contracts.validity import DeviceAxisContentKind
from leo.domain.iq import IqBlock
from leo.domain.profiles import compile_capture_plan
from leo.radio.fake import FakeRadioSource
from leo.storage import BundleCorruptionError, BundleStateError, RecordingStore
from leo.storage.writer import (
    DeviceAxisStreamBundleWriter,
    DeviceAxisStreamWriteReceipt,
    RecordingBundleWriter,
    StreamQueueTelemetry,
)


@dataclass(frozen=True, slots=True)
class PreparedV3Bundle:
    store: RecordingStore
    writer: RecordingBundleWriter
    manifest: RecordingManifestV3
    receipt: DeviceAxisStreamWriteReceipt
    logical_iq: np.ndarray


def _prepare_v3_bundle(
    tmp_path: Path,
    session_id: str,
    *,
    sample_rate_hz: int = 5_000_000,
    requested_sample_count: int = 8,
    appended_refills: int = 2,
    gaps_before_blocks: dict[int, int] | None = None,
    overflow_blocks: tuple[int, ...] = (),
    terminal_refill: bool = False,
    genuine_observed_zeros: bool = False,
    target_uncompressed_bytes: int = 32,
) -> PreparedV3Bundle:
    receiver_ids = (0, 1)
    refill_samples = 4
    profile = CaptureProfileV2(
        name=f"v3-{session_id}",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=sample_rate_hz,
        bandwidth_hz=2_500_000,
        receivers=receiver_ids,
        gain_mode=GainMode.MANUAL,
        gains=tuple(
            ReceiverGainV1(receiver_id=receiver_id, gain_db=30.0) for receiver_id in receiver_ids
        ),
        sample_count=requested_sample_count,
        refill_samples=refill_samples,
        settle_seconds=Decimal(0),
        prime_refills=0,
        kernel_buffers=8,
        refill_queue_capacity=32,
        continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
        peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
        tags=("TEST",),
    )
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
        receiver_ids=receiver_ids,
        gain_mode=profile.gain_mode,
        gains=profile.gains,
    )
    radio = FakeRadioSource(
        "radio-a",
        seed=23,
        gaps_before_blocks=gaps_before_blocks,
        overflow_blocks=overflow_blocks,
    )
    radio.open()
    radio.configure(settings)
    radio.begin_metadata_capture(refill_samples, kernel_buffers=8)
    compression = CompressionSettingsV1(
        policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
        level=3,
        target_uncompressed_bytes=target_uncompressed_bytes,
    )
    store = RecordingStore(tmp_path / session_id)
    writer = store.begin(session_id, compression)
    stream_writer = writer.open_device_axis_stream(
        "stream-a",
        radio.identity,
        receiver_ids,
        requested_device_span=requested_sample_count,
        kernel_buffers=8,
    )
    expected = np.zeros((requested_sample_count, 2, 2), dtype="<i2")
    for _ in range(appended_refills):
        block = radio.read_block(refill_samples)
        if genuine_observed_zeros:
            block = IqBlock(samples=np.zeros_like(block.samples), metadata=block.metadata)
        assert block.metadata.device_sample_counter is not None
        device_start = block.metadata.device_sample_counter
        expected[device_start : device_start + block.metadata.sample_count] = block.samples
        stream_writer.append(block)
    terminal = radio.read_block(refill_samples).metadata if terminal_refill else None
    if terminal is not None:
        assert isinstance(terminal, IqBlockMetadataV2)
    receipt = stream_writer.finalize(
        queue_telemetry=StreamQueueTelemetry(
            capacity_refills=32,
            high_water_refills=2,
            maximum_refill_service_interval_ns=1_000,
        ),
        terminal_gap_metadata=terminal,
    )
    radio.close()
    partial = bool(receipt.zero_fill_sample_count or receipt.continuity.overflow_count)
    stream = RecordingStreamV3(
        stream_id="stream-a",
        radio=radio.identity,
        requested_settings=settings,
        applied_settings=settings,
        state=StreamState.PARTIAL if partial else StreamState.COMPLETE,
        requested_sample_count=requested_sample_count,
        logical_sample_count=receipt.logical_sample_count,
        observed_sample_count=receipt.observed_sample_count,
        zero_fill_sample_count=receipt.zero_fill_sample_count,
        timing=_timing(),
        chunks=receipt.chunks,
        observed_iq_sha256=receipt.observed_iq_sha256,
        logical_iq_sha256=receipt.logical_iq_sha256,
        timeline_relative_path=receipt.timeline_relative_path,
        timeline_sha256=receipt.timeline_sha256,
        gap_map_relative_path=receipt.gap_map_relative_path,
        gap_map_sha256=receipt.gap_map_sha256,
        validity_inventory_relative_path=receipt.validity_inventory_relative_path,
        validity_inventory_sha256=receipt.validity_inventory_sha256,
        continuity=receipt.continuity,
        error="counter-proven observation integrity loss" if partial else None,
    )
    manifest = RecordingManifestV3(
        session_id=session_id,
        state=CaptureState.DEGRADED if partial else CaptureState.COMMITTED,
        source_type=SourceType.TEST,
        created_utc_ns=1_700_000_000_000_000_000,
        finalized_utc_ns=1_700_000_002_000_000_000,
        capture_plan=plan,
        tags=("TEST",),
        streams=(stream,),
        synchronization=SynchronizationSummaryV1(
            requested_mode=plan.requested_synchronization_mode,
            effective_mode=plan.effective_synchronization_mode,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=("stream-a",),
        ),
        compression=compression,
        host=HostIdentityV1(hostname="v3-storage-test", machine_id="test-machine"),
        producer=ProducerV1(name="leo-v3-storage-test", version="1"),
    )
    return PreparedV3Bundle(store, writer, manifest, receipt, expected)


def _timing() -> StreamTimingV1:
    return StreamTimingV1(
        first_sample=TimingEstimateV1(
            estimate_utc_ns=1_700_000_000_000_000_000,
            earliest_utc_ns=1_700_000_000_000_000_000,
            latest_utc_ns=1_700_000_000_001_000_000,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
        last_sample=TimingEstimateV1(
            estimate_utc_ns=1_700_000_001_000_000_000,
            earliest_utc_ns=1_700_000_000_999_000_000,
            latest_utc_ns=1_700_000_001_001_000_000,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
    )


def _decompress(path: Path) -> bytes:
    with (
        path.open("rb") as source,
        zstd.ZstdDecompressor().stream_reader(source) as reader,
    ):
        return reader.read()


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 3_000_000, 5_000_000))
def test_v3_lossless_round_trip_has_fixed_device_axis_and_validity(
    tmp_path: Path,
    sample_rate_hz: int,
) -> None:
    prepared = _prepare_v3_bundle(
        tmp_path,
        f"v3-lossless-{sample_rate_hz}",
        sample_rate_hz=sample_rate_hz,
    )

    published = prepared.writer.publish(prepared.manifest)
    inspected = prepared.store.inspect(published.session_id)
    report = prepared.store.verify(inspected)

    assert inspected.manifest == prepared.manifest
    assert (
        parse_recording_manifest_json((published.path / "manifest.json").read_bytes())
        == prepared.manifest
    )
    assert report.validity_inventory_count == 1
    assert report.gap_map_count == 1
    assert report.uncompressed_bytes == prepared.logical_iq.nbytes
    expected_digest = sha256_digest(prepared.logical_iq.tobytes(order="C"))
    assert prepared.receipt.observed_iq_sha256 == expected_digest
    assert prepared.receipt.logical_iq_sha256 == expected_digest
    np.testing.assert_array_equal(
        prepared.store.read_ci16(published, "stream-a", 0, 8),
        prepared.logical_iq,
    )
    reader = prepared.store.reader(published, "stream-a")
    span = reader.read_device_span(0, 8)
    assert span.valid_samples.all()
    assert set(span.continuity_segment_ids) == {0}
    with pytest.raises(ValueError, match="validity-aware"):
        reader.read(0, 1)


def test_v3_internal_gap_is_physical_zero_and_remains_observation_partial(
    tmp_path: Path,
) -> None:
    prepared = _prepare_v3_bundle(
        tmp_path,
        "v3-internal-gap",
        requested_sample_count=12,
        gaps_before_blocks={1: 4},
    )
    published = prepared.writer.publish(prepared.manifest)

    assert prepared.manifest.state is CaptureState.DEGRADED
    stream = prepared.manifest.streams[0]
    assert stream.state is StreamState.PARTIAL
    assert stream.observed_sample_count == 8
    assert stream.zero_fill_sample_count == 4
    assert [chunk.content_kind for chunk in stream.chunks] == [
        DeviceAxisContentKind.OBSERVED,
        DeviceAxisContentKind.ZERO_FILL,
        DeviceAxisContentKind.OBSERVED,
    ]
    assert [chunk.continuity_segment_index for chunk in stream.chunks] == [0, None, 1]
    assert prepared.receipt.logical_iq_sha256 == sha256_digest(
        prepared.logical_iq.tobytes(order="C")
    )
    assert prepared.receipt.observed_iq_sha256 == sha256_digest(
        prepared.logical_iq[:4].tobytes(order="C") + prepared.logical_iq[8:].tobytes(order="C")
    )
    np.testing.assert_array_equal(
        prepared.store.read_ci16(published, "stream-a", 0, 12),
        prepared.logical_iq,
    )
    reader = prepared.store.reader(published, "stream-a")
    validity = reader.validity_inventory()
    assert [run.content_kind for run in validity.runs] == [
        DeviceAxisContentKind.OBSERVED,
        DeviceAxisContentKind.ZERO_FILL,
        DeviceAxisContentKind.OBSERVED,
    ]
    span = reader.read_device_span(0, 12)
    assert span.valid_samples.tolist() == [True] * 4 + [False] * 4 + [True] * 4
    assert span.continuity_segment_ids.tolist() == [0] * 4 + [-1] * 4 + [1] * 4
    assert prepared.store.verify(published).validity_inventory_count == 1


def test_v3_overflow_only_boundary_splits_segments_without_a_zero_run(
    tmp_path: Path,
) -> None:
    prepared = _prepare_v3_bundle(
        tmp_path,
        "v3-overflow-boundary",
        overflow_blocks=(1,),
    )
    published = prepared.writer.publish(prepared.manifest)
    validity = prepared.store.reader(published, "stream-a").validity_inventory()

    assert prepared.receipt.zero_fill_sample_count == 0
    assert prepared.receipt.continuity.overflow_count == 1
    assert [run.continuity_segment_index for run in validity.runs] == [0, 1]
    assert len(validity.segments) == 2
    assert validity.segments[1].preceding_missing_sample_count == 0
    assert validity.segments[1].preceding_boundary_reason == "overflow_flag"


def test_v3_multiple_gaps_close_one_canonical_device_axis(tmp_path: Path) -> None:
    prepared = _prepare_v3_bundle(
        tmp_path,
        "v3-multiple-gaps",
        requested_sample_count=20,
        appended_refills=3,
        gaps_before_blocks={1: 4, 2: 4},
    )
    published = prepared.writer.publish(prepared.manifest)
    validity = prepared.store.reader(published, "stream-a").validity_inventory()

    assert validity.logical_sample_count == 20
    assert validity.observed_sample_count == 12
    assert validity.missing_sample_count == 8
    assert len(validity.segments) == 3
    assert [run.content_kind for run in validity.runs] == [
        DeviceAxisContentKind.OBSERVED,
        DeviceAxisContentKind.ZERO_FILL,
        DeviceAxisContentKind.OBSERVED,
        DeviceAxisContentKind.ZERO_FILL,
        DeviceAxisContentKind.OBSERVED,
    ]
    assert prepared.store.verify(published).validity_inventory_count == 1


def test_v3_terminal_gap_persists_zeros_and_an_empty_terminal_segment(
    tmp_path: Path,
) -> None:
    prepared = _prepare_v3_bundle(
        tmp_path,
        "v3-terminal-gap",
        requested_sample_count=12,
        appended_refills=1,
        gaps_before_blocks={1: 8},
        terminal_refill=True,
    )
    published = prepared.writer.publish(prepared.manifest)
    reader = prepared.store.reader(published, "stream-a")
    validity = reader.validity_inventory()

    assert prepared.receipt.zero_fill_sample_count == 8
    assert prepared.receipt.continuity.terminal_gap is not None
    assert len(validity.segments) == 2
    assert validity.segments[-1].observed_sample_count == 0
    assert validity.segments[-1].device_sample_start == 12
    assert validity.segments[-1].device_sample_stop == 12
    np.testing.assert_array_equal(
        prepared.store.read_ci16(published, "stream-a", 4, 8),
        np.zeros((8, 2, 2), dtype="<i2"),
    )


def test_v3_genuine_observed_zero_iq_remains_valid(
    tmp_path: Path,
) -> None:
    prepared = _prepare_v3_bundle(
        tmp_path,
        "v3-observed-zeros",
        genuine_observed_zeros=True,
    )
    published = prepared.writer.publish(prepared.manifest)

    assert all(
        chunk.content_kind is DeviceAxisContentKind.OBSERVED for chunk in prepared.receipt.chunks
    )
    assert prepared.store.verify(published).validity_inventory_count == 1
    span = prepared.store.reader(published, "stream-a").read_device_span(0, 8)
    assert span.valid_samples.all()
    assert not span.samples.any()


def test_v3_semantic_evidence_is_invariant_to_physical_chunk_partitioning(
    tmp_path: Path,
) -> None:
    narrow = _prepare_v3_bundle(
        tmp_path,
        "v3-partition-narrow",
        requested_sample_count=12,
        gaps_before_blocks={1: 4},
        target_uncompressed_bytes=16,
    )
    wide = _prepare_v3_bundle(
        tmp_path,
        "v3-partition-wide",
        requested_sample_count=12,
        gaps_before_blocks={1: 4},
        target_uncompressed_bytes=64,
    )
    narrow_bundle = narrow.writer.publish(narrow.manifest)
    wide_bundle = wide.writer.publish(wide.manifest)

    assert len(narrow.receipt.chunks) > len(wide.receipt.chunks)
    assert narrow.receipt.observed_iq_sha256 == wide.receipt.observed_iq_sha256
    assert narrow.receipt.logical_iq_sha256 == wide.receipt.logical_iq_sha256
    assert (
        narrow.store.reader(narrow_bundle, "stream-a").validity_inventory()
        == wide.store.reader(wide_bundle, "stream-a").validity_inventory()
    )


def test_v3_unknown_tail_and_queue_failure_refuse_a_receipt(tmp_path: Path) -> None:
    for session_id, queue_failures in (("v3-unknown-tail", 0), ("v3-queue-failure", 1)):
        profile = _prepare_unfinalized_v3(tmp_path, session_id)
        with pytest.raises(
            BundleStateError,
            match="endpoint is unproven" if not queue_failures else "enqueue failure",
        ):
            profile[1].finalize(
                queue_telemetry=StreamQueueTelemetry(
                    capacity_refills=32,
                    high_water_refills=1,
                    enqueue_failure_count=queue_failures,
                )
            )
        profile[1].abort()
        profile[0].close()
        profile[2].close()
        assert (profile[0].spool_path).is_dir()


def _prepare_unfinalized_v3(
    tmp_path: Path,
    session_id: str,
) -> tuple[RecordingBundleWriter, DeviceAxisStreamBundleWriter, FakeRadioSource]:
    profile = CaptureProfileV2(
        name=session_id,
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=5_000_000,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30),
            ReceiverGainV1(receiver_id=1, gain_db=30),
        ),
        sample_count=8,
        refill_samples=4,
        kernel_buffers=8,
        peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
    )
    settings = RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=profile.receivers,
        gain_mode=profile.gain_mode,
        gains=profile.gains,
    )
    radio = FakeRadioSource("radio-a")
    radio.open()
    radio.configure(settings)
    radio.begin_metadata_capture(4, kernel_buffers=8)
    store = RecordingStore(tmp_path / session_id)
    writer = store.begin(
        session_id,
        CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=32,
        ),
    )
    stream = writer.open_device_axis_stream(
        "stream-a",
        radio.identity,
        (0, 1),
        requested_device_span=8,
        kernel_buffers=8,
    )
    stream.append(radio.read_block(4))
    return writer, stream, radio


def test_v3_verifier_rejects_nonzero_bytes_even_with_rewritten_digests(
    tmp_path: Path,
) -> None:
    prepared = _prepare_v3_bundle(
        tmp_path,
        "v3-zero-tamper",
        requested_sample_count=12,
        gaps_before_blocks={1: 4},
    )
    published = prepared.writer.publish(prepared.manifest)
    assert isinstance(published.manifest, RecordingManifestV3)
    stream = published.manifest.streams[0]
    zero_index = next(
        index
        for index, chunk in enumerate(stream.chunks)
        if chunk.content_kind is DeviceAxisContentKind.ZERO_FILL
    )
    zero_chunk = stream.chunks[zero_index]
    zero_path = published.path / zero_chunk.relative_path
    uncompressed = bytearray(_decompress(zero_path))
    uncompressed[0] = 1
    compressed = zstd.ZstdCompressor(level=prepared.manifest.compression.level).compress(
        uncompressed
    )
    zero_path.write_bytes(compressed)

    chunks = list(stream.chunks)
    chunks[zero_index] = DeviceAxisRecordingChunkV1.model_validate(
        {
            **zero_chunk.model_dump(),
            "compressed_bytes": len(compressed),
            "uncompressed_sha256": sha256_digest(bytes(uncompressed)),
            "compressed_sha256": sha256_digest(compressed),
        }
    )
    logical = hashlib.sha256()
    for chunk in chunks:
        payload = _decompress(published.path / chunk.relative_path)
        logical.update(payload)
    altered_stream = stream.model_copy(
        update={
            "chunks": tuple(chunks),
            "logical_iq_sha256": f"sha256:{logical.hexdigest()}",
        }
    )
    altered_manifest = published.manifest.model_copy(update={"streams": (altered_stream,)})
    (published.path / "manifest.json").write_bytes(
        canonical_json_bytes(altered_manifest.model_dump(mode="json"))
    )

    inspected = prepared.store.inspect(published.session_id)
    with pytest.raises(BundleCorruptionError, match="zero-fill chunk contains observed bytes"):
        prepared.store.reader(inspected, "stream-a").read_device_span(4, 4)
    with pytest.raises(BundleCorruptionError, match="zero-fill chunk contains observed bytes"):
        prepared.store.verify(inspected)


def test_v3_validity_sidecar_tamper_fails_before_science_reads(tmp_path: Path) -> None:
    prepared = _prepare_v3_bundle(tmp_path, "v3-validity-tamper")
    published = prepared.writer.publish(prepared.manifest)
    assert isinstance(published.manifest, RecordingManifestV3)
    stream = published.manifest.streams[0]
    path = published.path / stream.validity_inventory_relative_path
    document = json.loads(path.read_bytes())
    document["first_device_sample_counter"] += 1
    payload = canonical_json_bytes(document)
    path.write_bytes(payload)
    altered_stream = stream.model_copy(update={"validity_inventory_sha256": sha256_digest(payload)})
    altered_manifest = published.manifest.model_copy(update={"streams": (altered_stream,)})
    (published.path / "manifest.json").write_bytes(
        canonical_json_bytes(altered_manifest.model_dump(mode="json"))
    )

    with pytest.raises(BundleCorruptionError, match="disagrees with verified counter evidence"):
        prepared.store.verify(prepared.store.inspect(published.session_id))
