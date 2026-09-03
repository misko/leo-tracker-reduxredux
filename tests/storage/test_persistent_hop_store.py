from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import compile_persistent_hop_plan_v1
from leo.scanner.persistent_hop_ports import PersistentHopVisitBlock
from leo.storage import PersistentHopIqStore, persisted_persistent_hop_analysis_source
from leo.storage.errors import BundleCorruptionError, BundleStateError


def _cancelled_capture(tmp_path, *, visit_count: int = 9):
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000, kernel_buffers=8)
    radio = FakePersistentHopRadio(transition_invalid_ms=12)
    radio.open()
    session = radio.begin_session(plan, session_id="hop-storage-test")
    store = PersistentHopIqStore(tmp_path)
    writer = store.begin_queued("hop-storage-test", plan, capacity_visits=2)
    blocks = []
    for _ in range(visit_count):
        block = session.read_visit()
        blocks.append(block)
        writer.append(block)
    session.request_cancel()
    receipt = session.finish()
    published = writer.finish(receipt)
    radio.close()
    return store, published, blocks


def test_persistent_hop_store_streams_sweep_chunks_and_reopens(tmp_path) -> None:
    store, published, blocks = _cancelled_capture(tmp_path)

    assert published.manifest.receipt.capture_outcome == "cancelled"
    assert published.manifest.total_sample_count == 9 * 300_000
    assert [(chunk.sweep_index, chunk.visit_count) for chunk in published.manifest.chunks] == [
        (0, 8),
        (1, 1),
    ]
    assert published.manifest.queue_telemetry is not None
    assert published.manifest.queue_telemetry.capacity_visits == 2
    assert sorted(item.name for item in published.path.iterdir()) == [
        "iq-sweep-000000.ci16.zst",
        "iq-sweep-000001.ci16.zst",
        "manifest.json",
    ]

    reopened = store.inspect("hop-storage-test")
    assert reopened.manifest == published.manifest
    visits, values = store.read_sweep_ci16(reopened, 0)
    assert len(visits) == 8
    assert values.shape == (8 * 300_000, 2, 2)
    assert values.dtype == np.dtype("<i2")
    assert values[0].tolist() == [[1, 1], [1, 2]]
    assert values[300_000].tolist() == [[2, 1], [2, 2]]
    assert not values.flags.writeable
    assert visits == tuple(block.evidence for block in blocks[:8])

    reader = store.valid_ci16_reader(reopened)
    assert reader.sample_count == 9 * 300_000
    assert reader.receiver_ids == (0, 1)
    crossing = reader.read_valid_ci16(8 * 300_000 - 2, 4)
    assert crossing.shape == (4, 2, 2)
    assert crossing.tolist() == [
        [[8, 1], [8, 2]],
        [[8, 1], [8, 2]],
        [[1, 1], [1, 2]],
        [[1, 1], [1, 2]],
    ]
    assert not crossing.flags.writeable

    with pytest.raises(ValueError, match="exceeds"):
        reader.read_valid_ci16(reader.sample_count - 1, 2)

    source = persisted_persistent_hop_analysis_source(store, reopened)
    visit = source.read_visit(8)
    assert visit.span.evidence == blocks[8].evidence
    assert visit.samples_ci16.shape == (300_000, 2, 2)
    assert visit.samples_ci16[0].tolist() == [[1, 1], [1, 2]]


def test_persistent_hop_store_publishes_attested_zero_visit_cancellation(tmp_path) -> None:
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000, kernel_buffers=2)
    radio = FakePersistentHopRadio()
    radio.open()
    session = radio.begin_session(plan, session_id="hop-zero-visit")
    writer = PersistentHopIqStore(tmp_path).begin("hop-zero-visit", plan)

    session.request_cancel()
    receipt = session.finish()
    published = writer.finish(receipt)
    radio.close()

    assert published.manifest.chunks == ()
    assert published.manifest.total_sample_count == 0
    assert published.manifest.uncompressed_bytes == 0
    with pytest.raises(KeyError, match="sweep does not exist"):
        PersistentHopIqStore(tmp_path).read_sweep_ci16(published, 0)


def test_persistent_hop_store_rejects_tampered_sweep(tmp_path) -> None:
    store, published, _blocks = _cancelled_capture(tmp_path, visit_count=1)
    chunk = published.manifest.chunks[0]
    path = published.path / chunk.relative_path
    payload = bytearray(path.read_bytes())
    payload[len(payload) // 2] ^= 1
    path.write_bytes(payload)

    with pytest.raises(BundleCorruptionError, match="compressed digest mismatch"):
        store.read_sweep_ci16(published, 0)


def test_queued_persistent_hop_writer_surfaces_conversion_failure(tmp_path) -> None:
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000, kernel_buffers=2)
    radio = FakePersistentHopRadio()
    radio.open()
    session = radio.begin_session(plan, session_id="hop-writer-failure")
    block = session.read_visit()
    invalid = block.samples.copy()
    invalid[0, 0] = np.complex64(0.5 + 1j)
    writer = PersistentHopIqStore(tmp_path).begin_queued(
        "hop-writer-failure", plan, capacity_visits=1
    )
    writer.append(
        PersistentHopVisitBlock(
            samples=invalid,
            receiver_ids=block.receiver_ids,
            evidence=block.evidence,
        )
    )
    session.request_cancel()
    receipt = session.finish()

    with pytest.raises(BundleStateError, match="storage worker failed"):
        writer.finish(receipt)
    radio.close()


def test_persistent_hop_store_rejects_receipt_that_does_not_match_iq(tmp_path) -> None:
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000, kernel_buffers=2)
    radio = FakePersistentHopRadio()
    radio.open()
    session = radio.begin_session(plan, session_id="hop-receipt-mismatch")
    block = session.read_visit()
    writer = PersistentHopIqStore(tmp_path).begin("hop-receipt-mismatch", plan)
    writer.append(block)
    session.request_cancel()
    receipt = session.finish()

    with pytest.raises(ValueError, match="receipt disagrees"):
        writer.finish(receipt.model_copy(update={"visits": ()}))
    writer.abort()
    radio.close()


def test_persistent_hop_store_refuses_qnap() -> None:
    with pytest.raises(ValueError, match="QNAP"):
        PersistentHopIqStore(Path("/mnt/qnap01/hop-test"))
