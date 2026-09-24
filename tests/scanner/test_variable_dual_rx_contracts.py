from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.states import GainMode
from leo.scanner.adaptive_hop import (
    AdaptiveHopDecisionV1,
    AdaptiveHopEventV3,
    AdaptiveHopPlanV6,
    AdaptiveHopPolicyV2,
    AdaptiveHopReceiptV6,
    AdaptiveHopTerminalV2,
    validate_adaptive_hop_plan,
    validate_adaptive_hop_receipt,
)
from leo.scanner.models import scheduled_low_band_targets
from leo.scanner.persistent_hop import (
    PersistentHopProfileV1,
    PersistentHopRestorationReceiptV1,
    VariableDualRxPlanV5,
    persistent_hop_wire_session_id,
)


def _plan(*, active_ms: int = 360, gain_mode: GainMode = GainMode.MANUAL):
    rate = 2_500_000
    profiles = tuple(
        PersistentHopProfileV1(target_index=i, fastlock_profile_index=i, target=target)
        for i, target in enumerate(scheduled_low_band_targets(bandwidth_hz=rate))
    )
    geometry = VariableDualRxPlanV5(
        sample_rate_hz=rate,
        bandwidth_hz=rate,
        gain_mode=gain_mode,
        gain_db=50.0 if gain_mode is GainMode.MANUAL else None,
        active_valid_visit_ms=active_ms,
        samples_per_block=1_000_000,
        kernel_buffers=16,
        profiles=profiles,
    )
    return AdaptiveHopPlanV6(
        geometry=geometry,
        policy=AdaptiveHopPolicyV2(
            mode="adaptive",
            generation=71,
            allowed_target_mask=0x0F,
        ),
    )


def _receipt() -> AdaptiveHopReceiptV6:
    plan = _plan()
    rate = plan.geometry.sample_rate_hz
    session_id = "variable-dual-rx-test"
    counter = (1 << 53) + 17
    events: list[AdaptiveHopEventV3] = []
    for index, duration_ms in enumerate((120, 360, 120)):
        valid_start = counter + 20
        valid_end = valid_start + rate * duration_ms // 1_000
        events.append(
            AdaptiveHopEventV3(
                visit_index=index,
                event_sequence=index,
                device_event_id=index + 101,
                target_index=index,
                from_profile_index=index - 1 if index else None,
                fastlock_slot=index,
                target=plan.geometry.profiles[index].target,
                actual_lo_frequency_hz=plan.geometry.profiles[index].target.if_center_hz,
                actual_if_offset_hz=0,
                invalid_start_counter=counter,
                transition_before_counter=counter + 10,
                transition_after_counter=valid_start,
                valid_start_counter=valid_start,
                valid_end_counter_exclusive=valid_end,
                decision=AdaptiveHopDecisionV1(
                    mode="adaptive",
                    generation=plan.policy.generation,
                    decision_counter=counter,
                    basis_visit=index - 1 if index else None,
                    proposed_target=index,
                    reason="warmup",
                    active_mask=0,
                    quiet_mask=0,
                    consecutive_misses=0,
                    cooldown_remaining_samples=0,
                ),
            )
        )
        counter = valid_end
    first = events[0].invalid_start_counter
    final = events[-1].valid_end_counter_exclusive
    retained = (0, 2)
    valid = sum(
        events[index].valid_end_counter_exclusive - events[index].valid_start_counter
        for index in retained
    )
    missing = events[1].valid_end_counter_exclusive - events[1].valid_start_counter
    invalid = sum(event.valid_start_counter - event.invalid_start_counter for event in events)
    denominator = final - first
    settings = RadioSettingsV1(
        center_frequency_hz=1_100_000_000,
        sample_rate_hz=rate,
        bandwidth_hz=rate,
        receiver_ids=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=tuple(ReceiverGainV1(receiver_id=i, gain_db=50.0) for i in (0, 1)),
    )
    return AdaptiveHopReceiptV6(
        session_id=session_id,
        radio_id="synthetic",
        radio_serial="synthetic-only",
        radio_uri="ip:192.0.2.1",
        plan=plan,
        stream_generation=123,
        source_span_attested=True,
        kernel_buffers_requested=16,
        kernel_buffers_readback=16,
        terminal=AdaptiveHopTerminalV2(
            state="cancelled",
            reason="client_close",
            session_id=persistent_hop_wire_session_id(session_id),
            visits_started=len(events),
            events_emitted=len(events),
            next_event_sequence=len(events),
            last_block_sequence=len(events) - 1,
            last_block_end_counter=final,
            first_counter=first,
            final_counter=final,
            restore_before_counter=final,
            restore_after_counter=final + 10,
            restored_lo_frequency_hz=settings.center_frequency_hz,
            active_profile_index=events[-1].target_index,
            restored_profile_index=None,
            startup_invalid_start_counter=first,
            startup_invalid_end_counter_exclusive=events[0].valid_start_counter,
        ),
        events=tuple(events),
        retained_visit_indices=retained,
        transport_missing_sample_count=missing,
        complete_visit_count=len(retained),
        valid_sample_count=valid,
        transition_invalid_sample_count=invalid,
        unclassified_sample_count=missing,
        unreceived_tail_sample_count=0,
        duty_denominator_sample_count=denominator,
        valid_duty_ppm=valid * 1_000_000 // denominator,
        duty_target_met=False,
        restoration=PersistentHopRestorationReceiptV1(
            status="restored",
            original_settings=settings,
            restored_settings=settings,
            receive_buffer_closed=True,
            fastlock_inactive=True,
        ),
    )


def test_variable_dual_rx_round_trip_preserves_source_intervals() -> None:
    receipt = _receipt()
    restored = AdaptiveHopReceiptV6.model_validate_json(receipt.model_dump_json())

    assert restored == receipt
    assert validate_adaptive_hop_plan(receipt.plan.model_dump()) == receipt.plan
    assert validate_adaptive_hop_receipt(receipt.model_dump()) == receipt
    assert receipt.plan.geometry.allowed_active_valid_visit_ms == (120, 240, 360)
    assert receipt.plan.geometry.quiet_valid_visit_ms == 120
    assert [visit.valid_sample_count for visit in receipt.visits] == [300_000, 300_000]
    assert receipt.transport_missing_sample_count == 900_000
    assert sum(item.valid_sample_count for item in receipt.target_coverage) == 600_000
    assert receipt.terminal.wire_protocol_version == 3


@pytest.mark.parametrize(
    ("field", "value"),
    [("valid_sample_count", 900_000), ("transport_missing_sample_count", 300_000)],
)
def test_variable_dual_rx_rejects_fixed_dwell_accounting(field: str, value: int) -> None:
    payload = _receipt().model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValidationError):
        AdaptiveHopReceiptV6.model_validate(payload)


def test_variable_dual_rx_rejects_duration_outside_selected_plan() -> None:
    payload = _receipt().model_dump(mode="json")
    replacement_end = (
        payload["events"][1]["valid_start_counter"] + 2_500_000 * 240 // 1_000
    )
    payload["events"][1]["valid_end_counter_exclusive"] = replacement_end
    payload["events"][2]["invalid_start_counter"] = replacement_end
    payload["transition_invalid_sample_count"] += 300_000
    payload["unclassified_sample_count"] = 600_000
    payload["transport_missing_sample_count"] = 600_000
    with pytest.raises(ValidationError, match="outside its plan"):
        AdaptiveHopReceiptV6.model_validate(payload)


def test_variable_dual_rx_gain_is_truthful() -> None:
    assert _plan().geometry.gain_db == 50.0
    automatic = _plan(gain_mode=GainMode.SLOW_ATTACK)
    assert automatic.geometry.gain_db is None

    payload = automatic.geometry.model_dump()
    payload["gain_db"] = 50.0
    with pytest.raises(ValidationError, match="automatic gain"):
        VariableDualRxPlanV5.model_validate(payload)


@pytest.mark.parametrize("active_ms", [120, 240, 360])
def test_variable_dual_rx_admits_each_protocol_three_active_dwell(active_ms: int) -> None:
    assert _plan(active_ms=active_ms).geometry.active_valid_visit_ms == active_ms
