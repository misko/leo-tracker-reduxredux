from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from leo.scanner import (
    PersistentHopPlanV1,
    PersistentHopRestorationReceiptV1,
    PersistentHopSessionReceiptV1,
    PersistentHopTargetCoverageV1,
    PersistentHopTerminalStatusV1,
    PersistentHopVisitV1,
    compile_persistent_hop_plan_v1,
)
from leo.scanner.fake_persistent_hop import (
    FakePersistentHopError,
    FakePersistentHopRadio,
    default_fake_persistent_hop_settings,
)

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "persistent_hop_session_v1.json"


@pytest.mark.parametrize("sample_rate_hz", [2_500_000, 5_000_000])
def test_plan_freezes_duration_rate_bandwidth_and_profile_order(sample_rate_hz: int) -> None:
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=sample_rate_hz)  # type: ignore[arg-type]

    assert plan.nominal_duration_seconds == 300
    assert plan.valid_visit_ms == 120
    assert plan.maximum_visit_count == 2_500
    assert plan.bandwidth_hz == sample_rate_hz
    assert plan.valid_visit_samples == sample_rate_hz * 120 // 1_000
    assert plan.transition_guard_samples == sample_rate_hz * 11 // 1_000
    assert plan.planned_valid_duty_ppm == 916_030
    assert plan.nominal_device_sample_count == sample_rate_hz * 300
    assert [
        (profile.fastlock_profile_index, profile.target.channel, profile.target.edge.value)
        for profile in plan.profiles
    ] == [
        (0, 1, "lower"),
        (1, 2, "lower"),
        (2, 3, "lower"),
        (3, 4, "lower"),
        (4, 1, "upper"),
        (5, 2, "upper"),
        (6, 3, "upper"),
        (7, 4, "upper"),
    ]


def test_plan_rejects_rate_bandwidth_mismatch_and_profile_reordering() -> None:
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    document = plan.model_dump(mode="python")

    with pytest.raises(ValidationError, match="bandwidth must equal sample rate"):
        PersistentHopPlanV1.model_validate({**document, "bandwidth_hz": 5_000_000})
    with pytest.raises(ValidationError, match="profiles must map 0..7"):
        PersistentHopPlanV1.model_validate(
            {**document, "profiles": tuple(reversed(document["profiles"]))}
        )


@pytest.mark.parametrize("fixture_index", [0, 1])
def test_fake_full_session_matches_shared_counter_and_duty_fixture(fixture_index: int) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    case = fixture["cases"][fixture_index]
    radio = FakePersistentHopRadio(
        transition_invalid_ms=fixture["transition_invalid_ms"],
        first_device_sample_counter=fixture["first_device_sample_counter"],
    )
    radio.open()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=case["sample_rate_hz"])

    receipt = radio.begin_session(plan, session_id=f"fixture-{fixture_index}").run_to_completion()

    assert receipt.qualified is True
    assert receipt.metadata_abi_version == 3
    assert len(receipt.visits) == case["completed_visit_count"]
    assert receipt.duty_denominator_sample_count == case["session_device_sample_count"]
    assert receipt.valid_sample_count == case["valid_sample_count"]
    assert receipt.transition_invalid_sample_count == case["transition_invalid_sample_count"]
    assert receipt.valid_duty_ppm == case["valid_duty_ppm"]
    assert receipt.valid_duty_percent == pytest.approx(90.9090909)
    assert [item.visit_count for item in receipt.target_coverage] == case["target_visit_counts"]
    assert receipt.session_end_device_sample_counter_exclusive == (
        fixture["first_device_sample_counter"] + case["session_device_sample_count"]
    )
    assert receipt.terminal_status.planned_dwells == 2_500
    assert receipt.terminal_status.visits_started == len(receipt.visits)
    assert receipt.terminal_status_attested is True
    first = receipt.visits[0]
    expected = case["first_visit"]
    assert first.transition_invalid_before.device_sample_counter == expected["invalid_start"]
    assert first.transition_invalid_before.transition_after_counter == expected["transition_after"]
    assert (
        first.transition_invalid_before.device_sample_counter_end_exclusive
        == expected["invalid_end"]
    )
    assert first.valid_device_sample_counter == expected["valid_start"]
    assert first.valid_device_sample_counter_end_exclusive == expected["valid_end"]
    assert receipt.restoration.status == "restored"
    assert radio.settings == default_fake_persistent_hop_settings()
    radio.close()


def test_fake_visit_block_contains_only_valid_deterministic_iq() -> None:
    first_radio = FakePersistentHopRadio()
    second_radio = FakePersistentHopRadio()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000, kernel_buffers=4)
    for radio in (first_radio, second_radio):
        radio.open()

    first = first_radio.begin_session(plan, session_id="block-a").read_visit()
    duplicate = second_radio.begin_session(plan, session_id="block-b").read_visit()

    assert first.samples.shape == (300_000, 2)
    assert first.samples.dtype == np.complex64
    assert first.samples.flags.writeable is False
    np.testing.assert_array_equal(first.samples, duplicate.samples)
    assert first.samples[0].tolist() == [1 + 1j, 1 + 2j]
    assert first.evidence.transition_invalid_before.kind == "startup_prime"
    assert first.evidence.transition_invalid_before.sample_count == 30_000
    assert first.evidence.valid_device_sample_counter == 1_030_000
    assert first.evidence.valid_sample_count == plan.valid_visit_samples


def test_visit_accepts_only_bounded_lossless_lo_quantization() -> None:
    radio = FakePersistentHopRadio()
    radio.open()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    visit = radio.begin_session(plan, session_id="quantization").read_visit().evidence
    document = visit.model_dump(mode="python")

    quantized = PersistentHopVisitV1.model_validate(
        {
            **document,
            "actual_lo_frequency_hz": visit.requested_if_center_hz - 7,
            "actual_if_offset_hz": 7,
        }
    )
    assert quantized.actual_if_offset_hz == 7
    with pytest.raises(ValidationError, match="bounded IF offset"):
        PersistentHopVisitV1.model_validate(
            {
                **document,
                "actual_lo_frequency_hz": visit.requested_if_center_hz - 11,
                "actual_if_offset_hz": 11,
            }
        )


@pytest.mark.parametrize(
    ("radio_kwargs", "fault_kind", "counter_extra"),
    [
        ({"gaps_before_visits": {3: 17}}, "missing_samples", 17),
        ({"overflow_visits": {3}}, "rx_overflow", 0),
        (
            {"hop_event_sequence_gaps_before_visits": {3: 2}},
            "hop_event_sequence_gap",
            0,
        ),
    ],
)
def test_fake_continuity_faults_fail_closed_with_truthful_accounting(
    radio_kwargs: dict[str, object], fault_kind: str, counter_extra: int
) -> None:
    radio = FakePersistentHopRadio(**radio_kwargs)  # type: ignore[arg-type]
    radio.open()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)

    receipt = radio.begin_session(plan, session_id=f"fault-{fault_kind}").run_to_completion()

    assert receipt.capture_outcome == "failed"
    assert receipt.continuity_attested is False
    assert receipt.qualified is False
    assert [item.kind for item in receipt.continuity_faults] == [fault_kind]
    expected_visits = 4 if fault_kind == "rx_overflow" else 3
    assert len(receipt.visits) == expected_visits
    assert receipt.duty_denominator_sample_count == (
        receipt.valid_sample_count + receipt.transition_invalid_sample_count + counter_extra
    )
    assert receipt.terminal_status.flags & 4
    assert (
        max(item.visit_count for item in receipt.target_coverage)
        - min(item.visit_count for item in receipt.target_coverage)
        <= 1
    )


def test_restoration_failure_is_terminal_evidence_not_a_qualified_session() -> None:
    radio = FakePersistentHopRadio(restoration_error="injected restore failure")
    original = radio.settings
    radio.open()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)

    receipt = radio.begin_session(plan, session_id="restore-failure").run_to_completion()

    assert receipt.capture_outcome == "failed"
    assert receipt.qualified is False
    assert receipt.restoration.status == "failed"
    assert receipt.restoration.error_message == "injected restore failure"
    assert receipt.terminal_status.reason == "restore_error"
    assert radio.settings != original


def test_session_receipt_rejects_forged_duty_and_target_coverage() -> None:
    radio = FakePersistentHopRadio()
    radio.open()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    receipt = radio.begin_session(plan, session_id="tamper-proof").run_to_completion()
    document = receipt.model_dump(mode="python")

    with pytest.raises(ValidationError, match="terminal accounting disagrees"):
        PersistentHopSessionReceiptV1.model_validate(
            {**document, "valid_duty_ppm": receipt.valid_duty_ppm + 1}
        )
    forged_coverage = [dict(item) for item in document["target_coverage"]]
    forged_coverage[0]["visit_count"] += 1
    with pytest.raises(ValidationError, match="target coverage disagrees"):
        PersistentHopSessionReceiptV1.model_validate(
            {**document, "target_coverage": forged_coverage}
        )


def test_transport_loss_cannot_produce_a_terminal_receipt() -> None:
    radio = FakePersistentHopRadio(transport_loss_before_visit=1)
    radio.open()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    session = radio.begin_session(plan, session_id="transport-loss")
    session.read_visit()

    with pytest.raises(FakePersistentHopError, match="transport loss"):
        session.read_visit()
    with pytest.raises(FakePersistentHopError, match="no server-attested"):
        session.finish()


@pytest.mark.parametrize("visits_before_cancel", [0, 3])
def test_in_band_cancel_retains_terminal_status_and_exact_restoration(
    visits_before_cancel: int,
) -> None:
    radio = FakePersistentHopRadio()
    original = radio.settings
    radio.open()
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=5_000_000, kernel_buffers=2)
    session = radio.begin_session(plan, session_id=f"cancel-{visits_before_cancel}")
    for _ in range(visits_before_cancel):
        session.read_visit()

    session.request_cancel()
    with pytest.raises(StopIteration):
        session.read_visit()
    receipt = session.finish()

    assert receipt.capture_outcome == "cancelled"
    assert receipt.terminal_status.state == "cancelled"
    assert receipt.terminal_status.reason == "client_close"
    assert receipt.terminal_status_attested is True
    assert receipt.continuity_attested is True
    assert len(receipt.visits) == visits_before_cancel
    assert receipt.valid_duty_ppm == (909_090 if visits_before_cancel else 0)
    assert receipt.restoration.status == "restored"
    assert radio.settings == original
    radio.close()


def test_previsit_failure_receipt_can_retain_terminal_restoration_without_fake_iq() -> None:
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    settings = default_fake_persistent_hop_settings()
    restoration = PersistentHopRestorationReceiptV1(
        status="restored",
        original_settings=settings,
        restored_settings=settings,
        receive_buffer_closed=True,
        fastlock_inactive=True,
    )
    terminal = PersistentHopTerminalStatusV1(
        state="failed",
        reason="device",
        error_code=-5,
        flags=1 | 8 | 16 | 32,
        session_id=1,
        visits_started=0,
        events_emitted=0,
        next_event_sequence=0,
        last_block_sequence=0,
        last_block_end_counter=1_000_000,
        first_counter=1_000_000,
        final_counter=1_000_000,
        restore_before_counter=1_000_000,
        restore_after_counter=1_000_000,
        restored_lo_frequency_hz=settings.center_frequency_hz,
        restore_error_code=0,
        startup_invalid_start_counter=1_000_000,
        startup_invalid_end_counter_exclusive=1_000_000,
        device_dropped_events=0,
    )
    coverage = tuple(
        PersistentHopTargetCoverageV1(
            target_index=profile.target_index,
            target=profile.target,
            visit_count=0,
            valid_sample_count=0,
        )
        for profile in plan.profiles
    )

    receipt = PersistentHopSessionReceiptV1(
        session_id="previsit-failure",
        radio_id="radio-a",
        radio_serial="serial-a",
        radio_uri="ip:192.168.1.20",
        plan=plan,
        stream_generation="hop-1",
        kernel_buffers_requested=8,
        kernel_buffers_readback=8,
        capture_outcome="failed",
        terminal_status=terminal,
        session_start_device_sample_counter=1_000_000,
        session_end_device_sample_counter_exclusive=1_000_000,
        visits=(),
        target_coverage=coverage,
        valid_sample_count=0,
        transition_invalid_sample_count=0,
        missing_sample_count=0,
        overflow_count=0,
        hop_event_sequence_gap_count=0,
        duty_denominator_sample_count=0,
        valid_duty_ppm=0,
        continuity_attested=True,
        duty_target_met=False,
        restoration=restoration,
    )

    assert receipt.valid_duty_percent == 0.0
    assert receipt.qualified is False
