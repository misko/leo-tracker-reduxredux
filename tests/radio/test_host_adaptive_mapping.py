import dataclasses

import numpy as np
import pytest
from pluto_plus.host_adaptive_hop import HostDecisionOutcome, HostFeedbackV1
from pluto_plus.host_adaptive_hop_stream import HostAdaptiveHopSampledVisitV3

from leo.analysis.host_decision import HostDecisionEvidence
from leo.radio.adaptive_hop_mapping import map_adaptive_capture
from leo.radio.host_adaptive_mapping import (
    load_host_decision,
    map_host_capture,
    map_host_sampled_visit,
    map_host_work_result,
)
from leo.radio.host_decision_worker import HostDecisionWorkResult
from leo.scanner.ports import ScanRadioIdentity
from tests.radio.adaptive_hop_fixtures import upstream_receipt
from tests.scanner.adaptive_hop_fixtures import receipt_fixture
from tests.scanner.host_adaptive_fixtures import host_receipt


@pytest.mark.parametrize("receiver", [0, 1])
@pytest.mark.parametrize("mode", ["shadow", "adaptive"])
def test_major3_maps_actual_tuning_single_payload_and_complete_receipt(receiver, mode):
    receipt = host_receipt(receiver=receiver, mode=mode, count=30)
    upstream = upstream_receipt(receipt)
    identity = ScanRadioIdentity(receipt.radio_id, receipt.radio_serial, receipt.radio_uri)
    mapped = map_host_capture(
        upstream,
        plan=receipt.plan,
        identity=identity,
        session_id=receipt.session_id,
        host_decisions=receipt.host_decisions,
    )
    assert mapped == receipt
    values = np.full((1, 1_200_000), 123 - 456j, dtype=np.complex64)
    sampled = HostAdaptiveHopSampledVisitV3(upstream.stream.visits[25], values, receiver)
    block = map_host_sampled_visit(sampled, receipt.plan)
    assert block.receiver_ids == (receiver,)
    assert block.samples.shape == (1_200_000, 1)
    assert block.evidence == receipt.visits[25]
    assert block.samples[0, 0] == 123 - 456j
    with pytest.raises(ValueError, match="physical receiver"):
        map_host_sampled_visit(dataclasses.replace(sampled, receiver_id=1 - receiver), receipt.plan)
    with pytest.raises(ValueError, match="explicit V2"):
        map_adaptive_capture(
            upstream, plan=receipt.plan, identity=identity, session_id=receipt.session_id
        )


@pytest.mark.parametrize("fault", ["major", "configuration", "receiver", "serial", "uri"])
def test_mapping_refuses_mixed_wire_contracts_or_provider_identity(fault):
    receipt = host_receipt(count=2)
    upstream = upstream_receipt(receipt)
    if fault == "major":
        upstream = upstream_receipt(receipt_fixture(count=2))
    elif fault in ("configuration", "receiver"):
        decision = load_host_decision(receipt.plan)
        decision = dataclasses.replace(
            decision,
            **({"receiver_id": 1} if fault == "receiver" else {"configuration_sha256": b"b" * 32}),
        )
        upstream = dataclasses.replace(
            upstream,
            stream=dataclasses.replace(
                upstream.stream,
                request=dataclasses.replace(upstream.stream.request, decision=decision),
            ),
        )
    else:
        upstream = dataclasses.replace(upstream, **{"radio_" + fault: "foreign"})
    with pytest.raises(ValueError):
        map_host_capture(
            upstream,
            plan=receipt.plan,
            session_id=receipt.session_id,
            identity=ScanRadioIdentity(receipt.radio_id, receipt.radio_serial, receipt.radio_uri),
            host_decisions=receipt.host_decisions,
        )


@pytest.mark.parametrize("state", ["healthy", "expired", "failure", "ended", "rejected"])
def test_worker_mapping_preserves_unknown_failure_and_feedback_acceptance(state):
    record = host_receipt(count=2).host_decisions[0]
    source = HostFeedbackV1(
        session_id=record.session_id,
        generation=record.generation,
        stream_id=record.stream_generation,
        visit=0,
        event_sequence=0,
        receiver_id=record.receiver_id,
        target_index=record.target_index,
        valid_start=record.valid_start_counter,
        valid_end=record.valid_end_counter_exclusive,
        configuration_sha256=bytes.fromhex(record.configuration_sha256[7:]),
        outcome=HostDecisionOutcome.UNKNOWN,
        healthy=0,
        screen_mask=0,
        confirmation_mask=0,
    )
    evidence = HostDecisionEvidence(**record.numerics.model_dump(exclude={"schema_version"}))
    result = HostDecisionWorkResult(
        source,
        None if state == "failure" else evidence,
        "synthetic failure" if state == "failure" else None,
        100,
        200,
        10_000_000,
    )
    mapped = map_host_work_result(
        result,
        feedback_ns=2_000_000_000 if state == "expired" else 20_000_000,
        accepted=state != "ended",
        feedback_error="synthetic rejection" if state == "rejected" else None,
        feedback_completed_ns=2_001_000_000 if state == "expired" else 21_000_000,
    )
    assert mapped.health == {"expired": "expired", "failure": "detector_failure"}.get(
        state, "healthy"
    )
    assert mapped.feedback_outcome == (
        "unknown" if state in ("expired", "failure") else "not_detected"
    )
    assert mapped.feedback_disposition == {"ended": "source_ended", "rejected": "rejected"}.get(
        state, "accepted"
    )
    if state == "expired":
        assert mapped.numerics == record.numerics
    assert mapped.feedback_call_elapsed_ns == 1_000_000
