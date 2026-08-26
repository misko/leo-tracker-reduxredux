from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import zstandard as zstd

from leo.catalog import CaptureRecordingIdentity, RunExecutionInfo
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.recording import DeviceAxisRecordingChunkV1, RecordingManifestV3
from leo.contracts.validity import DeviceAxisContentKind
from leo.pipeline import ScopeIdentityV1, WindowValidity
from leo.processing import RecordingIqReaderProvider
from leo.radio import FakeRadioSource
from leo.storage import BundleCorruptionError
from tests.acquisition.test_continuity_capture_v2 import _coordinator, _plan
from tests.storage.test_recording_store_v3 import _decompress, _prepare_v3_bundle


def test_v3_provider_exposes_only_verified_mandatory_validity_iq(tmp_path: Path) -> None:
    prepared = _prepare_v3_bundle(
        tmp_path,
        "provider-v3-gap",
        requested_sample_count=12,
        gaps_before_blocks={1: 4},
    )
    published = prepared.writer.publish(prepared.manifest)
    provider = RecordingIqReaderProvider(
        prepared.store,
        allow_unpinned_integrity_for_tests=True,
    )
    attestation = provider.verify_integrity(_identity(published))
    assert (
        provider.verified_validity_inventory(
            attestation.attestation_digest,
            "stream-a",
        )
        == prepared.store.reader(published, "stream-a").validity_inventory()
    )
    execution = _execution(published, attestation)
    scope = _scope(published.session_id, "stream-a")

    with pytest.raises(ValueError, match="validity-aware"):
        provider.open_scope(execution, scope)

    reader = provider.open_validity_scope(execution, scope)
    assert reader.sample_rate_hz == 5_000_000
    assert reader.sample_count == 12
    assert reader.observed_sample_count == 8
    assert reader.missing_sample_count == 4
    assert reader.receiver_ids == (0,)

    span = reader.read_device_span(0, 12)
    np.testing.assert_array_equal(span.samples, prepared.logical_iq[:, 0:1, :])
    assert span.valid_samples.tolist() == [True] * 4 + [False] * 4 + [True] * 4
    assert span.continuity_segment_ids.tolist() == [0] * 4 + [-1] * 4 + [1] * 4
    assert not span.samples[4:8].any()

    masked = tuple(reader.iter_masked_blocks(block_samples=3))
    assert [block.device_sample_start for block in masked] == [0, 3, 4, 7, 8, 11]
    assert sum(block.sample_count for block in masked) == 12
    valid = tuple(reader.iter_valid_blocks(block_samples=3))
    assert [block.device_sample_start for block in valid] == [0, 3, 8, 11]
    np.testing.assert_array_equal(
        np.concatenate([block.samples for block in valid]),
        np.concatenate((prepared.logical_iq[:4, 0:1, :], prepared.logical_iq[8:, 0:1, :])),
    )

    segments = reader.segment_readers()
    assert [segment.global_device_sample_start for segment in segments] == [0, 8]
    assert [segment.sample_count for segment in segments] == [4, 4]
    np.testing.assert_array_equal(
        np.concatenate([block.samples for block in segments[1].iter_blocks(block_samples=3)]),
        prepared.logical_iq[8:, 0:1, :],
    )
    assert reader.classify_window(3, 6).status is WindowValidity.GAP_OVERLAP
    assert reader.classify_window(8, 4).status is WindowValidity.VALID

    provider.close()
    np.testing.assert_array_equal(
        reader.read_device_span(8, 4).samples,
        prepared.logical_iq[8:, 0:1, :],
    )
    reader.close()
    reader.close()
    with pytest.raises(RuntimeError, match="closed"):
        reader.read_device_span(0, 1)


@pytest.mark.parametrize(
    ("gaps_before_blocks", "logical_sample_count"),
    (({}, 8), ({1: 4}, 12)),
)
def test_v2_synthesized_and_v3_physical_views_are_bit_and_digest_equivalent(
    tmp_path: Path,
    gaps_before_blocks: dict[int, int],
    logical_sample_count: int,
) -> None:
    suffix = "gapped" if gaps_before_blocks else "lossless"
    v3 = _prepare_v3_bundle(
        tmp_path / "v3",
        f"parity-v3-{suffix}",
        requested_sample_count=logical_sample_count,
        gaps_before_blocks=gaps_before_blocks,
    )
    v3_published = v3.writer.publish(v3.manifest)
    v2_coordinator = _coordinator(tmp_path / "v2")
    v2_result = v2_coordinator.capture_once(
        _plan(sample_count=logical_sample_count, sample_rate_hz=5_000_000),
        {
            "radio-a": FakeRadioSource(
                "radio-a",
                seed=23,
                gaps_before_blocks=gaps_before_blocks,
            )
        },
        session_id=f"parity-v2-{suffix}",
    )
    assert v2_result.bundle is not None
    v2_published = v2_result.bundle

    v2_provider = RecordingIqReaderProvider(
        v2_coordinator.store,
        allow_unpinned_integrity_for_tests=True,
    )
    v3_provider = RecordingIqReaderProvider(
        v3.store,
        allow_unpinned_integrity_for_tests=True,
    )
    v2_attestation = v2_provider.verify_integrity(_identity(v2_published))
    v3_attestation = v3_provider.verify_integrity(_identity(v3_published))
    v2_evidence = v2_provider.verified_historical_v2_native_stream_evidence(
        v2_attestation.attestation_digest,
        "stream-0",
    )
    v3_stream = v3_published.manifest.streams[0]
    assert v2_evidence.raw_integrity_attestation_digest == v2_attestation.attestation_digest
    assert v2_evidence.selected_stream_digest == canonical_digest(
        v2_published.manifest.streams[0].model_dump(mode="json")
    )
    assert v2_evidence.uncompressed_chunk_closure_digest == (
        v2_attestation.streams[0].uncompressed_closure_digest
    )
    assert v2_evidence.observed_iq_digest == v3_stream.observed_iq_sha256
    assert v2_evidence.logical_iq_digest == v3_stream.logical_iq_sha256
    assert (v2_evidence.observed_iq_digest == v2_evidence.logical_iq_digest) is (
        not gaps_before_blocks
    )
    v2_reader = v2_provider.open_validity_scope(
        _execution(v2_published, v2_attestation),
        _scope(v2_published.session_id, "stream-0"),
    )
    v3_reader = v3_provider.open_validity_scope(
        _execution(v3_published, v3_attestation),
        _scope(v3_published.session_id, "stream-a"),
    )

    v2_span = v2_reader.read_device_span(0, logical_sample_count)
    v3_span = v3_reader.read_device_span(0, logical_sample_count)
    np.testing.assert_array_equal(v3_span.samples, v2_span.samples)
    np.testing.assert_array_equal(v3_span.valid_samples, v2_span.valid_samples)
    np.testing.assert_array_equal(
        v3_span.continuity_segment_ids,
        v2_span.continuity_segment_ids,
    )
    assert [
        (
            run.content_kind,
            run.device_sample_start,
            run.sample_count,
            run.stored_sample_start,
            run.continuity_segment_index,
        )
        for run in v3_reader.validity_inventory.runs
    ] == [
        (
            run.content_kind,
            run.device_sample_start,
            run.sample_count,
            run.stored_sample_start,
            run.continuity_segment_index,
        )
        for run in v2_reader.validity_inventory.runs
    ]
    assert [
        (
            segment.device_sample_start,
            segment.device_sample_stop,
            segment.stored_sample_start,
            segment.stored_sample_stop,
            segment.preceding_missing_sample_count,
            segment.preceding_boundary_reason,
        )
        for segment in v3_reader.validity_inventory.segments
    ] == [
        (
            segment.device_sample_start,
            segment.device_sample_stop,
            segment.stored_sample_start,
            segment.stored_sample_stop,
            segment.preceding_missing_sample_count,
            segment.preceding_boundary_reason,
        )
        for segment in v2_reader.validity_inventory.segments
    ]
    for start in range(logical_sample_count):
        for count in range(1, logical_sample_count + 1 - start):
            assert v3_reader.classify_window(start, count) == v2_reader.classify_window(
                start,
                count,
            )

    v2_reader.close()
    v3_reader.close()
    v2_provider.close()
    v3_provider.close()


def test_v3_provider_rejects_validity_and_physical_zero_tamper(tmp_path: Path) -> None:
    validity = _prepare_v3_bundle(
        tmp_path / "validity",
        "provider-v3-validity-tamper",
        requested_sample_count=12,
        gaps_before_blocks={1: 4},
    )
    validity_published = validity.writer.publish(validity.manifest)
    validity_stream = validity_published.manifest.streams[0]
    validity_path = validity_published.path / validity_stream.validity_inventory_relative_path
    payload = bytearray(validity_path.read_bytes())
    payload[-2] = ord("0") if payload[-2] != ord("0") else ord("1")
    validity_path.write_bytes(payload)
    with pytest.raises(BundleCorruptionError, match="validity-inventory digest mismatch"):
        RecordingIqReaderProvider(
            validity.store,
            allow_unpinned_integrity_for_tests=True,
        ).verify_integrity(_identity(validity_published))

    physical = _prepare_v3_bundle(
        tmp_path / "physical",
        "provider-v3-zero-tamper",
        requested_sample_count=12,
        gaps_before_blocks={1: 4},
    )
    physical_published = physical.writer.publish(physical.manifest)
    assert isinstance(physical_published.manifest, RecordingManifestV3)
    stream = physical_published.manifest.streams[0]
    zero_index = next(
        index
        for index, chunk in enumerate(stream.chunks)
        if chunk.content_kind is DeviceAxisContentKind.ZERO_FILL
    )
    zero_chunk = stream.chunks[zero_index]
    zero_path = physical_published.path / zero_chunk.relative_path
    uncompressed = bytearray(_decompress(zero_path))
    uncompressed[0] = 1
    compressed = zstd.ZstdCompressor(level=physical.manifest.compression.level).compress(
        uncompressed
    )
    zero_path.write_bytes(compressed)
    chunks = list(stream.chunks)
    chunks[zero_index] = DeviceAxisRecordingChunkV1.model_validate(
        {
            **zero_chunk.model_dump(mode="json"),
            "compressed_bytes": len(compressed),
            "uncompressed_sha256": sha256_digest(bytes(uncompressed)),
            "compressed_sha256": sha256_digest(compressed),
        }
    )
    logical = hashlib.sha256()
    for chunk in chunks:
        logical.update(_decompress(physical_published.path / chunk.relative_path))
    altered_stream = stream.model_copy(
        update={
            "chunks": tuple(chunks),
            "logical_iq_sha256": f"sha256:{logical.hexdigest()}",
        }
    )
    altered_manifest = physical_published.manifest.model_copy(update={"streams": (altered_stream,)})
    (physical_published.path / "manifest.json").write_bytes(
        canonical_json_bytes(altered_manifest.model_dump(mode="json"))
    )
    altered = physical.store.inspect(physical_published.session_id)
    with pytest.raises(BundleCorruptionError, match="zero-fill chunk contains observed bytes"):
        RecordingIqReaderProvider(
            physical.store,
            allow_unpinned_integrity_for_tests=True,
        ).verify_integrity(_identity(altered))


def _identity(published) -> CaptureRecordingIdentity:
    return CaptureRecordingIdentity(
        session_id=published.session_id,
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
    )


def _execution(published, attestation) -> RunExecutionInfo:
    return RunExecutionInfo(
        run_id=f"run-{published.session_id}",
        session_id=published.session_id,
        pipeline_release_id="1" * 40,
        pipeline_configuration={},
        input_manifest_digest=published.manifest_sha256,
        trigger="reprocess",
        bundle_uri=published.uri,
        raw_integrity_attestation_digest=attestation.attestation_digest,
        raw_integrity_attestation=attestation.model_dump(mode="json"),
    )


def _scope(session_id: str, stream_id: str) -> ScopeIdentityV1:
    return ScopeIdentityV1.receiver_path(
        session_id=session_id,
        stream_id=stream_id,
        receiver_id=0,
    )
