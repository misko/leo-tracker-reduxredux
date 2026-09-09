from __future__ import annotations

import json
import os

import numpy as np
import pytest
import zstandard as zstd
from pydantic import ValidationError

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_hop_ports import AdaptiveHopVisitBlock
from leo.storage.adaptive_hop import AdaptiveHopIqManifestV1, AdaptiveHopIqStore
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError, BundleStateError
from leo.storage.persistent_hop import (
    PersistentHopIqSessionManifestV1,
    PersistentHopIqSessionManifestV2,
)
from tests.scanner.adaptive_hop_fixtures import block_fixture, receipt_fixture, timing_fixture


def publish(tmp_path, *, rate=2_500_000, mode="adaptive", count=10):
    receipt = receipt_fixture(rate=rate, mode=mode, count=count)
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin(receipt.session_id, receipt.plan)
    assert store.session_ids() == ()
    for index in range(receipt.complete_visit_count):
        writer.append(block_fixture(receipt, index))
    published = writer.finish(receipt, timing=timing_fixture(receipt) if count else None)
    return store, published


def session_path(tmp_path, session_id="adaptive-storage-test"):
    return tmp_path / "scanner-adaptive-recordings" / session_id


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_adaptive_store_lossless_actual_visit_roundtrip(tmp_path, rate, mode):
    store, published = publish(tmp_path, rate=rate, mode=mode, count=30)
    assert store.inspect(published.session_id) == published
    assert store.verify(published.session_id) == published
    assert store.session_ids() == (published.session_id,)
    assert [c.visit_count for c in published.manifest.chunks] == [8, 8, 8, 5]
    event, samples = store.read_visit_ci16(published, 25)
    assert event.event.target_index == (2 if mode == "adaptive" else 1)
    assert samples.shape == (rate * 120 // 1000, 2, 2)
    assert samples[0].tolist() == [[26, 2], [event.event.target_index + 10, -3]]
    assert np.all(samples == samples[0])
    assert not samples.flags.writeable
    assert event.event.valid_start_counter > 2**53
    assert published.manifest.receipt.complete_visit_count == 29
    assert published.manifest.receipt.unclassified_sample_count == 101
    assert not any("sweep" in p.name for p in session_path(tmp_path).iterdir())
    for old in (PersistentHopIqSessionManifestV1, PersistentHopIqSessionManifestV2):
        with pytest.raises(ValidationError):
            old.model_validate_json(published.manifest.model_dump_json())
    store.close()


def test_adaptive_read_only_and_missing_records_create_nothing(tmp_path):
    receipt = receipt_fixture(count=0)
    store = AdaptiveHopIqStore(tmp_path, read_only=True)
    assert store.session_ids() == ()
    with pytest.raises(BundleNotFoundError):
        store.inspect(receipt.session_id)
    with pytest.raises(BundleStateError, match="read-only"):
        store.begin(receipt.session_id, receipt.plan)
    assert list(tmp_path.iterdir()) == []
    store.close()


def test_adaptive_empty_cancel_and_duplicate_session_are_safe(tmp_path):
    store, published = publish(tmp_path, count=0)
    assert published.manifest.chunks == ()
    assert published.manifest.timing is None
    assert store.verify(published.session_id) == published
    with pytest.raises(FileExistsError):
        store.begin(published.session_id, published.manifest.receipt.plan)
    with pytest.raises(ValueError):
        store.read_visit_ci16(published, 0)
    store.close()


@pytest.mark.parametrize("field", ["total_sample_count", "compressed_bytes", "session_id"])
def test_adaptive_manifest_tamper_rejected_including_history(tmp_path, field):
    store, published = publish(tmp_path, count=2)
    path = session_path(tmp_path) / "manifest.json"
    payload = json.loads(path.read_bytes())
    payload["manifest"][field] = "wrong-id" if field == "session_id" else 1
    path.write_text(json.dumps(payload))
    with pytest.raises(BundleCorruptionError):
        store.inspect(published.session_id)
    with pytest.raises(BundleCorruptionError):
        store.session_ids()
    store.close()


@pytest.mark.parametrize("fault", ["tamper", "truncate", "symlink", "hardlink", "fifo"])
def test_adaptive_chunk_corruption_fails_closed(tmp_path, fault):
    store, published = publish(tmp_path, count=2)
    path = session_path(tmp_path) / published.manifest.chunks[0].relative_path
    raw = path.read_bytes()
    if fault == "tamper":
        path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    elif fault == "truncate":
        path.write_bytes(raw[:-2])
    elif fault == "symlink":
        saved = path.with_suffix(".saved")
        path.rename(saved)
        path.symlink_to(saved)
    elif fault == "hardlink":
        os.link(path, path.with_suffix(".alias"))
    else:
        path.unlink()
        os.mkfifo(path)
    with pytest.raises(BundleCorruptionError):
        store.verify(published.session_id)
    store.close()


@pytest.mark.parametrize("fault", ["extra_frame", "wrong_raw_hash", "large_output"])
def test_adaptive_rejects_malicious_compressed_payload_even_with_new_compressed_hash(
    tmp_path, fault
):
    store, published = publish(tmp_path, count=2)
    path = session_path(tmp_path) / published.manifest.chunks[0].relative_path
    payload = path.read_bytes()
    if fault == "extra_frame":
        payload += zstd.ZstdCompressor().compress(b"unexpected trailing frame")
    elif fault == "large_output":
        # Match checksum and size in manifest, but never allow expansion past
        # its attested exact CI16 capacity (writer emits content-size-less frames).
        payload = zstd.ZstdCompressor(write_content_size=False).compress(bytes(2_400_008))
    path.write_bytes(payload)
    manifest = published.manifest.model_dump(mode="json")
    chunk = manifest["chunks"][0]
    chunk["compressed_bytes"] = manifest["compressed_bytes"] = len(payload)
    chunk["compressed_sha256"] = sha256_digest(payload)
    if fault == "wrong_raw_hash":
        chunk["uncompressed_sha256"] = sha256_digest(b"wrong")
    model = AdaptiveHopIqManifestV1.model_validate(manifest)
    seal = dict(
        manifest=model.model_dump(mode="json"),
        sha256=sha256_digest(canonical_json_bytes(model.model_dump(mode="json"))),
    )
    (session_path(tmp_path) / "manifest.json").write_bytes(canonical_json_bytes(seal))
    with pytest.raises(BundleCorruptionError):
        store.verify(published.session_id)
    store.close()


def test_adaptive_failure_preserves_unpublished_iq_and_never_retries_in_place(tmp_path):
    receipt = receipt_fixture(count=2)
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin(receipt.session_id, receipt.plan)
    writer.append(block_fixture(receipt, 0))
    with pytest.raises(ValueError):
        writer.finish(receipt, timing=None)
    writer.abort()
    assert store.session_ids() == ()
    assert list(session_path(tmp_path).glob("*.zst"))
    with pytest.raises(FileExistsError):
        store.begin(receipt.session_id, receipt.plan)
    store.close()


@pytest.mark.parametrize("fault", ["noninteger", "overflow", "source_order"])
def test_adaptive_failed_append_poisoned_writer_cannot_publish(tmp_path, fault):
    receipt = receipt_fixture(count=3)
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin(receipt.session_id, receipt.plan)
    block = block_fixture(receipt, 1 if fault == "source_order" else 0)
    if fault != "source_order":
        values = block.samples.copy()
        values[0, 0] = 0.5 if fault == "noninteger" else 32768
        block = AdaptiveHopVisitBlock(values, (0, 1), block.evidence)
    with pytest.raises(ValueError):
        writer.append(block)
    with pytest.raises(BundleStateError):
        writer.finish(receipt, timing=timing_fixture(receipt))
    writer.abort()
    assert store.session_ids() == ()
    store.close()


def test_adaptive_manifest_publication_is_atomic_no_replace(tmp_path):
    receipt = receipt_fixture(count=0)
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin(receipt.session_id, receipt.plan)
    path = session_path(tmp_path) / "manifest.json"
    path.write_bytes(b"independent evidence must survive")
    with pytest.raises(FileExistsError):
        writer.finish(receipt, timing=None)
    writer.abort()
    assert path.read_bytes() == b"independent evidence must survive"
    store.close()


def test_adaptive_pinned_root_survives_path_replacement(tmp_path):
    root = tmp_path / "local"
    root.mkdir()
    store = AdaptiveHopIqStore(root)
    retained = tmp_path / "retained"
    root.rename(retained)
    root.symlink_to(tmp_path / "outside")
    receipt = receipt_fixture(count=0)
    writer = store.begin(receipt.session_id, receipt.plan)
    published = writer.finish(receipt, timing=None)
    assert store.verify(receipt.session_id) == published
    assert not (tmp_path / "outside").exists()
    assert (
        retained / "scanner-adaptive-recordings" / receipt.session_id / "manifest.json"
    ).is_file()
    store.close()


def test_adaptive_qnap_and_symlink_roots_refused_without_writes(tmp_path):
    from pathlib import Path

    with pytest.raises(ValueError):
        AdaptiveHopIqStore(Path("/mnt/qnap01/must-not-create-adaptive"))
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        AdaptiveHopIqStore(alias)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["alias"]


def test_adaptive_reader_validates_manifest_once_and_caches_only_one_chunk(tmp_path, monkeypatch):
    import leo.storage.adaptive_hop as storage

    store, published = publish(tmp_path, count=18)
    reads = []
    original = storage._read_regular

    def counted(directory, name, maximum):
        reads.append(name)
        return original(directory, name, maximum)

    monkeypatch.setattr(storage, "_read_regular", counted)
    with store.reader(published.session_id) as reader:
        for index in (0, 1, 7, 8, 9, 16):
            visit, values = reader.read_visit_ci16(index)
            assert visit.event.visit_index == index
            assert values[0, 0, 0] == index + 1
        assert reads == [
            "manifest.json",
            "iq-block-000000.ci16.zst",
            "iq-block-000001.ci16.zst",
            "iq-block-000002.ci16.zst",
        ]
        assert reader._cached_index == 2
        reader.read_visit_ci16(0)
        assert reads[-1] == "iq-block-000000.ci16.zst"
    with pytest.raises(RuntimeError, match="closed"):
        reader.read_visit_ci16(0)
    store.close()
