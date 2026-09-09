from __future__ import annotations

import pytest

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_history import (
    AdaptiveHopGlrtPresentationStore,
    AdaptiveHopPresentationStore,
)
from leo.storage.errors import BundleCorruptionError
from leo.storage.scanner_glrt import ScannerGlrtStore
from tests.scanner.adaptive_glrt_publication_fixtures import publication_fixture
from tests.scanner.adaptive_hop_fixtures import block_fixture, receipt_fixture, timing_fixture


def publish_capture(root, **kwargs):
    receipt = receipt_fixture(**kwargs)
    return publish_receipt(root, receipt)


def publish_receipt(root, receipt):
    store = AdaptiveHopIqStore(root)
    try:
        writer = store.begin(receipt.session_id, receipt.plan)
        for index in range(receipt.complete_visit_count):
            writer.append(block_fixture(receipt, index))
        return writer.finish(receipt, timing=timing_fixture(receipt) if receipt.events else None)
    finally:
        store.close()


def test_cancellation_during_guard_does_not_claim_future_valid_iq(tmp_path):
    from leo.scanner.adaptive_hop import AdaptiveHopReceiptV1

    receipt = receipt_fixture(count=1)
    payload = receipt.model_dump()
    final = receipt.events[0].transition_after_counter
    payload["terminal"].update(
        final_counter=final,
        last_block_end_counter=final,
        restore_before_counter=final,
        restore_after_counter=final + 10,
    )
    payload.update(
        duty_denominator_sample_count=final - receipt.terminal.first_counter,
        transition_invalid_sample_count=final - receipt.terminal.first_counter,
        unclassified_sample_count=0,
    )
    receipt = AdaptiveHopReceiptV1.model_validate(payload)
    capture = publish_receipt(tmp_path, receipt)
    detail = AdaptiveHopPresentationStore(tmp_path).detail(capture.session_id)
    assert detail.capture.source_span_seconds < detail.visits[0].valid_start_seconds
    assert detail.visits[0].invalid_start_seconds == 0
    assert detail.visits[0].valid_end_seconds is None
    assert detail.capture.retained_visits == 0
    assert all(
        c.maximum_unobserved_seconds == detail.capture.source_span_seconds
        for c in detail.capture.target_coverage
    )


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_history_preserves_actual_visits_integer_origin_and_cancelled_tail(
    tmp_path, rate, mode, monkeypatch
):
    capture = publish_capture(tmp_path, rate=rate, mode=mode, count=30)

    def forbidden(*args, **kwargs):
        raise AssertionError("history must never decode IQ")

    monkeypatch.setattr(AdaptiveHopIqStore, "reader", forbidden)
    presentation = AdaptiveHopPresentationStore(tmp_path)
    page = presentation.page(cursor=0, limit=5)
    detail = presentation.detail(capture.session_id)
    assert detail is not None and page.items == (detail.capture,)
    receipt = capture.manifest.receipt
    assert detail.source_origin_counter == 2**53 + 17
    assert detail.capture.started_visits == 30 and detail.capture.retained_visits == 29
    assert not detail.capture.capture_qualified
    assert detail.capture.analysis_state == "not_integrated"
    assert detail.capture.mode == mode
    row = detail.visits[25]
    assert row.target_index == (2 if mode == "adaptive" else 1)
    assert row.proposed_target_index == (2 if mode == "adaptive" else 4)
    assert (
        row.valid_start_seconds == (row.valid_start_counter - detail.source_origin_counter) / rate
    )
    assert row.valid_end_counter - row.valid_start_counter == rate * 120 // 1000
    assert not detail.visits[-1].retained
    assert detail.visits[-1].valid_end_seconds is None
    assert detail.visits[-1].valid_end_counter is None
    assert detail.capture.valid_duty_ppm == receipt.valid_duty_ppm
    serialized = detail.model_dump(mode="json")
    assert serialized["source_origin_counter"] == str(2**53 + 17)
    assert serialized["visits"][25]["valid_start_counter"] == str(row.valid_start_counter)
    assert serialized["capture"]["policy_generation"] == "71"
    for coverage in detail.capture.target_coverage:
        visits = [v for v in receipt.visits if v.event.target_index == coverage.target_index]
        assert coverage.retained_visits == len(visits)
        assert coverage.valid_seconds == pytest.approx(len(visits) * 0.12)
        assert coverage.allocation_ppm == len(visits) * 1_000_000 // 29
        gaps = [visits[0].event.valid_start_counter - receipt.terminal.first_counter]
        gaps += [
            b.event.valid_start_counter - a.valid_end_counter_exclusive
            for a, b in zip(visits, visits[1:], strict=False)
        ]
        gaps += [receipt.terminal.final_counter - visits[-1].valid_end_counter_exclusive]
        assert coverage.maximum_unobserved_seconds == max(gaps) / rate
        assert (
            coverage.maximum_revisit_seconds
            == max(
                b.event.valid_start_counter - a.event.valid_start_counter
                for a, b in zip(visits, visits[1:], strict=False)
            )
            / rate
        )


def test_empty_and_unsampled_targets_do_not_invent_duty_time_or_revisits(tmp_path):
    capture = publish_capture(tmp_path, count=0)
    presentation = AdaptiveHopPresentationStore(tmp_path)
    detail = presentation.detail(capture.session_id)
    assert detail.visits == () and detail.source_origin_counter is None
    assert detail.capture.captured_at is None
    assert detail.capture.source_span_seconds is None and detail.capture.valid_duty_ppm is None
    assert all(
        c.allocation_ppm is None and c.maximum_unobserved_seconds is None
        for c in detail.capture.target_coverage
    )
    assert not detail.capture.utc_qualified
    other = publish_capture(tmp_path, count=2, session_id="one-retained")
    detail = presentation.detail(other.session_id)
    assert all(c.maximum_revisit_seconds is None for c in detail.capture.target_coverage)
    assert (
        detail.capture.target_coverage[1].maximum_unobserved_seconds
        == detail.capture.source_span_seconds
    )


def test_read_only_pagination_is_publication_order_and_ignores_unpublished(tmp_path):
    presentation = AdaptiveHopPresentationStore(tmp_path)
    assert presentation.page(cursor=0, limit=1).total == 0
    assert presentation.detail("missing") is None
    assert list(tmp_path.iterdir()) == []
    first = publish_capture(tmp_path, count=0, session_id="z-first")
    second = publish_capture(tmp_path, count=0, session_id="a-second")
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin("unpublished", first.manifest.receipt.plan)
    writer.abort()
    store.close()
    page = presentation.page(cursor=0, limit=1)
    assert page.total == 2 and page.next_cursor == 1
    assert page.items[0].session_id == second.session_id
    assert presentation.page(cursor=1, limit=1).items[0].session_id == first.session_id
    assert presentation.page(cursor=99, limit=1).items == ()
    assert presentation.detail("unpublished") is None


@pytest.mark.parametrize("cursor,limit", [(-1, 1), (True, 1), (0, 0), (0, 21), (0, True)])
def test_invalid_pagination_is_rejected_before_opening_root(cursor, limit):
    with pytest.raises(ValueError, match="pagination"):
        AdaptiveHopPresentationStore(None).page(cursor=cursor, limit=limit)


def test_corrupt_manifest_is_not_hidden_as_empty_history(tmp_path):
    capture = publish_capture(tmp_path, count=0)
    path = tmp_path / "scanner-adaptive-recordings" / capture.session_id / "manifest.json"
    path.write_bytes(b"corrupt")
    presentation = AdaptiveHopPresentationStore(tmp_path)
    with pytest.raises(BundleCorruptionError):
        presentation.page(cursor=0, limit=1)
    with pytest.raises(BundleCorruptionError):
        presentation.detail(capture.session_id)


def test_adaptive_glrt_uses_separate_actual_event_binding_and_keeps_fractional_offsets(tmp_path):
    capture = publish_capture(tmp_path, count=30)
    reader = AdaptiveHopGlrtPresentationStore(tmp_path)
    assert reader.detail(capture.session_id) is None
    publication = publication_fixture(capture.manifest.receipt, capture.manifest_sha256)
    ScannerGlrtStore(tmp_path).publish(publication)
    assert reader.detail(capture.session_id) == publication
    assert reader.detail(capture.session_id).evidence.results[25].fractional_offset_samples == 0.375
    assert reader.detail("missing") is None


def test_adaptive_glrt_rejects_wrong_manifest_without_hiding_recording(tmp_path):
    capture = publish_capture(tmp_path, count=2)
    ScannerGlrtStore(tmp_path).publish(publication_fixture(capture.manifest.receipt))
    with pytest.raises(ValueError):
        AdaptiveHopGlrtPresentationStore(tmp_path).detail(capture.session_id)
    assert AdaptiveHopPresentationStore(tmp_path).detail(capture.session_id) is not None
