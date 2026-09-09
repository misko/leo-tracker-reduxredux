from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.scanner.adaptive_hop import AdaptiveHopPlanV1, AdaptiveHopPolicyV1, AdaptiveHopReceiptV1
from leo.scanner.persistent_hop import PersistentHopSessionReceiptV1
from tests.scanner.adaptive_hop_fixtures import receipt_fixture


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
@pytest.mark.parametrize("count,complete", [(0, False), (1, False), (30, False), (0, True)])
def test_adaptive_receipt_round_trip_and_actual_coverage(rate, mode, count, complete):
    receipt = receipt_fixture(rate=rate, mode=mode, count=count, complete=complete)
    restored = AdaptiveHopReceiptV1.model_validate_json(receipt.model_dump_json())
    assert restored == receipt
    assert sum(c.valid_sample_count for c in restored.target_coverage) == receipt.valid_sample_count
    assert sum(c.visit_count for c in restored.target_coverage) == receipt.complete_visit_count
    assert not receipt.visits or receipt.visits[0].event.valid_start_counter > 2**53
    assert not receipt.visits or not hasattr(receipt.visits[0], "sweep_index")
    if complete:
        assert receipt.duty_target_met
        assert receipt.duty_denominator_sample_count >= 300 * rate
    elif count:
        assert len(receipt.events) == len(receipt.visits) + 1
        assert receipt.unclassified_sample_count == 101
    if mode == "adaptive" and len(receipt.events) > 24:
        assert receipt.events[25].target_index == 2  # not visit index modulo eight
    if mode == "shadow" and receipt.events:
        assert receipt.events[0].decision.proposed_target != receipt.events[0].target_index
    with pytest.raises(ValidationError):
        PersistentHopSessionReceiptV1.model_validate_json(receipt.model_dump_json())


@pytest.mark.parametrize(
    "path,value",
    [
        (("valid_sample_count",), 1),
        (("complete_visit_count",), 10),
        (("valid_duty_ppm",), 1_000_000),
        (("duty_target_met",), False),
        (("stream_generation",), None),
        (("source_span_attested",), False),
        (("unclassified_sample_count",), 0),
        (("unreceived_tail_sample_count",), 1),
        (("kernel_buffers_readback",), 7),
        (("terminal", "session_id"), 42),
        (("terminal", "flags"), 1),
        (("terminal", "next_event_sequence"), 12),
        (("terminal", "state"), "failed"),
        (("terminal", "last_block_end_counter"), 0),
        (("restoration", "receive_buffer_closed"), False),
        (("events", 1, "target_index"), 7),
        (("events", 1, "from_profile_index"), 3),
        (("events", 1, "device_event_id"), 99),
        (("events", 1, "decision", "basis_visit"), 1),
        (("events", 1, "decision", "decision_counter"), 0),
        (("events", 1, "decision", "generation"), 99),
        (("events", 1, "decision", "active_mask"), 1),
        (("events", 1, "decision", "cooldown_remaining_samples"), 10_000_000),
        (("events", 1, "actual_if_offset_hz"), 1),
        (("plan", "geometry", "bandwidth_hz"), 5_000_000),
        (("plan", "classification_receiver"), True),
    ],
)
def test_adaptive_receipt_rejects_corrupted_source_binding(path, value):
    payload = receipt_fixture().model_dump(mode="json")
    if path == ("events", 1, "decision", "active_mask"):
        payload["events"][1]["decision"]["quiet_mask"] = 1
    node = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValidationError):
        AdaptiveHopReceiptV1.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", 1.0),
        ("generation", True),
        ("generation", 2**64),
        ("quiet_weight", True),
        ("schema_version", 1.0),
        ("missed_dwells", 4),
        ("cooldown_ms", 1000),
        ("maximum_result_age_ms", 3000),
    ],
)
def test_adaptive_policy_is_exact_and_pinned(field, value):
    payload = dict(mode="adaptive", generation=1)
    payload[field] = value
    with pytest.raises(ValidationError):
        AdaptiveHopPolicyV1.model_validate(payload)


def test_adaptive_revalidates_unchecked_clones_at_boundaries():
    receipt = receipt_fixture()
    with pytest.raises(ValidationError):
        AdaptiveHopReceiptV1.model_validate(receipt.model_copy(update={"valid_sample_count": 0}))
    with pytest.raises(ValidationError):
        AdaptiveHopPlanV1(
            policy=receipt.plan.policy,
            geometry=receipt.plan.geometry.model_copy(update={"bandwidth_hz": 5_000_000}),
        )


def test_empty_cancel_retains_raw_terminal_without_inventing_elapsed_time():
    payload = receipt_fixture(count=0).model_dump()
    payload["terminal"].update(
        final_counter=2**53 + 17,
        restore_before_counter=2**53 + 17,
        restore_after_counter=2**53 + 20,
    )
    receipt = AdaptiveHopReceiptV1.model_validate(payload)
    assert not receipt.source_span_attested
    assert receipt.terminal.final_counter == 2**53 + 17
    assert receipt.duty_denominator_sample_count == 0
    assert receipt.unclassified_sample_count == receipt.unreceived_tail_sample_count == 0
    assert not receipt.duty_target_met
    with pytest.raises(ValidationError):
        AdaptiveHopReceiptV1.model_validate(
            receipt.model_copy(update={"source_span_attested": True})
        )
