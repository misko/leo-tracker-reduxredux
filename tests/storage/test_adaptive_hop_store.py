from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
import zstandard as zstd
from pydantic import ValidationError

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_hop import (
    AdaptiveHopPlanV2,
    AdaptiveHopPolicyV2,
    AdaptiveHopReceiptV2,
)
from leo.scanner.adaptive_hop_ports import AdaptiveHopVisitBlock
from leo.station.geometry import AdaptiveReceiverGeometryBindingV1, StationReceiverGeometryV1
from leo.storage.adaptive_hop import AdaptiveHopIqManifestV1, AdaptiveHopIqStore
from leo.storage.adaptive_hop_history import AdaptiveHopPresentationStore
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


def test_history_indexes_timestamp_beyond_small_prefix_without_full_decode(tmp_path, monkeypatch):
    store, published = publish(tmp_path, count=0)
    path = session_path(tmp_path) / "manifest.json"
    # Legal JSON whitespace moves the sealed fields beyond the old 512 KiB
    # window, reproducing the offset caused by a full V12 chunk inventory.
    path.write_bytes(b" " * (600 * 1024) + path.read_bytes())
    assert store.inspect(published.session_id) == published

    def no_full_decode(*args, **kwargs):
        raise AssertionError("history indexing must not decode the full receipt")

    monkeypatch.setattr(store, "inspect", no_full_decode)
    assert store.history_index() == ((published.manifest.created_utc_ns, published.session_id),)
    assert store.tracking_metadata_index() == (
        (
            published.manifest.created_utc_ns,
            published.manifest.created_utc_ns,
            published.manifest.receipt.radio_id,
            published.session_id,
        ),
    )
    store.close()


def test_history_index_expansion_remains_bounded(tmp_path):
    store, _ = publish(tmp_path, count=0)
    path = session_path(tmp_path) / "manifest.json"
    path.write_bytes(b" " * (2 * 1024 * 1024) + path.read_bytes())
    with pytest.raises(BundleCorruptionError, match="bounded history index"):
        store.history_index()
    store.close()


def test_adaptive_manifest_seals_dual_receiver_fixture_geometry(tmp_path):
    geometry_path = Path(__file__).parents[2] / (
        "deploy/station/gauss-r21-lt3d-001a-20260920-v1.json"
    )
    geometry = StationReceiverGeometryV1.model_validate_json(geometry_path.read_bytes())
    binding = AdaptiveReceiverGeometryBindingV1.create(
        geometry,
        radio_id="radio_pluto_19f2",
        radio_serial="10400056f695001322002d0010ad1719f2",
    )
    receipt = receipt_fixture(
        count=0,
        radio_id=binding.radio.radio_id,
        radio_serial=binding.radio.radio_serial,
    )
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin(receipt.session_id, receipt.plan, receiver_geometry=binding)
    published = writer.finish(receipt, timing=None)
    assert published.manifest.schema_version == 6
    assert published.manifest.receiver_geometry == binding
    assert published.manifest.receiver_geometry.fixture.fixture_part_id == "LT3D-001A"
    assert tuple(
        item.slot_id for item in published.manifest.receiver_geometry.radio.assignments
    ) == ("negative-x", "positive-x")
    assert store.verify(receipt.session_id) == published
    store.close()


def test_one_edge_manifest_preserves_mask_and_geometry_as_v7(tmp_path):
    geometry_path = Path(__file__).parents[2] / (
        "deploy/station/gauss-r21-lt3d-001a-20260920-v1.json"
    )
    geometry = StationReceiverGeometryV1.model_validate_json(geometry_path.read_bytes())
    binding = AdaptiveReceiverGeometryBindingV1.create(
        geometry,
        radio_id="radio_pluto_19f2",
        radio_serial="10400056f695001322002d0010ad1719f2",
    )
    legacy = receipt_fixture(
        count=0,
        radio_id=binding.radio.radio_id,
        radio_serial=binding.radio.radio_serial,
    )
    plan = AdaptiveHopPlanV2(
        geometry=legacy.plan.geometry,
        policy=AdaptiveHopPolicyV2(mode="adaptive", generation=71, allowed_target_mask=0xF0),
    )
    payload = legacy.model_dump(mode="json")
    payload.update(schema_version=2, plan=plan.model_dump(mode="json"))
    receipt = AdaptiveHopReceiptV2.model_validate(payload)
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin(receipt.session_id, receipt.plan, receiver_geometry=binding)
    published = writer.finish(receipt, timing=None)

    assert published.manifest.schema_version == 7
    assert published.manifest.receipt.plan.policy.allowed_target_mask == 0xF0
    assert store.verify(receipt.session_id) == published
    page = AdaptiveHopPresentationStore(tmp_path).page_v2(cursor=0, limit=20)
    assert page.schema_version == 4
    assert page.items[0].selected_edge == "upper"
    assert page.items[0].allowed_target_mask == 0xF0
    detail = AdaptiveHopPresentationStore(tmp_path).detail_v2(receipt.session_id)
    assert detail is not None and detail.schema_version == 4
    store.close()


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_adaptive_store_lossless_actual_visit_roundtrip(tmp_path, rate, mode):
    store, published = publish(tmp_path, rate=rate, mode=mode, count=30)
    assert store.inspect(published.session_id) == published
    assert store.verify(published.session_id) == published
    assert store.session_ids() == (published.session_id,)
    publication_index = store.publication_index()
    assert publication_index[0][0] > 0
    assert publication_index[0][1] == published.session_id
    tracking_index = store.tracking_metadata_index()
    assert tracking_index == (
        (
            published.manifest.created_utc_ns,
            published.manifest.timing.first_sample_estimate_utc_ns,
            published.manifest.receipt.radio_id,
            published.session_id,
        ),
    )
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
    assert store.publication_index() == ()
    with pytest.raises(BundleNotFoundError):
        store.inspect(receipt.session_id)
    with pytest.raises(BundleStateError, match="read-only"):
        store.begin(receipt.session_id, receipt.plan)
    assert list(tmp_path.iterdir()) == []
    store.close()


def test_history_index_covers_maximum_variable_dwell_chunk_inventory(tmp_path):
    directory = session_path(tmp_path, "scan-fw-variable-dwell-history")
    directory.mkdir(parents=True)
    padding = b"x" * (900 * 1024)
    (directory / "manifest.json").write_bytes(
        b'{"manifest":{"chunks":"'
        + padding
        + b'","created_utc_ns":123,"finalized_utc_ns":456,'
        + b'"timing":{"first_sample_estimate_utc_ns":789}}}'
    )

    store = AdaptiveHopIqStore(tmp_path, read_only=True)
    assert store.history_index() == ((789, "scan-fw-variable-dwell-history"),)
    store.close()


def test_reservation_query_includes_unpublished_evidence_without_creating_paths(tmp_path):
    store = AdaptiveHopIqStore(tmp_path)
    receipt = receipt_fixture(count=0)
    assert not store.contains_session(receipt.session_id)
    assert list(tmp_path.iterdir()) == []
    writer = store.begin(receipt.session_id, receipt.plan)
    assert store.contains_session(receipt.session_id)
    writer.abort()
    assert store.contains_session(receipt.session_id)
    assert not store.contains_session(receipt.session_id + "-other")
    with pytest.raises(ValueError):
        store.contains_session("../outside")
    store.close()


def test_reservation_query_includes_published_sessions(tmp_path):
    store, published = publish(tmp_path, count=0)
    assert store.contains_session(published.session_id)
    reader = AdaptiveHopIqStore(tmp_path, read_only=True)
    assert reader.contains_session(published.session_id)
    reader.close()
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


def test_adaptive_spool_keeps_capture_writes_off_bulk_until_verified_publish(tmp_path, monkeypatch):
    import leo.storage.adaptive_hop as storage

    bulk = tmp_path / "bulk"
    spool = tmp_path / "nvme"
    bulk.mkdir()
    spool.mkdir()
    receipt = receipt_fixture(count=2)
    store = AdaptiveHopIqStore(bulk, spool_root=spool)
    writer = store.begin(receipt.session_id, receipt.plan)
    writer.append(block_fixture(receipt, 0))
    assert not (bulk / "scanner-adaptive-recordings").exists()
    assert tuple((spool / "scanner-adaptive-spool" / receipt.session_id).glob("*.partial"))

    original = storage._copy_regular_verified

    def observe_hidden_copy(*args, **kwargs):
        assert store.session_ids() == ()
        return original(*args, **kwargs)

    monkeypatch.setattr(storage, "_copy_regular_verified", observe_hidden_copy)
    published = writer.finish(receipt, timing=timing_fixture(receipt))
    assert store.verify(receipt.session_id) == published
    assert not (spool / "scanner-adaptive-spool" / receipt.session_id).exists()
    assert not tuple((bulk / "scanner-adaptive-recordings").glob(".transfer-*"))
    store.close()


def test_adaptive_spool_recovers_sealed_session_after_transfer_failure(tmp_path, monkeypatch):
    import leo.storage.adaptive_hop as storage

    bulk = tmp_path / "bulk"
    spool = tmp_path / "nvme"
    bulk.mkdir()
    spool.mkdir()
    receipt = receipt_fixture(count=2)
    store = AdaptiveHopIqStore(bulk, spool_root=spool)
    writer = store.begin(receipt.session_id, receipt.plan)
    writer.append(block_fixture(receipt, 0))

    def fail_copy(*_args, **_kwargs):
        raise OSError("injected RAID failure")

    monkeypatch.setattr(storage, "_copy_regular_verified", fail_copy)
    with pytest.raises(OSError, match="injected RAID failure"):
        writer.finish(receipt, timing=timing_fixture(receipt))
    assert not store.session_ids()
    assert (spool / "scanner-adaptive-spool" / receipt.session_id / "manifest.json").is_file()
    store.close()

    monkeypatch.undo()
    recovered = AdaptiveHopIqStore(bulk, spool_root=spool)
    assert recovered.session_ids() == (receipt.session_id,)
    assert recovered.verify(receipt.session_id).manifest.receipt == receipt
    assert not (spool / "scanner-adaptive-spool" / receipt.session_id).exists()
    recovered.close()


def test_adaptive_spool_can_defer_raid_transfer_for_background_mover(tmp_path):
    bulk = tmp_path / "bulk"
    spool = tmp_path / "nvme"
    bulk.mkdir()
    spool.mkdir()
    receipt = receipt_fixture(count=2)
    capture_store = AdaptiveHopIqStore(bulk, spool_root=spool, defer_spool_transfer=True)
    writer = capture_store.begin(receipt.session_id, receipt.plan)
    writer.append(block_fixture(receipt, 0))
    sealed = writer.finish(receipt, timing=timing_fixture(receipt))
    assert sealed.manifest.receipt == receipt
    assert capture_store.session_ids() == ()
    assert (spool / "scanner-adaptive-spool" / receipt.session_id / "manifest.json").is_file()
    capture_store.close()

    mover = AdaptiveHopIqStore(bulk, spool_root=spool)
    assert mover.verify(receipt.session_id).manifest_sha256 == sealed.manifest_sha256
    assert not (spool / "scanner-adaptive-spool" / receipt.session_id).exists()
    mover.close()


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
