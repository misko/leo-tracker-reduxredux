from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from leo.scanner.dual_rx import (
    DUAL_RX_ADAPTIVE_2P5_PROFILE_ID,
    DualRxAdaptive2p5ScheduledScannerIntentV7,
    compile_dual_rx_adaptive_2p5_scanner_intent,
)
from leo.scanner.schedule import ScheduledScannerRunIntentV1
from leo.scanner.single_rx import parse_scheduled_scanner_intent


def make_intent():
    scheduled = datetime(2026, 9, 20, 22, 0, tzinfo=UTC)
    return compile_dual_rx_adaptive_2p5_scanner_intent(
        operation_key="scheduled-scanner:20260920T220000Z",
        radio_id="radio_pluto_19f2",
        radio_serial="10400056f695001322002d0010ad1719f2",
        scheduled_for=scheduled,
        interval_seconds=600.0,
        maximum_lateness_seconds=300.0,
        run_duration_seconds=300.0,
        dwell_ms=120,
        gain_db=40,
        margin_gate=0.025,
        maximum_acquisition_candidates=8,
    )


def test_dual_rx_profile_is_fixed_to_both_receivers_and_2p5m():
    intent = make_intent()
    assert intent.policy_id == DUAL_RX_ADAPTIVE_2P5_PROFILE_ID
    assert intent.configuration.receiver_ids == (0, 1)
    assert intent.configuration.sample_rate_hz == 2_500_000
    assert intent.configuration.bandwidth_hz == 2_500_000
    assert parse_scheduled_scanner_intent(intent.model_dump(mode="json")) == intent


def test_dual_rx_profile_does_not_validate_as_the_legacy_alternating_contract():
    intent = make_intent()
    assert DualRxAdaptive2p5ScheduledScannerIntentV7.model_validate_json(
        intent.model_dump_json()
    ) == intent
    with pytest.raises(ValidationError):
        ScheduledScannerRunIntentV1.model_validate_json(intent.model_dump_json())


@pytest.mark.parametrize(
    "field,value",
    [
        ("sample_rate_hz", 5_000_000),
        ("bandwidth_hz", 5_000_000),
        ("receiver_ids", [0]),
    ],
)
def test_dual_rx_profile_rejects_rate_or_receiver_drift(field, value):
    payload = make_intent().model_dump(mode="json")
    payload["configuration"][field] = value
    with pytest.raises(ValidationError):
        DualRxAdaptive2p5ScheduledScannerIntentV7.model_validate(payload)
