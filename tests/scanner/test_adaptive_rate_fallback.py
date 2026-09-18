from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from leo.scanner.adaptive_rate_fallback import (
    AdaptiveRateAttempt,
    decide_rate_fallback,
    initial_rate_attempt,
    successful_rate_outcome,
)

SLOT = datetime(2026, 9, 18, 12, 10, tzinfo=UTC)


def _fallback(attempt, *, remaining=315.0, retryable=True):
    return decide_rate_fallback(
        attempt,
        failure_retryable=retryable,
        now_utc=SLOT - timedelta(seconds=remaining),
        next_slot_utc=SLOT,
    )


def test_20m_falls_back_to_15m_then_10m_without_changing_requested_rate():
    first = initial_rate_attempt(20_000_000)
    second = _fallback(first).next_attempt
    assert second == AdaptiveRateAttempt(20_000_000, 15_000_000, 2)
    assert second is not None and second.is_fallback
    third = _fallback(second).next_attempt
    assert third == AdaptiveRateAttempt(20_000_000, 10_000_000, 3)
    assert _fallback(third).disposition == "exhausted"


def test_15m_falls_back_directly_to_10m_and_10m_is_exhausted():
    decision = _fallback(initial_rate_attempt(15_000_000))
    assert decision.next_attempt == AdaptiveRateAttempt(15_000_000, 10_000_000, 2)
    assert _fallback(initial_rate_attempt(10_000_000)).disposition == "exhausted"


def test_retry_must_fit_capture_and_setup_margin_before_next_slot():
    attempt = initial_rate_attempt(20_000_000)
    assert _fallback(attempt, remaining=315.0).disposition == "retry"
    blocked = _fallback(attempt, remaining=314.999)
    assert blocked.disposition == "deadline"
    assert blocked.next_attempt is None
    assert blocked.required_seconds == 315.0


def test_non_retryable_failure_never_selects_a_fallback():
    decision = _fallback(initial_rate_attempt(20_000_000), retryable=False)
    assert decision.disposition == "not_retryable"
    assert decision.next_attempt is None


def test_success_records_requested_and_actual_acquired_rate_separately():
    fallback = AdaptiveRateAttempt(20_000_000, 15_000_000, 2)
    outcome = successful_rate_outcome(fallback)
    assert outcome.requested_rate_hz == 20_000_000
    assert outcome.acquired_rate_hz == 15_000_000
    assert outcome.attempt_ordinal == 2


def test_impossible_attempt_sequence_and_naive_clocks_fail_closed():
    with pytest.raises(ValueError, match="fallback sequence"):
        AdaptiveRateAttempt(20_000_000, 10_000_000, 2)
    with pytest.raises(ValueError, match="timezone-aware"):
        decide_rate_fallback(
            initial_rate_attempt(20_000_000),
            failure_retryable=True,
            now_utc=datetime(2026, 9, 18, 12, 0),
            next_slot_utc=SLOT,
        )
