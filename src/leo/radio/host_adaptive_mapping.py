"""Explicit provider major 3 mapping; native IQ and host feedback stay separate."""

from __future__ import annotations

import dataclasses
import importlib
from typing import Any

import numpy as np

from leo.radio.adaptive_hop_mapping import _load_policy, _map_capture, map_adaptive_visit
from leo.radio.host_decision_worker import HostDecisionWorkResult
from leo.scanner.host_adaptive import (
    HostAdaptiveHopPlanV2,
    HostAdaptiveHopPlanV3,
    HostAdaptiveHopReceiptV2,
    HostAdaptiveHopReceiptV3,
    HostAdaptiveHopTerminalV2,
    HostDecisionNumericsV1,
    HostDecisionNumericsV2,
    HostDecisionRecordV1,
    HostDecisionRecordV2,
)
from leo.scanner.host_adaptive_ports import HostAdaptiveHopVisitBlock
from leo.scanner.ports import ScanRadioIdentity


def _validated_plan(plan: HostAdaptiveHopPlanV2 | HostAdaptiveHopPlanV3):
    model = HostAdaptiveHopPlanV3 if plan.schema_version == 3 else HostAdaptiveHopPlanV2
    return model.model_validate(plan)


def load_host_policy(plan: HostAdaptiveHopPlanV2 | HostAdaptiveHopPlanV3) -> Any:
    plan = _validated_plan(plan)
    return _load_policy(plan.policy)


def load_host_decision(plan: HostAdaptiveHopPlanV2 | HostAdaptiveHopPlanV3) -> Any:
    plan = _validated_plan(plan)
    module = importlib.import_module("pluto_plus.host_adaptive_hop")
    model = (
        module.HostDecisionConfigurationV2
        if isinstance(plan, HostAdaptiveHopPlanV3)
        else module.HostDecisionConfigurationV1
    )
    fields = (
        {"source_rate_hz": plan.decision.source_rate_hz}
        if isinstance(plan, HostAdaptiveHopPlanV3)
        else {}
    )
    return model(
        receiver_id=plan.classification_receiver,
        configuration_sha256=bytes.fromhex(plan.decision.configuration_sha256[7:]),
        **fields,
    )


def map_host_sampled_visit(
    sampled: Any, plan: HostAdaptiveHopPlanV2 | HostAdaptiveHopPlanV3
) -> HostAdaptiveHopVisitBlock:
    module = importlib.import_module("pluto_plus.host_adaptive_hop_stream")
    if not isinstance(sampled, module.HostAdaptiveHopSampledVisitV3):
        raise ValueError("host adaptive samples require provider major 3")
    if sampled.receiver_id != plan.classification_receiver:
        raise ValueError("host adaptive physical receiver differs from the requested plan")
    evidence = map_adaptive_visit(sampled.visit, plan)
    values = np.asarray(sampled.samples)
    if values.dtype != np.complex64 or values.shape != (1, evidence.valid_sample_count):
        raise ValueError("host adaptive IQ differs from its native single-RX interval")
    return HostAdaptiveHopVisitBlock(
        np.ascontiguousarray(values.T), (plan.classification_receiver,), evidence
    )


def map_host_capture(
    upstream: Any,
    *,
    plan: HostAdaptiveHopPlanV2 | HostAdaptiveHopPlanV3,
    identity: ScanRadioIdentity,
    session_id: str,
    host_decisions: tuple[HostDecisionRecordV1 | HostDecisionRecordV2, ...],
) -> HostAdaptiveHopReceiptV2 | HostAdaptiveHopReceiptV3:
    module = importlib.import_module("pluto_plus.host_adaptive_hop_client")
    if not isinstance(upstream, module.HostAdaptiveHopCaptureReceiptV3):
        raise ValueError("host adaptive application requires provider major 3")
    plan = _validated_plan(plan)
    if upstream.stream.request.decision != load_host_decision(plan):
        raise ValueError("host adaptive provider changed the detector configuration or receiver")
    receipt_model = (
        HostAdaptiveHopReceiptV3 if plan.schema_version == 3 else HostAdaptiveHopReceiptV2
    )
    receipt = _map_capture(
        upstream,
        plan=plan,
        identity=identity,
        session_id=session_id,
        terminal_model=HostAdaptiveHopTerminalV2,
        receipt_model=receipt_model,
        receipt_fields={"host_decisions": host_decisions},
    )
    assert isinstance(receipt, (HostAdaptiveHopReceiptV2, HostAdaptiveHopReceiptV3))
    return receipt


def map_host_work_result(
    result: HostDecisionWorkResult,
    *,
    feedback_ns: int,
    accepted: bool,
    feedback_error: str | None = None,
    feedback_completed_ns: int | None = None,
    submitted: bool = True,
    source_rate_hz: int = 10_000_000,
) -> HostDecisionRecordV1 | HostDecisionRecordV2:
    """Map the exact feedback-time snapshot used for submission by the IIO owner."""
    feedback = result.feedback(feedback_ns)
    evidence = result.evidence
    failure = result.failure
    health = "healthy"
    if evidence is None:
        health = "detector_failure"
        failure = failure or "host detector returned no numerical evidence"
    elif not feedback.healthy:
        health = "expired"
        failure = "host decision exceeded its one-second processing age"
    values = dict(
            session_id=feedback.session_id,
            generation=feedback.generation,
            stream_generation=feedback.stream_id,
            visit_index=feedback.visit,
            event_sequence=feedback.event_sequence,
            receiver_id=feedback.receiver_id,
            target_index=feedback.target_index,
            valid_start_counter=feedback.valid_start,
            valid_end_counter_exclusive=feedback.valid_end,
            configuration_sha256="sha256:" + feedback.configuration_sha256.hex(),
            submitted_monotonic_ns=result.submitted_ns,
            started_monotonic_ns=result.started_ns,
            completed_monotonic_ns=result.completed_ns,
            feedback_monotonic_ns=feedback_ns,
            feedback_completed_monotonic_ns=(
                feedback_ns if feedback_completed_ns is None else feedback_completed_ns
            ),
            numerics=(
                HostDecisionNumericsV1.model_validate(dataclasses.asdict(evidence))
                if source_rate_hz == 10_000_000
                else HostDecisionNumericsV2.model_validate(
                    {
                        **dataclasses.asdict(evidence),
                        "schema_version": 2,
                        "source_rate_hz": source_rate_hz,
                    }
                )
            )
            if evidence is not None
            else None,
            health=health,
            failure=failure[:2048] if failure else None,
            feedback_outcome=feedback.outcome.name.lower(),
            feedback_disposition="rejected"
            if feedback_error and submitted
            else "not_submitted"
            if not submitted
            else "accepted"
            if accepted
            else "source_ended",
            feedback_error=feedback_error,
        )
    if source_rate_hz == 10_000_000:
        return HostDecisionRecordV1.model_validate(values)
    return HostDecisionRecordV2.model_validate(
        {**values, "schema_version": 2, "source_rate_hz": source_rate_hz}
    )
