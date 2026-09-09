"""Synthetic source-counter fixtures; no RF, detector or timing qualification."""

from __future__ import annotations

import numpy as np

from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.states import GainMode
from leo.scanner.adaptive_hop import (
    AdaptiveHopDecisionV1,
    AdaptiveHopEventV1,
    AdaptiveHopPlanV1,
    AdaptiveHopPolicyV1,
    AdaptiveHopReceiptV1,
    AdaptiveHopTerminalV1,
    AdaptiveHopVisitV1,
)
from leo.scanner.adaptive_hop_ports import AdaptiveHopVisitBlock
from leo.scanner.persistent_hop import (
    PersistentHopRestorationReceiptV1,
    PersistentHopUtcTimingAuthorityV1,
    compile_persistent_hop_plan_v1,
    persistent_hop_wire_session_id,
)


def receipt_fixture(
    *,
    rate=2_500_000,
    mode="adaptive",
    count=10,
    complete=False,
    start=(1 << 53) + 17,
    session_id="adaptive-storage-test",
    plan=None,
    radio_id="synthetic",
    radio_serial="synthetic-only",
    radio_uri="ip:192.168.1.14",
    transition_samples=20,
):
    plan = plan or AdaptiveHopPlanV1(
        geometry=compile_persistent_hop_plan_v1(sample_rate_hz=rate),
        policy=AdaptiveHopPolicyV1(mode=mode, generation=71),
    )
    mode = plan.policy.mode
    g = plan.geometry
    events = []
    counter = start
    index = 0
    while counter - start < g.nominal_device_sample_count if complete else index < count:
        target_index = index % 8 if mode == "shadow" or index < 24 else (0, 2, 3)[index % 3]
        events.append(
            AdaptiveHopEventV1(
                visit_index=index,
                event_sequence=index,
                device_event_id=index + 101,
                target_index=target_index,
                from_profile_index=events[-1].target_index if events else None,
                fastlock_slot=target_index,
                target=g.profiles[target_index].target,
                actual_lo_frequency_hz=g.profiles[target_index].target.if_center_hz,
                actual_if_offset_hz=0,
                invalid_start_counter=counter,
                transition_before_counter=counter + 10,
                transition_after_counter=counter + transition_samples,
                valid_start_counter=counter + transition_samples + g.transition_guard_samples,
                decision=AdaptiveHopDecisionV1(
                    mode=mode,
                    generation=plan.policy.generation,
                    decision_counter=counter,
                    basis_visit=index - 1 if index else None,
                    proposed_target=(index + 3) % 8 if mode == "shadow" else target_index,
                    reason="warmup" if index < 24 else "weighted",
                    active_mask=0 if index < 24 else 13,
                    quiet_mask=0 if index < 24 else 242,
                    consecutive_misses=0,
                    cooldown_remaining_samples=0,
                ),
            )
        )
        counter = events[-1].valid_start_counter + g.valid_visit_samples
        index += 1
    final = counter if complete else events[-1].valid_start_counter + 101 if events else 0
    first = start if events else 0
    valid_count = len(events) if complete else max(0, len(events) - 1)
    invalid = sum(e.valid_start_counter - e.invalid_start_counter for e in events)
    valid = valid_count * g.valid_visit_samples
    denominator = final - first
    duty = valid * 1_000_000 // denominator if denominator else 0
    original = RadioSettingsV1(
        center_frequency_hz=1_100_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receiver_ids=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=tuple(ReceiverGainV1(receiver_id=i, gain_db=40) for i in (0, 1)),
    )
    return AdaptiveHopReceiptV1(
        session_id=session_id,
        radio_id=radio_id,
        radio_serial=radio_serial,
        radio_uri=radio_uri,
        plan=plan,
        stream_generation=123 if events else None,
        source_span_attested=bool(events),
        kernel_buffers_requested=g.kernel_buffers,
        kernel_buffers_readback=g.kernel_buffers,
        terminal=AdaptiveHopTerminalV1(
            state="completed" if complete else "cancelled",
            reason="complete" if complete else "client_close",
            session_id=persistent_hop_wire_session_id(session_id),
            visits_started=len(events),
            events_emitted=len(events),
            next_event_sequence=len(events),
            last_block_sequence=0,
            last_block_end_counter=final,
            first_counter=first,
            final_counter=final,
            restore_before_counter=final,
            restore_after_counter=final + 10,
            restored_lo_frequency_hz=original.center_frequency_hz,
            active_profile_index=events[-1].target_index if events else None,
            restored_profile_index=None,
            startup_invalid_start_counter=first,
            startup_invalid_end_counter_exclusive=events[0].valid_start_counter if events else 0,
        ),
        events=tuple(events),
        complete_visit_count=valid_count,
        valid_sample_count=valid,
        transition_invalid_sample_count=invalid,
        unclassified_sample_count=denominator - valid - invalid,
        unreceived_tail_sample_count=0,
        duty_denominator_sample_count=denominator,
        valid_duty_ppm=duty,
        duty_target_met=duty >= g.minimum_valid_duty_ppm,
        restoration=PersistentHopRestorationReceiptV1(
            status="restored",
            original_settings=original,
            restored_settings=original,
            receive_buffer_closed=True,
            fastlock_inactive=True,
        ),
    )


def block_fixture(receipt, index):
    visit = AdaptiveHopVisitV1(
        event=receipt.events[index],
        valid_end_counter_exclusive=(
            receipt.events[index].valid_start_counter + receipt.plan.geometry.valid_visit_samples
        ),
    )
    samples = np.empty((visit.valid_sample_count, 2), dtype=np.complex64)
    samples[:, 0] = (index + 1) + 2j
    samples[:, 1] = (visit.event.target_index + 10) - 3j
    return AdaptiveHopVisitBlock(samples, (0, 1), visit)


def timing_fixture(receipt):
    return PersistentHopUtcTimingAuthorityV1.from_host_bracket(
        session_id=receipt.session_id,
        session_start_device_sample_counter=receipt.terminal.first_counter,
        sample_rate_hz=receipt.plan.geometry.sample_rate_hz,
        begin_before_realtime_ns=1_780_000_000_000_000_000,
        begin_before_monotonic_ns=1_000_000_000,
        begin_after_realtime_ns=1_780_000_000_001_000_000,
        begin_after_monotonic_ns=1_001_000_000,
        terminal_realtime_ns=1_780_000_300_000_000_000,
        terminal_monotonic_ns=301_000_000_000,
    )
