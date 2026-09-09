"""Explicit PPU V2 to application adaptive contracts; never a fixed-hop receipt."""

from __future__ import annotations

import dataclasses
import importlib
from typing import Any

import numpy as np

from leo.radio.pluto_persistent_hop import _load_plan, _map_settings, _reason_name, _state_name
from leo.scanner.adaptive_hop import (
    AdaptiveHopDecisionV1,
    AdaptiveHopEventV1,
    AdaptiveHopPlanV1,
    AdaptiveHopReceiptV1,
    AdaptiveHopTerminalV1,
    AdaptiveHopVisitV1,
)
from leo.scanner.adaptive_hop_ports import AdaptiveHopVisitBlock
from leo.scanner.persistent_hop import (
    PersistentHopRestorationReceiptV1,
    persistent_hop_wire_session_id,
)
from leo.scanner.ports import ScanRadioIdentity

_REASONS = ("warmup", "weighted", "exploration", "none_active", "fault_fallback")


def load_adaptive_policy(plan: AdaptiveHopPlanV1) -> Any:
    plan = AdaptiveHopPlanV1.model_validate(plan)
    module = importlib.import_module("pluto_plus.adaptive_hop")
    return module.AdaptiveHopPolicyV2(
        generation=plan.policy.generation,
        mode=module.AdaptiveHopMode[plan.policy.mode.upper()],
    )


def map_adaptive_event(event: Any, choice: Any, plan: AdaptiveHopPlanV1) -> AdaptiveHopEventV1:
    event.pack()
    choice.pack(event)
    expected_kind = "STARTUP" if event.dwell_index == 0 else "RETUNE"
    if event.kind.name != expected_kind:
        raise ValueError("adaptive source event kind disagrees with its visit")
    decision = AdaptiveHopDecisionV1.model_validate(
        dict(
            mode=choice.mode.name.lower(),
            generation=choice.generation,
            decision_counter=choice.decision_counter,
            basis_visit=None if choice.basis_visit == (1 << 64) - 1 else choice.basis_visit,
            proposed_target=choice.proposed_target,
            reason=_REASONS[choice.reason],
            active_mask=choice.active_mask,
            quiet_mask=choice.quiet_mask,
            consecutive_misses=choice.consecutive_misses,
            cooldown_remaining_samples=choice.cooldown_remaining_samples,
        )
    )
    return AdaptiveHopEventV1(
        visit_index=event.dwell_index,
        event_sequence=event.event_sequence,
        device_event_id=event.device_event_id,
        device_event_flags=3,  # event.pack() above requires both exact attestations
        target_index=event.to_profile_index,
        from_profile_index=None if event.from_profile_index == 255 else event.from_profile_index,
        fastlock_slot=event.fastlock_slot,
        target=plan.geometry.profiles[event.to_profile_index].target,
        actual_lo_frequency_hz=event.actual_lo_frequency_hz,
        actual_if_offset_hz=event.actual_if_offset_hz,
        invalid_start_counter=event.invalid_start_counter,
        transition_before_counter=event.transition_before_counter,
        transition_after_counter=event.transition_after_counter,
        valid_start_counter=event.invalid_end_counter_exclusive,
        decision=decision,
    )


def map_adaptive_visit(upstream: Any, plan: AdaptiveHopPlanV1) -> AdaptiveHopVisitV1:
    event = map_adaptive_event(upstream.event, upstream.choice, plan)
    profile = upstream.profile
    if (
        profile.target_index != event.target_index
        or profile.fastlock_profile_index != event.fastlock_slot
        or profile.center_hz != event.target.if_center_hz
        or profile.lo_hz != event.actual_lo_frequency_hz
    ):
        raise ValueError("adaptive visit profile differs from actual source tuning")
    visit = AdaptiveHopVisitV1(
        event=event, valid_end_counter_exclusive=upstream.valid_end_counter_exclusive
    )
    if (
        visit.valid_sample_count != plan.geometry.valid_visit_samples
        or event.decision.mode != plan.policy.mode
        or event.decision.generation != plan.policy.generation
        or event.valid_start_counter
        != event.transition_after_counter + plan.geometry.transition_guard_samples
    ):
        raise ValueError("adaptive sampled visit differs from its requested geometry/policy")
    return visit


def map_adaptive_sampled_visit(sampled: Any, plan: AdaptiveHopPlanV1) -> AdaptiveHopVisitBlock:
    evidence = map_adaptive_visit(sampled.visit, plan)
    values = np.asarray(sampled.samples)
    if values.dtype != np.complex64 or values.shape != (2, evidence.valid_sample_count):
        raise ValueError("adaptive PPU IQ differs from its full dual-RX interval")
    return AdaptiveHopVisitBlock(np.ascontiguousarray(values.T), (0, 1), evidence)


def map_adaptive_capture(
    upstream: Any,
    *,
    plan: AdaptiveHopPlanV1,
    identity: ScanRadioIdentity,
    session_id: str,
) -> AdaptiveHopReceiptV1:
    module = importlib.import_module("pluto_plus.adaptive_hop_client")
    if not isinstance(upstream, module.AdaptiveHopCaptureReceiptV2):
        raise ValueError("adaptive application requires an explicit V2 capture receipt")
    plan = AdaptiveHopPlanV1.model_validate(plan)
    stream = upstream.stream
    stream.request.pack()
    stream.status.pack()
    expected = _load_plan(plan.geometry).request(
        session_id=persistent_hop_wire_session_id(session_id)
    )
    if (
        upstream.radio_serial != identity.serial
        or upstream.radio_uri != identity.uri
        or stream.request.policy != load_adaptive_policy(plan)
        or dataclasses.replace(stream.request.geometry, profiles=expected.profiles) != expected
        or any(
            dataclasses.replace(actual, profile_crc32=0) != wanted
            for actual, wanted in zip(
                stream.request.geometry.profiles, expected.profiles, strict=True
            )
        )
    ):
        raise ValueError("adaptive capture request or radio identity changed")
    status = stream.status.geometry
    fields = {
        name: getattr(status, name)
        for name in AdaptiveHopTerminalV1.model_fields
        if name
        not in {"schema_version", "wire_protocol_version", "wire_feature_flags", "state", "reason"}
    }
    fields["flags"] = int(status.flags)
    for name in ("active_profile_index", "restored_profile_index"):
        fields[name] = None if fields[name] == 255 else fields[name]
    terminal = AdaptiveHopTerminalV1.model_validate(
        dict(
            fields,
            state=_state_name(status.state),
            reason=_reason_name(status.reason),
        )
    )
    host = upstream.host_lifecycle
    if host is None or host.receive_buffer_closed is not True or host.fastlock_inactive is not True:
        raise ValueError("adaptive capture lacks exact host cleanup evidence")
    restoration = PersistentHopRestorationReceiptV1(
        status="restored",
        original_settings=_map_settings(host.original_settings),
        restored_settings=_map_settings(host.restored_settings),
        receive_buffer_closed=True,
        fastlock_inactive=True,
    )
    receipt = AdaptiveHopReceiptV1(
        session_id=session_id,
        radio_id=identity.radio_id,
        radio_serial=identity.serial,
        radio_uri=identity.uri,
        plan=plan,
        stream_generation=stream.stream_generation,
        source_span_attested=stream.source_span_attested,
        kernel_buffers_requested=upstream.kernel_buffers_requested,
        kernel_buffers_readback=upstream.kernel_buffers_readback,
        terminal=terminal,
        events=tuple(
            map_adaptive_event(e, d, plan)
            for e, d in zip(stream.events, stream.choices, strict=True)
        ),
        complete_visit_count=len(stream.visits),
        valid_sample_count=stream.valid_sample_count,
        transition_invalid_sample_count=stream.transition_invalid_sample_count,
        unclassified_sample_count=stream.unclassified_sample_count,
        unreceived_tail_sample_count=stream.unreceived_tail_sample_count,
        duty_denominator_sample_count=stream.duty_denominator_sample_count,
        valid_duty_ppm=stream.valid_duty_ppm,
        duty_target_met=stream.duty_target_met,
        restoration=restoration,
    )
    if tuple(map_adaptive_visit(v, plan) for v in stream.visits) != receipt.visits:
        raise ValueError("adaptive complete visits disagree with its event prefix")
    if tuple(
        (c.target_index, c.visit_count, c.valid_sample_count) for c in stream.target_coverage
    ) != tuple(
        (c.target_index, c.visit_count, c.valid_sample_count) for c in receipt.target_coverage
    ):
        raise ValueError("adaptive target coverage disagrees with recorded actual visits")
    return receipt
