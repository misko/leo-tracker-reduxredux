import pytest
from pydantic import ValidationError

from leo.scanner.adaptive_hop_history import AdaptiveHopHistoryPageV1
from leo.scanner.host_adaptive_history import AdaptiveHistoryPageV2, HostAdaptiveSessionDetailV2
from leo.scanner.single_rx import SingleRxHopTimingV2
from leo.storage.adaptive_hop import AdaptiveHopIqReader, AdaptiveHopIqStore
from leo.storage.adaptive_hop_history import AdaptiveHopPresentationStore
from tests.scanner.adaptive_hop_fixtures import timing_fixture
from tests.scanner.host_adaptive_fixtures import host_receipt
from tests.storage.test_adaptive_hop_history import publish_capture
from tests.storage.test_host_adaptive_hop_store import block


def publish_native(root, *, receiver=0):
    receipt = host_receipt(receiver=receiver, count=4, session_id="host-native-history")
    store = AdaptiveHopIqStore(root)
    writer = store.begin(receipt.session_id, receipt.plan)
    try:
        for i in range(receipt.complete_visit_count):
            writer.append(block(receipt, i))
        return writer.finish(receipt, timing=timing_fixture(receipt, SingleRxHopTimingV2))
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
