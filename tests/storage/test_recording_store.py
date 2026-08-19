from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV1,
    RecordingStreamV1,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    GainMode,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.domain.profiles import compile_capture_plan
from leo.radio.fake import FakeRadioSource
from leo.storage import (
    BundleCorruptionError,
    BundleStateError,
    PathConfinementError,
    RecordingStore,
)
from leo.storage.writer import RecordingBundleWriter, StreamWriteReceipt


@dataclass(frozen=True, slots=True)
class PreparedBundle:
    writer: RecordingBundleWriter
    manifest: RecordingManifestV1
    receipt: StreamWriteReceipt
    expected: np.ndarray


def _prepare_bundle(
    store: RecordingStore,
    session_id: str,
    *,
    block_sizes: tuple[int, ...] = (3, 3),
    receiver_ids: tuple[int, ...] = (0, 1),
    target_bytes: int = 32,
    gaps_before_blocks: dict[int, int] | None = None,
    failure_injector=None,
) -> PreparedBundle:
    sample_count = sum(block_sizes)
    profile = CaptureProfileV1(
        name=f"profile-{session_id}",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=receiver_ids,
        gain_mode=GainMode.MANUAL,
        gains=tuple(
            ReceiverGainV1(receiver_id=receiver, gain_db=30.0) for receiver in receiver_ids
        ),
        sample_count=sample_count,
        storage_policy="test-zstd-v1",
        tags=("TEST",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        ["radio-a"],
        source_type=SourceType.TEST,
    )
    compression = CompressionSettingsV1(
        policy_id="test-zstd-v1",
        level=3,
        target_uncompressed_bytes=target_bytes,
    )
    settings = RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=receiver_ids,
        gain_mode=GainMode.MANUAL,
        gains=tuple(
            ReceiverGainV1(receiver_id=receiver, gain_db=30.0) for receiver in receiver_ids
        ),
    )
    radio = FakeRadioSource(
        "radio-a",
        receiver_count=2,
        seed=17,
        gaps_before_blocks=gaps_before_blocks,
    )
    radio.open()
    radio.configure(settings)
    writer = store.begin(
        session_id,
        compression,
        failure_injector=failure_injector,
    )
    stream_writer = writer.open_stream("stream-a", radio.identity, receiver_ids)
    blocks = []
    for size in block_sizes:
        block = radio.read_block(size)
        blocks.append(block.samples.copy())
        stream_writer.append(block)
    receipt = stream_writer.finalize()
    radio.close()
    expected = np.concatenate(blocks, axis=0)
    timing = StreamTimingV1(
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
    stream = RecordingStreamV1(
        stream_id="stream-a",
        radio=radio.identity,
        requested_settings=settings,
        applied_settings=settings,
        state=StreamState.COMPLETE,
        requested_sample_count=sample_count,
        captured_sample_count=receipt.captured_sample_count,
        timing=timing,
        chunks=receipt.chunks,
        timeline_relative_path=receipt.timeline_relative_path,
        timeline_sha256=receipt.timeline_sha256,
        continuity=receipt.continuity,
    )
    manifest = RecordingManifestV1(
        session_id=session_id,
        state=CaptureState.COMMITTED,
        source_type=SourceType.TEST,
        created_utc_ns=1_700_000_000_000_000_000,
        finalized_utc_ns=1_700_000_002_000_000_000,
        capture_plan=plan,
        tags=("TEST",),
        streams=(stream,),
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=SynchronizationMode.NONE,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=("stream-a",),
        ),
        compression=compression,
        host=HostIdentityV1(hostname="storage-test-host", machine_id="test-machine"),
        producer=ProducerV1(name="leo-storage-test", version="1"),
    )
    return PreparedBundle(writer, manifest, receipt, expected)


def _read_zstd(path: Path) -> bytes:
    with path.open("rb") as source, zstd.ZstdDecompressor().stream_reader(source) as reader:
        return reader.read()


def test_independent_shards_publish_and_read_exactly_across_boundaries(
    tmp_path: Path,
) -> None:
    store = RecordingStore(tmp_path / "bulk")
    prepared = _prepare_bundle(store, "session-cross-shard")

    published = prepared.writer.publish(prepared.manifest)

    assert not prepared.writer.spool_path.exists()
    assert published.path == (store.recordings_root / "2023" / "11" / "14" / "session-cross-shard")
    assert (published.path / "manifest.json").is_file()
    assert len(prepared.receipt.chunks) == 2
    assert all(chunk.sample_count == 3 for chunk in prepared.receipt.chunks)
    assert store.resolve_uri(published.uri) == published.path
    assert store.inspect("session-cross-shard").manifest == prepared.manifest
    assert store.inspect_uri(published.uri).manifest_sha256 == published.manifest_sha256

    result = store.read_ci16("session-cross-shard", "stream-a", 2, 3)
    selected = store.read_ci16(
        published,
        "stream-a",
        1,
        4,
        receiver_ids=(1,),
    )
    empty = store.read_ci16(published, "stream-a", 6, 0)
    np.testing.assert_array_equal(result, prepared.expected[2:5])
    np.testing.assert_array_equal(selected, prepared.expected[1:5, (1,), :])
    assert empty.shape == (0, 2, 2)

    report = store.verify(published)
    assert report.chunk_count == 2
    assert report.uncompressed_bytes == prepared.expected.nbytes
    assert report.timeline_count == 1
    timeline = _read_zstd(published.path / prepared.receipt.timeline_relative_path)
    records = [json.loads(line) for line in timeline.splitlines()]
    assert [record["session_sample_start"] for record in records] == [0, 3]

    reader = store.reader(published, "stream-a")
    blocks = list(reader.iter_blocks(block_samples=2))
    assert reader.sample_rate_hz == 2_500_000
    assert reader.center_frequency_hz == 1_700_000_000
    assert reader.sample_count == 6
    assert reader.receiver_ids == (0, 1)
    assert [block.metadata.session_sample_start for block in blocks] == [0, 2, 3, 5]
    assert all(block.metadata.sample_count <= 2 for block in blocks)
    np.testing.assert_array_equal(
        np.concatenate([block.samples for block in blocks], axis=0),
        prepared.expected,
    )


def test_shards_end_only_on_refill_or_continuity_boundaries(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    oversized = _prepare_bundle(
        store,
        "session-refill-aligned",
        block_sizes=(5, 1),
        target_bytes=32,
    )
    published = oversized.writer.publish(oversized.manifest)

    assert [chunk.sample_count for chunk in oversized.receipt.chunks] == [5, 1]
    np.testing.assert_array_equal(
        store.read_ci16(published, "stream-a", 0, 6),
        oversized.expected,
    )

    segmented = _prepare_bundle(
        store,
        "session-gap-segmented",
        block_sizes=(2, 2),
        target_bytes=1024,
        gaps_before_blocks={1: 7},
    )
    segmented.writer.publish(segmented.manifest)
    assert [chunk.segment_index for chunk in segmented.receipt.chunks] == [0, 1]
    assert segmented.receipt.continuity.segment_count == 2
    assert segmented.receipt.continuity.gap_count == 1
    assert segmented.receipt.continuity.missing_sample_count == 7


def test_range_reader_rejects_invalid_ranges_and_receivers(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    prepared = _prepare_bundle(store, "session-range-errors", receiver_ids=(0,))
    published = prepared.writer.publish(prepared.manifest)

    with pytest.raises(ValueError, match="negative"):
        store.read_ci16(published, "stream-a", -1, 1)
    with pytest.raises(ValueError, match="exceeds"):
        store.read_ci16(published, "stream-a", 5, 2)
    with pytest.raises(ValueError, match="absent"):
        store.read_ci16(published, "stream-a", 0, 1, receiver_ids=(1,))


def test_verification_detects_compressed_corruption(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    prepared = _prepare_bundle(store, "session-corrupt")
    published = prepared.writer.publish(prepared.manifest)
    chunk_path = published.path / prepared.receipt.chunks[0].relative_path
    payload = bytearray(chunk_path.read_bytes())
    payload[len(payload) // 2] ^= 0x80
    chunk_path.write_bytes(payload)

    # Inspection is deliberately bounded to schema, confinement, existence, and size.
    assert store.inspect("session-corrupt").session_id == "session-corrupt"
    with pytest.raises(BundleCorruptionError, match="digest mismatch"):
        store.verify(published)
    with pytest.raises(BundleCorruptionError, match="digest mismatch"):
        store.read_ci16(published, "stream-a", 0, 1)


@pytest.mark.parametrize(
    "uri",
    [
        "file:///srv/bulk/leo/recordings/a",
        "bulk://spool/session.partial",
        "bulk://recordings/../../mnt/qnap01/data",
        "bulk://recordings/%2e%2e/escape",
        "bulk://recordings/a/%2fetc",
        "bulk://recordings/a//b",
    ],
)
def test_bulk_uri_resolver_rejects_escape_and_private_namespaces(
    tmp_path: Path,
    uri: str,
) -> None:
    store = RecordingStore(tmp_path / "bulk")
    with pytest.raises(PathConfinementError):
        store.resolve_uri(uri, must_exist=False)


def test_inspection_rejects_a_symlinked_bundle_object(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "bulk")
    prepared = _prepare_bundle(store, "session-symlink")
    published = prepared.writer.publish(prepared.manifest)
    chunk_path = published.path / prepared.receipt.chunks[0].relative_path
    outside = tmp_path / "outside.ci16.zst"
    outside.write_bytes(chunk_path.read_bytes())
    chunk_path.unlink()
    chunk_path.symlink_to(outside)

    with pytest.raises(BundleCorruptionError, match="escapes"):
        store.inspect("session-symlink")


@pytest.mark.parametrize(
    ("failure_point", "is_committed", "manifest_name"),
    [
        ("after_manifest_fsync", False, "manifest.json.partial"),
        ("after_manifest_rename", False, "manifest.json"),
        ("after_session_rename", True, "manifest.json"),
        ("after_recordings_parent_fsync", True, "manifest.json"),
    ],
)
def test_publication_faults_are_unambiguously_partial_or_committed(
    tmp_path: Path,
    failure_point: str,
    is_committed: bool,
    manifest_name: str,
) -> None:
    class InjectedFailure(RuntimeError):
        pass

    def inject(point: str) -> None:
        if point == failure_point:
            raise InjectedFailure(point)

    store = RecordingStore(tmp_path / "bulk")
    session_id = f"fault-{failure_point}"
    prepared = _prepare_bundle(store, session_id, failure_injector=inject)
    with pytest.raises(InjectedFailure, match=failure_point):
        prepared.writer.publish(prepared.manifest)

    report = store.reconcile()
    if is_committed:
        assert [item.session_id for item in report.committed] == [session_id]
        assert report.issues == ()
        assert prepared.writer.published_path is not None
        assert (prepared.writer.published_path / manifest_name).is_file()
        assert not prepared.writer.spool_path.exists()
    else:
        assert report.committed == ()
        assert prepared.writer.published_path is None
        assert (prepared.writer.spool_path / manifest_name).is_file()


def test_reconcile_reports_invalid_final_directories_and_ignores_spool(
    tmp_path: Path,
) -> None:
    store = RecordingStore(tmp_path / "bulk")
    first = _prepare_bundle(store, "session-reconcile-a")
    second = _prepare_bundle(store, "session-reconcile-b")
    first.writer.publish(first.manifest)
    second.writer.publish(second.manifest)
    (store.spool_root / "unfinished.partial").mkdir()
    broken = store.recordings_root / "2023" / "11" / "14" / "broken-session"
    broken.mkdir()

    report = store.reconcile()

    assert [item.session_id for item in report.committed] == [
        "session-reconcile-a",
        "session-reconcile-b",
    ]
    assert len(report.issues) == 1
    assert report.issues[0].path == broken
    assert "manifest.json" in report.issues[0].error


def test_publish_rejects_manifest_that_disagrees_with_written_receipt(
    tmp_path: Path,
) -> None:
    store = RecordingStore(tmp_path / "bulk")
    prepared = _prepare_bundle(store, "session-inventory-mismatch")
    stream = prepared.manifest.streams[0]
    altered_stream = RecordingStreamV1.model_validate(
        {
            **stream.model_dump(),
            "timeline_sha256": "sha256:" + "f" * 64,
        }
    )
    altered_manifest = RecordingManifestV1.model_validate(
        {
            **prepared.manifest.model_dump(),
            "streams": (altered_stream.model_dump(),),
        }
    )

    with pytest.raises(BundleStateError, match="inventory disagrees"):
        prepared.writer.publish(altered_manifest)
    assert not tuple(store.recordings_root.glob("*/*/*/session-inventory-mismatch"))
