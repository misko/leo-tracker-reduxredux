from collections import Counter

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.fast_scan import FastSegmentSource
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3.first_third_ingress import (
    admitted_prefix, chunk_rows, drained_windows, verified_payload, verified_stream,
)
from reports.ALGO08.v3.first_third_trial import native_first_third


BAD_DIGEST = "sha256:" + "0" * 64


@pytest.fixture
def segment(tmp_path):
    target = dict(target_id="rx", edge="lower", channel=1, rf_center_hz=10_700_000_000,
                  lnb_lo_hz=9_750_000_000)
    writer = ShortWindowWriter(tmp_path, "test-sealed", configuration={
        "window_ms": 20, "sample_rate_hz": 10_000_000, "targets": [target],
    }, radio={"serial": "TEST"}, receiver_ids=(0, 1), chunk_windows=3, schema_version=2)
    samples = np.zeros((200_000, 2, 2), dtype="<i2")
    for i in range(6):
        samples[0, 0, 0] = i
        acq = dict(global_visit=i, complete=i > 0, validity_authority="provider_attested",
                   validity_includes_guard=True, quality_flags=[], actual_if_center_hz=950_000_000,
                   sample_start=i*200_000, sample_end=(i+1)*200_000, generation=1)
        writer.append(sequence=i, target_id="rx", samples=samples, acquisition=acq, powers=({}, {}))
    root = writer.finish(stop_reason="test")
    return dict(path=str(root), manifest_digest=ShortWindowReader(root).manifest_sha256)


@pytest.mark.parametrize("streamed", [False, True])
def test_admitted_cut_ignores_invalid_slot_and_drained_metadata_stays_identical(segment, streamed):
    plan = admitted_prefix([segment], [6])
    assert (plan.count, plan.admitted, plan.keep, plan.cutoff) == (6, 5, 1, 2)
    source = FastSegmentSource(segment)
    original = list(source.windows())
    stats = Counter()
    rows = list(drained_windows(source, plan, None, stats, streamed=streamed))
    assert stats["bulk_members"] == 2
    assert stats["bulk_array_rows"] == 2
    assert stats["metadata_only_rows"] == 4
    for before, after in zip(original, rows, strict=True):
        assert (before.sequence, before.iq_sha256, before.acquisition, before.target, before.samples.shape) == (
            after.sequence, after.iq_sha256, after.acquisition, after.target, after.samples.shape)
        if before.sequence < plan.cutoff:
            np.testing.assert_array_equal(before.samples, after.samples)
        else:
            assert not isinstance(after.samples, np.ndarray)


@pytest.mark.parametrize("attribute", ["compressed_sha256", "uncompressed_sha256", "window_sha256"])
@pytest.mark.parametrize("streamed", [False, True])
def test_drain_rejects_each_tampered_integrity_layer(segment, attribute, streamed):
    source = FastSegmentSource(segment)
    chunk, *_ = source.reader.manifest.chunks
    rows = chunk_rows(source, chunk)
    if attribute == "window_sha256":
        rows = (rows[0].model_copy(update={"iq_sha256": BAD_DIGEST}), *rows[1:])
    else:
        chunk = chunk.model_copy(update={attribute: BAD_DIGEST})
    with pytest.raises(BundleCorruptionError, match="changed"):
        if streamed:
            list(verified_stream(source.reader, chunk, rows, None, 0, Counter()))
        else:
            verified_payload(source.reader, chunk, rows, None, Counter())


def test_bad_manifest_and_trailing_valid_zstd_payload_fail(segment):
    with pytest.raises(ValueError, match="manifest changed"):
        admitted_prefix([dict(segment, manifest_digest=BAD_DIGEST)], [6])
    source = FastSegmentSource(segment)
    chunk, *_ = source.reader.manifest.chunks
    with pytest.raises(BundleCorruptionError, match="member changed"):
        chunk_rows(source, chunk.model_copy(update={"index_sha256": BAD_DIGEST}))
    rows = chunk_rows(source, chunk)
    path = source.reader.path / chunk.payload_relative_path
    compressed = path.read_bytes() + zstd.ZstdCompressor().compress(b"extra")
    path.write_bytes(compressed)
    chunk = chunk.model_copy(update={"compressed_sha256": sha256_digest(compressed),
                                     "compressed_bytes": len(compressed)})
    with pytest.raises(BundleCorruptionError, match="trailing IQ bytes"):
        verified_payload(source.reader, chunk, rows, None, Counter())


def test_native_projection_keeps_admitted_count_without_rebasing_hardware_visit():
    probes = [dict(visit_index=i, receiver_id=lane, candidates=[])
              for i in (1, 2, 3, 4, 5, 7) for lane in (0, 1)]
    result = native_first_third(dict(source={"probes": probes}, provenance={
        "window_count": 8, "processed_windows": 6, "invalid_capture": 2,
    }))
    assert (result["keep"], result["cutoff"], result["invalid"]) == (2, 3, 2)
