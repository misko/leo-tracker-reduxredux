import numpy as np
import pytest
from pydantic import ValidationError

from leo.scanner.host_adaptive_ports import HostAdaptiveHopVisitBlock
from leo.scanner.single_rx import SingleRxHopTimingV2
from leo.storage.adaptive_hop import (
    AdaptiveHopIqManifestV1,
    AdaptiveHopIqStore,
    HostAdaptiveHopIqManifestV2,
)
from leo.storage.errors import BundleStateError
from tests.scanner.adaptive_hop_fixtures import block_fixture, receipt_fixture, timing_fixture
from tests.scanner.host_adaptive_fixtures import host_receipt


def block(receipt, index):
    values = np.full((1_200_000, 1), (index + 1) - 32768j, np.complex64)
    values[0, 0] = -32768 + 32767j
    return HostAdaptiveHopVisitBlock(
        values, receipt.plan.geometry.receiver_ids, receipt.visits[index]
    )


@pytest.mark.parametrize("receiver", [0, 1])
@pytest.mark.parametrize("queued", [False, True])
def test_native_single_rx_store_full_chunk_tail_and_source_hashes(tmp_path, receiver, queued):
    receipt = host_receipt(receiver=receiver, count=11)
    store = AdaptiveHopIqStore(tmp_path)
    writer = (store.begin_queued if queued else store.begin)(receipt.session_id, receipt.plan)
    try:
        for index in range(receipt.complete_visit_count):
            writer.append(block(receipt, index))
        published = writer.finish(receipt, timing=timing_fixture(receipt, SingleRxHopTimingV2))
        assert isinstance(published.manifest, HostAdaptiveHopIqManifestV2)
        assert published.manifest.uncompressed_bytes == 10 * 1_200_000 * 4
        assert [c.sample_count for c in published.manifest.chunks] == [9_600_000, 2_400_000]
        assert [c.visit_count for c in published.manifest.chunks] == [8, 2]
        assert published.manifest.receipt.host_decisions == receipt.host_decisions
        assert store.inspect(receipt.session_id) == published
        assert store.verify(receipt.session_id) == published
        with store.reader(receipt.session_id, expected=published) as reader:
            for index in (9, 0, 7, 8):
                visit, iq = reader.read_visit_ci16(index)
                assert visit == receipt.visits[index]
                assert iq.shape == (1_200_000, 1, 2)
                assert iq.dtype == np.dtype("<i2")
                np.testing.assert_array_equal(iq[0, 0], [-32768, 32767])
                np.testing.assert_array_equal(iq[1, 0], [index + 1, -32768])
                assert not iq.flags.writeable
        with pytest.raises(ValidationError):
            AdaptiveHopIqManifestV1.model_validate_json(published.manifest.model_dump_json())
    finally:
        writer.abort()
        store.close()


def test_old_and_new_adaptive_manifests_share_discovery_without_relabelling(tmp_path):
    store = AdaptiveHopIqStore(tmp_path)
    legacy = receipt_fixture(count=2, session_id="legacy")
    native = host_receipt(receiver=1, count=2, session_id="native")
    try:
        for receipt, values, clock in (
            (legacy, block_fixture(legacy, 0), timing_fixture(legacy)),
            (native, block(native, 0), timing_fixture(native, SingleRxHopTimingV2)),
        ):
            writer = store.begin(receipt.session_id, receipt.plan)
            try:
                writer.append(values)
                writer.finish(receipt, timing=clock)
            finally:
                writer.abort()
        sessions = list(store.iter_sessions())
        assert [s.manifest.schema_version for s in sessions] == [1, 2]
        assert [s.manifest.receipt.plan.geometry.receiver_ids for s in sessions] == [(0, 1), (1,)]
    finally:
        store.close()


@pytest.mark.parametrize(
    "fault", ["wrong_rx", "fractional_iq", "wrong_timing", "missing_decision", "wrong_bytes"]
)
def test_store_refuses_native_evidence_corruption(tmp_path, fault):
    receipt = host_receipt(count=2)
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin(receipt.session_id, receipt.plan)
    values = block(receipt, 0)
    try:
        if fault == "wrong_rx":
            values = HostAdaptiveHopVisitBlock(values.samples, (1,), values.evidence)
            with pytest.raises(ValueError):
                writer.append(values)
        elif fault == "fractional_iq":
            changed = values.samples.copy()
            changed[0, 0] = 0.5j
            with pytest.raises(ValueError):
                writer.append(HostAdaptiveHopVisitBlock(changed, (0,), values.evidence))
        else:
            writer.append(values)
            timing = timing_fixture(receipt, SingleRxHopTimingV2)
            if fault == "wrong_timing":
                timing = timing.model_copy(update={"sample_rate_hz": 2_500_000})
            if fault == "missing_decision":
                receipt = receipt.model_copy(update={"host_decisions": ()})
            if fault == "wrong_bytes":
                manifest = writer.finish(receipt, timing=timing).manifest.model_dump()
                manifest["uncompressed_bytes"] *= 2
                with pytest.raises(ValidationError):
                    HostAdaptiveHopIqManifestV2.model_validate(manifest)
            else:
                with pytest.raises(ValidationError):
                    writer.finish(receipt, timing=timing)
        if fault != "wrong_bytes":
            with pytest.raises(BundleStateError):
                writer.append(values)
    finally:
        writer.abort()
        store.close()
