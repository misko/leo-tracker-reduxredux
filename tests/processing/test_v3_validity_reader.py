from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import zstandard as zstd

from leo.catalog import CaptureRecordingIdentity, RunExecutionInfo
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.recording import DeviceAxisRecordingChunkV1, RecordingManifestV3
from leo.contracts.validity import DeviceAxisContentKind
from leo.pipeline import ScopeIdentityV1, WindowValidity
from leo.processing import RecordingIqReaderProvider
from leo.storage import BundleCorruptionError
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
