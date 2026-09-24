from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.radio.pluto_persistent_hop import _load_plan
from leo.scanner.adaptive_hop import AdaptiveHopPlanV3, AdaptiveHopPolicyV2, AdaptiveHopReceiptV3
from leo.scanner.dual_rx import (
    DUAL_RX_ADAPTIVE_2P5_PROFILE_ID,
    DUAL_RX_EDGE_ADAPTIVE_2P5_PROFILE_ID,
    DUAL_RX_EDGE_ADAPTIVE_10M_PROFILE_ID,
    LEGACY_DUAL_RX_ADAPTIVE_2P5_PROFILE_ID,
    DualRxAdaptive2p5ScheduledScannerIntentV7,
    DualRxAdaptive2p5ScheduledScannerIntentV8,
    DualRxAdaptive2p5ScheduledScannerIntentV9,
    DualRxAdaptive10mScheduledScannerIntentV10,
    _edge_from_random_bit,
    compile_dual_rx_adaptive_2p5_hop_plan,
    compile_dual_rx_adaptive_2p5_scanner_intent,
    compile_dual_rx_adaptive_10m_hop_plan,
    compile_dual_rx_adaptive_10m_scanner_intent,
)
from leo.scanner.schedule import ScheduledScannerRunIntentV1
from leo.scanner.single_rx import parse_scheduled_scanner_intent
from tests.scanner.adaptive_hop_fixtures import receipt_fixture


def make_intent():
    scheduled = datetime(2026, 9, 20, 22, 0, tzinfo=UTC)
    return compile_dual_rx_adaptive_2p5_scanner_intent(
        operation_key="scheduled-scanner:20260920T220000Z",
        radio_id="radio_pluto_19f2",
        radio_serial="10400056f695001322002d0010ad1719f2",
        scheduled_for=scheduled,
        interval_seconds=360.0,
        maximum_lateness_seconds=300.0,
        run_duration_seconds=300.0,
        dwell_ms=120,
        gain_db=40,
        margin_gate=0.025,
        maximum_acquisition_candidates=8,
    )


def make_10m_intent():
    scheduled = datetime(2026, 9, 20, 22, 0, tzinfo=UTC)
    return compile_dual_rx_adaptive_10m_scanner_intent(
        operation_key="scheduled-scanner:20260920T220000Z",
        radio_id="radio_pluto_19f2",
        radio_serial="10400056f695001322002d0010ad1719f2",
        scheduled_for=scheduled,
        interval_seconds=360.0,
        maximum_lateness_seconds=300.0,
        run_duration_seconds=300.0,
        dwell_ms=120,
        gain_db=40,
        margin_gate=0.025,
        maximum_acquisition_candidates=8,
    )


def test_dual_rx_10m_profile_is_new_closed_contract() -> None:
    intent = make_10m_intent()
    assert intent.policy_id == DUAL_RX_EDGE_ADAPTIVE_10M_PROFILE_ID
    assert intent.configuration.receiver_ids == (0, 1)
    assert intent.configuration.sample_rate_hz == 10_000_000
    assert parse_scheduled_scanner_intent(intent.model_dump(mode="json")) == intent
    plan = compile_dual_rx_adaptive_10m_hop_plan(intent)
    assert plan.receiver_ids == (0, 1)
    assert plan.sample_rate_hz == 10_000_000
    assert plan.valid_visit_samples == 1_200_000
    assert plan.nominal_device_sample_count == 3_000_000_000
    upstream = _load_plan(plan)
    assert upstream.sample_rate_hz == 10_000_000
    assert len(upstream.profiles) == 8
    assert (
        DualRxAdaptive10mScheduledScannerIntentV10.model_validate_json(intent.model_dump_json())
        == intent
    )

    adaptive_plan = AdaptiveHopPlanV3(
        geometry=plan,
        policy=AdaptiveHopPolicyV2(mode="adaptive", generation=71, allowed_target_mask=0x0F),
    )
    receipt = receipt_fixture(
        rate=10_000_000,
        count=2,
        plan=adaptive_plan,
        receipt_factory=AdaptiveHopReceiptV3,
    )
    assert receipt.plan.geometry.sample_rate_hz == 10_000_000


def test_dual_rx_profile_is_fixed_to_both_receivers_and_2p5m():
    intent = make_intent()
    assert intent.policy_id == DUAL_RX_EDGE_ADAPTIVE_2P5_PROFILE_ID
    assert intent.configuration.receiver_ids == (0, 1)
    assert intent.configuration.sample_rate_hz == 2_500_000
    assert intent.configuration.bandwidth_hz == 2_500_000
    assert parse_scheduled_scanner_intent(intent.model_dump(mode="json")) == intent
    plan = compile_dual_rx_adaptive_2p5_hop_plan(intent)
    assert plan.receiver_ids == (0, 1)
    assert plan.sample_rate_hz == 2_500_000
    assert plan.valid_visit_samples == 300_000
    assert plan.nominal_device_sample_count == 750_000_000


def test_dual_rx_profile_does_not_validate_as_the_legacy_alternating_contract():
    intent = make_intent()
    assert (
        DualRxAdaptive2p5ScheduledScannerIntentV9.model_validate_json(intent.model_dump_json())
        == intent
    )
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
        DualRxAdaptive2p5ScheduledScannerIntentV9.model_validate(payload)


def test_edge_choice_maps_each_random_bit_and_is_tamper_evident(monkeypatch) -> None:
    assert _edge_from_random_bit(0) == "lower"
    assert _edge_from_random_bit(1) == "upper"
    with pytest.raises(ValueError, match="exact random bit"):
        _edge_from_random_bit(True)

    monkeypatch.setattr("leo.scanner.dual_rx.secrets.randbits", lambda width: 0)
    intent = make_intent()
    assert intent.configuration.selected_edge == "lower"

    payload = intent.model_dump(mode="json")
    payload["configuration"]["selected_edge"] = "upper"
    with pytest.raises(ValidationError, match="digest"):
        DualRxAdaptive2p5ScheduledScannerIntentV9.model_validate(payload)

    monkeypatch.setattr("leo.scanner.dual_rx.secrets.randbits", lambda width: 1)
    assert make_intent().configuration.selected_edge == "upper"


def _as_published_v8_payload() -> dict:
    payload = make_intent().model_dump(mode="json")
    payload.update(schema_version=8, policy_id=DUAL_RX_ADAPTIVE_2P5_PROFILE_ID)
    payload["configuration"].update(
        schema_version=7,
        band_plan_id="starlink-low-ch1-ch4-dual-rx-2p5m-v1",
    )
    payload["configuration"].pop("selected_edge")
    payload["intent_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "intent_digest"}
    )
    return payload


def test_published_six_minute_intent_remains_parseable() -> None:
    payload = _as_published_v8_payload()
    parsed = parse_scheduled_scanner_intent(payload)
    assert isinstance(parsed, DualRxAdaptive2p5ScheduledScannerIntentV8)
    assert parsed.interval_seconds == 360


def test_published_ten_minute_intent_remains_parseable() -> None:
    payload = _as_published_v8_payload()
    payload.update(
        schema_version=7,
        policy_id=LEGACY_DUAL_RX_ADAPTIVE_2P5_PROFILE_ID,
        cadence_ordinal=int(datetime.fromisoformat(payload["scheduled_for"]).timestamp() // 600),
        interval_seconds=600.0,
    )
    payload["intent_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "intent_digest"}
    )

    parsed = parse_scheduled_scanner_intent(payload)

    assert isinstance(parsed, DualRxAdaptive2p5ScheduledScannerIntentV7)
    assert parsed.interval_seconds == 600
