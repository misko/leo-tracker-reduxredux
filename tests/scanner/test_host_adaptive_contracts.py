from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.scanner.adaptive_hop import AdaptiveHopPlanV1, AdaptiveHopReceiptV1
from leo.scanner.host_adaptive import (
    HostAdaptiveHopPlanV2,
    HostAdaptiveHopReceiptV2,
    HostDecisionConfigurationV1,
    HostDecisionNumericsV1,
    HostDecisionRecordV1,
)
from leo.scanner.host_adaptive_ports import HostAdaptiveHopVisitBlock
from leo.scanner.host_adaptive_schedule import (
    HostAdaptiveScheduledScannerIntentV4,
    compile_host_adaptive_hop_plan,
    compile_host_adaptive_scanner_intent,
)
from leo.scanner.single_rx import parse_scheduled_scanner_intent
from tests.scanner.host_adaptive_fixtures import (
    decision_configuration,
    host_plan,
    host_receipt,
    numerics,
)


@pytest.mark.parametrize("receiver", [0, 1])
@pytest.mark.parametrize("mode", ["shadow", "adaptive"])
@pytest.mark.parametrize("complete,count", [(False, 0), (False, 30), (True, 0)])
def test_native_receipt_round_trip_actual_visits_and_old_major_rejection(
    receiver, mode, complete, count
):
    receipt = host_receipt(receiver=receiver, mode=mode, complete=complete, count=count)
    restored = HostAdaptiveHopReceiptV2.model_validate_json(receipt.model_dump_json())
    assert restored == receipt
    assert restored.plan.geometry.sample_rate_hz == 10_000_000
    assert restored.plan.geometry.receiver_ids == (receiver,)
    assert len(restored.host_decisions) == len(restored.visits)
    assert sum(c.valid_sample_count for c in restored.target_coverage) == receipt.valid_sample_count
    if receipt.events:
        assert receipt.events[0].valid_start_counter > 2**53
    if complete:
        assert receipt.duty_denominator_sample_count >= 3_000_000_000
        assert receipt.qualification_duty_floor_met
    if mode == "adaptive" and count > 25:
        assert receipt.events[25].target_index != 25 % 8
    with pytest.raises(ValidationError):
        AdaptiveHopReceiptV1.model_validate_json(receipt.model_dump_json())
    with pytest.raises(ValidationError):
        AdaptiveHopPlanV1.model_validate_json(receipt.plan.model_dump_json())


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", 15),
        ("generation", 72),
        ("stream_generation", 124),
        ("receiver_id", 1),
        ("target_index", 1),
        ("configuration_sha256", "sha256:" + "b" * 64),
        ("valid_start_counter", 10),
        ("visit_index", 2),
    ],
)
def test_receipt_rejects_foreign_feedback_source(field, value):
    payload = host_receipt(count=3).model_dump()
    payload["host_decisions"][0][field] = value
    with pytest.raises(ValidationError):
        HostAdaptiveHopReceiptV2.model_validate(payload)


def test_receipt_requires_every_complete_visit_and_revalidates_copies():
    receipt = host_receipt(count=3)
    with pytest.raises(ValidationError):
        HostAdaptiveHopReceiptV2.model_validate(receipt.model_copy(update={"host_decisions": ()}))
    with pytest.raises(ValidationError):
        HostAdaptiveHopPlanV2.model_validate(
            host_plan().model_copy(update={"classification_receiver": 1})
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("health", "queue_overflow"),
        ("feedback_outcome", "detected"),
        ("feedback_monotonic_ns", 2_000_000_000),
        ("numerics", None),
        ("started_monotonic_ns", 0),
        ("completed_monotonic_ns", None),
        ("feedback_completed_monotonic_ns", 0),
        ("receiver_id", True),
        ("receiver_id", 0.0),
        ("feedback_disposition", "rejected"),
        ("feedback_error", "invented error"),
    ],
)
def test_record_rejects_hidden_failure_or_bad_clock(field, value):
    record = host_receipt(count=2).host_decisions[0].model_dump()
    record[field] = value
    with pytest.raises(ValidationError):
        HostDecisionRecordV1.model_validate(record)


def test_degraded_unknown_and_unapplied_tail_remain_distinct_from_policy():
    record = host_receipt(count=2).host_decisions[0].model_dump()
    ended = HostDecisionRecordV1.model_validate({**record, "feedback_disposition": "source_ended"})
    assert ended.health == "healthy"
    expired = HostDecisionRecordV1.model_validate(
        {
            **record,
            "health": "expired",
            "failure": "one-second host age exceeded",
            "feedback_monotonic_ns": 2_000_000_000,
            "feedback_completed_monotonic_ns": 2_000_002_000,
            "feedback_outcome": "unknown",
        }
    )
    assert expired.numerics == ended.numerics
    overflow = HostDecisionRecordV1.model_validate(
        {
            **record,
            "health": "queue_overflow",
            "failure": "capacity two reached",
            "started_monotonic_ns": None,
            "completed_monotonic_ns": None,
            "numerics": None,
            "feedback_outcome": "unknown",
        }
    )
    assert overflow.numerics is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("screen_mask", 31),
        ("confirmation_mask", 3),
        ("supported_start", 0),
        ("cfo_hz", float("nan")),
        ("screen_scores", (float("inf"),) * 6),
        ("schema_version", True),
        ("candidate_supported", 1),
    ],
)
def test_numerics_reject_incomplete_screen_or_nonfinite_evidence(field, value):
    with pytest.raises(ValidationError):
        HostDecisionNumericsV1.model_validate({**numerics().model_dump(), field: value})


def test_first_candidate_epoch_uses_decimation_phase_and_filter_delay():
    result = numerics()
    assert result.first_candidate_source_epoch_offset == 4 * (50_000 + 121.125) - 80
    assert (
        result.model_copy(update={"fractional_complete": False}).first_candidate_source_epoch_offset
        is None
    )


@pytest.mark.parametrize("receiver", [0, 1])
def test_payload_column_zero_binds_either_physical_receiver(receiver):
    visit = host_receipt(receiver=receiver, count=2).visits[0]
    values = np.full((1_200_000, 1), 123 - 456j, dtype=np.complex64)
    block = HostAdaptiveHopVisitBlock(values, (receiver,), visit)
    assert block.receiver_ids == (receiver,)
    assert block.samples[0, 0] == 123 - 456j
    assert not block.samples.flags.writeable
    with pytest.raises(ValueError):
        HostAdaptiveHopVisitBlock(np.zeros((1_200_000, 2), np.complex64), (receiver,), visit)
    with pytest.raises(ValueError):
        HostAdaptiveHopVisitBlock(values, [receiver], visit)


def intent(**changes):
    return compile_host_adaptive_scanner_intent(
        **{
            "radio_id": "synthetic",
            "radio_serial": "synthetic-only",
            "scheduled_for": datetime(2026, 9, 13, 18, 30, tzinfo=UTC),
            "mode": "adaptive",
            "decision": decision_configuration(),
            "maximum_lateness_seconds": 60,
            "gain_db": 40,
            "margin_gate": 0.025,
            "maximum_acquisition_candidates": 4,
            **changes,
        }
    )


def test_durable_intent_binds_mode_configuration_slot_and_retry_receiver():
    run = intent()
    assert parse_scheduled_scanner_intent(run.model_dump(mode="json")) == run
    assert intent() == run
    assert intent(mode="shadow").operation_key != run.operation_key
    assert (
        intent(
            decision=HostDecisionConfigurationV1(detector_manifest_sha256="sha256:" + "b" * 64)
        ).operation_key
        != run.operation_key
    )
    assert (
        intent(scheduled_for=run.scheduled_for + timedelta(minutes=10)).operation_key
        != run.operation_key
    )
    plan = compile_host_adaptive_hop_plan(run)
    assert plan.geometry.receiver_ids == run.configuration.receiver_ids
    assert plan.policy == run.adaptive_policy
    assert plan.decision == run.decision
    assert plan.geometry.samples_per_block == 262_144
    assert plan.geometry.kernel_buffers == 32
    assert plan.qualification_minimum_valid_duty_ppm == 950_000
    choices = {
        intent(
            scheduled_for=run.scheduled_for + timedelta(minutes=10 * i)
        ).configuration.receiver_ids
        for i in range(32)
    }
    assert choices == {(0,), (1,)}


def test_durable_intent_revalidates_instances_and_exact_major():
    run = intent()
    with pytest.raises(ValidationError):
        HostAdaptiveScheduledScannerIntentV4.model_validate(
            run.model_copy(update={"interval_seconds": 1200})
        )
    payload = run.model_dump(mode="json")
    payload["schema_version"] = 4.0
    with pytest.raises(ValidationError):
        HostAdaptiveScheduledScannerIntentV4.model_validate(payload)
    with pytest.raises(ValueError):
        parse_scheduled_scanner_intent(payload)


@pytest.mark.parametrize("fault", ["receiver", "slot", "mode", "digest", "generation", "interval"])
def test_resigning_cannot_admit_inconsistent_durable_intent(fault):
    payload = intent().model_dump(mode="json")
    if fault == "receiver":
        payload["configuration"]["receiver_ids"][0] ^= 1
    elif fault == "slot":
        payload["scheduled_for"] = "2026-09-13T18:31:00Z"
    elif fault == "mode":
        payload["adaptive_policy"]["mode"] = "shadow"
    elif fault == "generation":
        payload["adaptive_policy"]["generation"] += 1
    elif fault == "interval":
        payload["interval_seconds"] = 1200
    else:
        payload["decision"]["detector_manifest_sha256"] = "sha256:" + "b" * 64
    payload["intent_digest"] = canonical_digest(
        {k: v for k, v in payload.items() if k != "intent_digest"}
    )
    with pytest.raises(ValidationError):
        HostAdaptiveScheduledScannerIntentV4.model_validate(payload)
