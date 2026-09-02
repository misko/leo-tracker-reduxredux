from datetime import UTC, datetime, timedelta

import pytest

from leo.scanner import compile_scheduled_scanner_run_intent_v1


def _compile(scheduled_for: datetime):
    ordinal = int(scheduled_for.timestamp() // 1_200)
    return compile_scheduled_scanner_run_intent_v1(
        operation_key=f"scheduled-scanner:{ordinal}",
        radio_id="radio-a",
        radio_serial="serial-a",
        scheduled_for=scheduled_for,
        interval_seconds=1_200,
        maximum_lateness_seconds=120,
        run_duration_seconds=300,
        dwell_ms=120,
        gain_db=40.0,
        margin_gate=0.025,
        maximum_acquisition_candidates=8,
    )


def test_scanner_schedule_alternates_exactly_across_one_utc_day() -> None:
    start = datetime(2026, 9, 2, tzinfo=UTC)
    intents = tuple(_compile(start + timedelta(minutes=20 * index)) for index in range(72))

    assert [item.configuration.sample_rate_hz for item in intents[:4]] == [
        2_500_000,
        5_000_000,
        2_500_000,
        5_000_000,
    ]
    assert sum(item.configuration.sample_rate_hz == 2_500_000 for item in intents) == 36
    assert sum(item.configuration.sample_rate_hz == 5_000_000 for item in intents) == 36
    assert all(
        item.configuration.bandwidth_hz == item.configuration.sample_rate_hz for item in intents
    )


def test_scanner_schedule_is_digest_stable_for_retry() -> None:
    scheduled_for = datetime(2026, 9, 2, 0, 20, tzinfo=UTC)

    first = _compile(scheduled_for)
    second = _compile(scheduled_for)

    assert first == second
    assert first.intent_digest == second.intent_digest


def test_scanner_schedule_rejects_an_unaligned_slot() -> None:
    with pytest.raises(ValueError, match="aligned"):
        _compile(datetime(2026, 9, 2, 0, 20, 1, tzinfo=UTC))
