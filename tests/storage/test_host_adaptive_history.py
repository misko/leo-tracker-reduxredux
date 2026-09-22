import pytest
from pydantic import ValidationError

from leo.scanner.adaptive_hop_history import AdaptiveHopHistoryPageV1
from leo.scanner.host_adaptive_history import AdaptiveHistoryPageV2, HostAdaptiveSessionDetailV2
from leo.scanner.single_rx import SingleRxHopTimingV2, SingleRxHopTimingV3
from leo.storage.adaptive_hop import AdaptiveHopIqReader, AdaptiveHopIqStore
from leo.storage.adaptive_hop_history import AdaptiveHopPresentationStore
from tests.scanner.adaptive_hop_fixtures import timing_fixture
from tests.scanner.host_adaptive_fixtures import host_receipt, sparse_multirate_host_receipt
from tests.storage.test_adaptive_hop_history import publish_capture
from tests.storage.test_host_adaptive_hop_store import block


def publish_native(root, *, receiver=0, timing_shift_ns=0):
    receipt = host_receipt(receiver=receiver, count=4, session_id="host-native-history")
    store = AdaptiveHopIqStore(root)
    writer = store.begin(receipt.session_id, receipt.plan)
    try:
        for i in range(receipt.complete_visit_count):
            writer.append(block(receipt, i))
        timing = timing_fixture(receipt, SingleRxHopTimingV2)
        if timing_shift_ns:
            timing = timing.model_copy(
                update={
                    "begin_before_realtime_ns": timing.begin_before_realtime_ns + timing_shift_ns,
                    "begin_after_realtime_ns": timing.begin_after_realtime_ns + timing_shift_ns,
                    "terminal_realtime_ns": timing.terminal_realtime_ns + timing_shift_ns,
                    "first_sample_earliest_utc_ns": timing.first_sample_earliest_utc_ns
                    + timing_shift_ns,
                    "first_sample_estimate_utc_ns": timing.first_sample_estimate_utc_ns
                    + timing_shift_ns,
                    "first_sample_latest_utc_ns": timing.first_sample_latest_utc_ns
                    + timing_shift_ns,
                }
            )
        return writer.finish(receipt, timing=timing)
    finally:
        writer.abort()
        store.close()


@pytest.mark.parametrize("receiver", [0, 1])
def test_mixed_history_preserves_legacy_major_and_exposes_host_evidence(
    tmp_path, monkeypatch, receiver
):
    legacy = publish_capture(tmp_path, count=3)
    native = publish_native(tmp_path, receiver=receiver)
    monkeypatch.setattr(
        AdaptiveHopIqReader, "read_visit_ci16", lambda *a: pytest.fail("history read IQ")
    )
    reader = AdaptiveHopPresentationStore(tmp_path)
    page = reader.page_v2(cursor=0, limit=20)
    assert isinstance(page, AdaptiveHistoryPageV2) and page.total == 2
    assert {c.schema_version for c in page.items} == {1, 2}
    assert AdaptiveHistoryPageV2.model_validate_json(page.model_dump_json()) == page
    assert [c.session_id for c in reader.page(cursor=0, limit=20).items] == [legacy.session_id]
    assert reader.detail(native.session_id) is None
    assert reader.glrt(native.session_id) is None
    detail = reader.detail_v2(native.session_id)
    assert isinstance(detail, HostAdaptiveSessionDetailV2)
    assert detail.capture.physical_receiver == receiver
    assert detail.capture.sample_rate_hz == 10_000_000
    assert detail.capture.decision_configuration.decision_rate_hz == 2_500_000
    assert detail.capture.host_feedback.healthy == 3
    assert detail.capture.host_feedback.accepted == 3
    assert len(detail.host_decisions) == 3
    assert detail.host_decisions[0].feedback_call_ms == 0.002
    assert detail.host_decisions[0].numerics.screen_mask == 63
    assert isinstance(detail.model_dump(mode="json")["visits"][0]["valid_start_counter"], str)
    with pytest.raises(ValidationError):
        AdaptiveHopHistoryPageV1.model_validate_json(page.model_dump_json())
    payload = detail.model_dump()
    payload["host_decisions"] = payload["host_decisions"][:-1]
    with pytest.raises(ValidationError):
        HostAdaptiveSessionDetailV2.model_validate(payload)


def test_combined_history_indexes_before_parsing_only_the_requested_page(tmp_path, monkeypatch):
    older = publish_capture(tmp_path, count=3, session_id="older-legacy")
    newer = publish_native(tmp_path, timing_shift_ns=1_000_000_000)
    inspected: list[str] = []
    original_inspect = AdaptiveHopIqStore.inspect

    def inspect(store, session_id):
        inspected.append(session_id)
        return original_inspect(store, session_id)

    monkeypatch.setattr(AdaptiveHopIqStore, "inspect", inspect)
    monkeypatch.setattr(
        AdaptiveHopIqStore,
        "iter_sessions",
        lambda *_args, **_kwargs: pytest.fail("combined history must use the bounded index"),
    )

    page = AdaptiveHopPresentationStore(tmp_path).page_v2(cursor=0, limit=1)

    assert page.total == 2
    assert page.items[0].session_id == newer.session_id
    assert inspected == [newer.session_id]
    assert older.session_id not in inspected


def test_sparse_wide_history_exposes_original_source_visit_indices(tmp_path):
    receipt = sparse_multirate_host_receipt(session_id="host-wide-sparse-history")
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin(receipt.session_id, receipt.plan)
    try:
        for ordinal in range(receipt.complete_visit_count):
            writer.append(block(receipt, ordinal))
        writer.finish(receipt, timing=timing_fixture(receipt, SingleRxHopTimingV3))
    finally:
        writer.abort()
        store.close()
    reader = AdaptiveHopPresentationStore(tmp_path)
    detail = reader.detail_v2(receipt.session_id)
    assert detail is not None
    assert detail.capture.sample_rate_hz == 20_000_000
    assert detail.capture.retained_visits == 5
    assert [decision.visit_index for decision in detail.host_decisions] == [0, 1, 3, 4, 5]
    assert [visit.visit_index for visit in detail.visits if visit.retained] == [0, 1, 3, 4, 5]
