from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from leo.scanner.models import ScannerConfigurationV3
from leo.scanner.persistent_hop import PersistentHopPlanV1
from leo.scanner.schedule import ScheduledScannerRunIntentV1
from leo.scanner.single_rx import (
    SingleRxPersistentHopPlanV2,
    SingleRxScannerConfigurationV4,
    SingleRxScheduledScannerIntentV2,
    compile_single_rx_hop_plan,
    compile_single_rx_scanner_intent,
    single_rx_for_operation,
)


def make_intent(index=0):
    scheduled = datetime(2026, 9, 12, tzinfo=UTC) + timedelta(minutes=20 * index)
    return compile_single_rx_scanner_intent(
        operation_key=f"scheduled-scanner:{scheduled.strftime('%Y%m%dT%H%M%SZ')}",
        radio_id="radio-pluto",
        radio_serial="serial-123",
        scheduled_for=scheduled,
        interval_seconds=1200,
        maximum_lateness_seconds=300,
        run_duration_seconds=300,
        dwell_ms=120,
        gain_db=40,
        margin_gate=0.025,
        maximum_acquisition_candidates=8,
    )


def test_receiver_is_stable_across_retry_and_serialization_and_varies_between_scans():
    intents = [make_intent(i) for i in range(100)]
    assert {v.configuration.receiver_ids for v in intents} == {(0,), (1,)}
    for i, intent in enumerate(intents):
        assert make_intent(i) == intent
        assert (
            SingleRxScheduledScannerIntentV2.model_validate_json(intent.model_dump_json()) == intent
        )
        assert intent.configuration.sample_rate_hz == 10_000_000
        assert intent.run_duration_seconds == 300
    assert 450 < sum(single_rx_for_operation(str(i), "serial") for i in range(1000)) < 550


def test_plan_preserves_physical_receiver_and_native_rate_geometry():
    for index in range(8):
        intent = make_intent(index)
        plan = compile_single_rx_hop_plan(intent)
        assert plan.receiver_ids == intent.configuration.receiver_ids
        assert plan.valid_visit_samples == 1_200_000
        assert plan.nominal_device_sample_count == 3_000_000_000
        assert plan.transition_guard_samples == 10_000
        assert plan.profiles[0].target.if_center_hz == 959_687_500
        assert SingleRxPersistentHopPlanV2.model_validate_json(plan.model_dump_json()) == plan


def test_historical_contracts_reject_new_profile_bytes():
    intent = make_intent()
    for legacy_type, value in (
        (ScheduledScannerRunIntentV1, intent),
        (ScannerConfigurationV3, intent.configuration),
        (PersistentHopPlanV1, compile_single_rx_hop_plan(intent)),
    ):
        with pytest.raises(ValidationError):
            legacy_type.model_validate_json(value.model_dump_json())


@pytest.mark.parametrize("receivers", [[], [0, 1], [True], [False], [2], ["1"]])
def test_invalid_physical_receiver_is_rejected(receivers):
    intent = make_intent()
    for cls, value in (
        (SingleRxScannerConfigurationV4, intent.configuration),
        (SingleRxPersistentHopPlanV2, compile_single_rx_hop_plan(intent)),
    ):
        document = value.model_dump()
        document["receiver_ids"] = receivers
        with pytest.raises(ValidationError):
            cls.model_validate(document)


def test_receiver_tampering_invalidates_the_bound_intent():
    intent = make_intent()
    document = intent.model_dump()
    document["configuration"]["receiver_ids"] = [1 - intent.configuration.receiver_ids[0]]
    with pytest.raises(ValidationError, match="choice disagrees"):
        SingleRxScheduledScannerIntentV2.model_validate(document)
