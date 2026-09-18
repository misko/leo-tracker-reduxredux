"""Pure deadline policy for retrying a durable adaptive scanner slot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AdaptiveCaptureRate = Literal[10_000_000, 15_000_000, 20_000_000]
FallbackDisposition = Literal["retry", "not_retryable", "deadline", "exhausted"]

_FALLBACK_RATE: dict[AdaptiveCaptureRate, AdaptiveCaptureRate] = {
    20_000_000: 15_000_000,
    15_000_000: 10_000_000,
}


@dataclass(frozen=True, slots=True)
class AdaptiveRateAttempt:
    """One rate attempt beneath an immutable requested scanner slot."""

    requested_rate_hz: AdaptiveCaptureRate
    capture_rate_hz: AdaptiveCaptureRate
    attempt_ordinal: int

    def __post_init__(self) -> None:
        if self.requested_rate_hz not in _FALLBACK_RATE | {10_000_000: 10_000_000}:
            raise ValueError("unsupported requested adaptive capture rate")
        if self.capture_rate_hz not in _FALLBACK_RATE | {10_000_000: 10_000_000}:
            raise ValueError("unsupported adaptive attempt rate")
        if self.attempt_ordinal < 1:
            raise ValueError("adaptive attempt ordinal must be positive")
        allowed = fallback_rate_sequence(self.requested_rate_hz)
        expected_index = self.attempt_ordinal - 1
        if expected_index >= len(allowed) or allowed[expected_index] != self.capture_rate_hz:
            raise ValueError("adaptive attempt rate differs from its requested fallback sequence")

    @property
    def is_fallback(self) -> bool:
        return self.capture_rate_hz != self.requested_rate_hz


@dataclass(frozen=True, slots=True)
class AdaptiveRateOutcome:
    """Successful rate evidence without changing the slot's requested rate."""

    requested_rate_hz: AdaptiveCaptureRate
    acquired_rate_hz: AdaptiveCaptureRate
    attempt_ordinal: int


@dataclass(frozen=True, slots=True)
class AdaptiveFallbackDecision:
    disposition: FallbackDisposition
    next_attempt: AdaptiveRateAttempt | None
    remaining_seconds: float
    required_seconds: float


def fallback_rate_sequence(
    requested_rate_hz: AdaptiveCaptureRate,
) -> tuple[AdaptiveCaptureRate, ...]:
    if requested_rate_hz == 20_000_000:
        return (20_000_000, 15_000_000, 10_000_000)
    if requested_rate_hz == 15_000_000:
        return (15_000_000, 10_000_000)
    if requested_rate_hz == 10_000_000:
        return (10_000_000,)
    raise ValueError("unsupported requested adaptive capture rate")


def initial_rate_attempt(requested_rate_hz: AdaptiveCaptureRate) -> AdaptiveRateAttempt:
    return AdaptiveRateAttempt(
        requested_rate_hz=requested_rate_hz,
        capture_rate_hz=requested_rate_hz,
        attempt_ordinal=1,
    )


def successful_rate_outcome(attempt: AdaptiveRateAttempt) -> AdaptiveRateOutcome:
    return AdaptiveRateOutcome(
        requested_rate_hz=attempt.requested_rate_hz,
        acquired_rate_hz=attempt.capture_rate_hz,
        attempt_ordinal=attempt.attempt_ordinal,
    )


def decide_rate_fallback(
    failed_attempt: AdaptiveRateAttempt,
    *,
    failure_retryable: bool,
    now_utc: datetime,
    next_slot_utc: datetime,
    capture_duration_seconds: float = 300.0,
    setup_margin_seconds: float = 15.0,
) -> AdaptiveFallbackDecision:
    """Choose a lower-rate retry only when it can finish inside this slot."""

    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("fallback decision clock must be timezone-aware")
    if next_slot_utc.tzinfo is None or next_slot_utc.utcoffset() is None:
        raise ValueError("next scanner slot clock must be timezone-aware")
    if capture_duration_seconds <= 0 or setup_margin_seconds < 0:
        raise ValueError("fallback duration must be positive and margin non-negative")

    remaining = (next_slot_utc - now_utc).total_seconds()
    required = capture_duration_seconds + setup_margin_seconds
    if not failure_retryable:
        return AdaptiveFallbackDecision("not_retryable", None, remaining, required)

    sequence = fallback_rate_sequence(failed_attempt.requested_rate_hz)
    next_index = failed_attempt.attempt_ordinal
    if next_index >= len(sequence):
        return AdaptiveFallbackDecision("exhausted", None, remaining, required)
    if remaining < required:
        return AdaptiveFallbackDecision("deadline", None, remaining, required)

    return AdaptiveFallbackDecision(
        "retry",
        AdaptiveRateAttempt(
            requested_rate_hz=failed_attempt.requested_rate_hz,
            capture_rate_hz=sequence[next_index],
            attempt_ordinal=failed_attempt.attempt_ordinal + 1,
        ),
        remaining,
        required,
    )
