from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
RAW_RESCUE = HERE.parent / "native_rescue"
for entry in (str(HERE), str(RAW_RESCUE)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from native_rescue_detector import CacheKey, NativeTradeoffDecision, NativeTradeoffDetector  # noqa: E402
from tone_conditioned_rescue_detector import ToneConditionedSameRxRescueDetector  # noqa: E402


RATE = 2_500_000


def key(receiver: int) -> CacheKey:
    return CacheKey("session", receiver, 1, "lower", RATE, "tune", f"cal-{receiver}")


def decision(receiver: int, active: bool) -> NativeTradeoffDecision:
    return NativeTradeoffDecision(
        active, "blind_cold", f"rx{receiver}", None, 11, 0, 11,
        2 if active else 0, 11, active,
    )


class Primary(NativeTradeoffDetector):
    def __init__(self, engine, outputs):
        self.engine = engine
        self.outputs = tuple(outputs)
        self.calls = []
        self.state = 0

    def process(self, raw, cache_key, **kwargs):
        self.calls.append((cache_key.receiver, kwargs))
        self.state += 1
        return self.outputs[cache_key.receiver]

    def clear(self):
        self.state = 0

    def snapshot(self):
        return self.state

    def restore(self, snapshot):
        self.state = snapshot


def observation(probe: int, *, nuisance="tone-fit"):
    start = probe * RATE // 100
    return SimpleNamespace(
        receiver=0, probe_index=probe, probe_start_sample=start,
        local_epoch_sample=123.25, dwell_epoch_sample=start + 123.25,
        acquired_cfo_hz=100_000.0, tracking_cfo_hz=101_000.0,
        margin=.04, exact_score=.30, control_score=.26,
        support_frames=14, fractional_complete=True, supported=True,
        fitted=False, valid_bounds=True, status=0, candidate_index=0,
        nuisance_receipt={"kind": nuisance, "removed_tones": 1},
    )


class ToneEngine:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.calls = []

    def guided(self, raw, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


class Acquisition:
    def __call__(self, *_args, **_kwargs):
        return SimpleNamespace(candidates=(SimpleNamespace(
            rank=0, refined_epoch_sample=123, absolute_cfo_hz=100_000.0,
        ),))


def score(*_args, **_kwargs):
    return SimpleNamespace(
        exact_score=.31, control_score=.27, margin=.04,
        tracking_cfo_hz=101_000.0,
    )


def raw():
    return np.zeros((RATE * 120 // 1000, 2, 2), dtype="<i2")


def test_distinct_ports_preserve_primary_and_capture_full_nuisance_receipts():
    primary_engine = object()
    primary_outputs = (decision(0, False), decision(1, True))
    primary = Primary(primary_engine, primary_outputs)
    tone = ToneEngine((observation(0), observation(2, nuisance="confirm-fit")))
    detector = ToneConditionedSameRxRescueDetector(
        primary, tone, acquisition=Acquisition(), scorer=score,
    )

    result = detector.process(raw(), (key(0), key(1)), start_counter=2**55, visit_index=3)

    assert [call[0] for call in primary.calls] == [0, 1]
    assert result.primary_decisions == primary_outputs
    assert result.decisions[1] is primary_outputs[1]
    assert result.decisions[0].route == "rescue_probe0_probe2"
    assert len(result.tone_guided_calls) == 2
    assert result.tone_guided_calls[0].observation.nuisance_receipt["removed_tones"] == 1
    assert result.tone_guided_calls[1].observation.nuisance_receipt["kind"] == "confirm-fit"
    assert result.tone_guided_calls[0].expected_physical_cfo_hz == 101_000.0
    assert result.total_scoring_count == result.primary_scoring_count + 3


def test_call_receipts_reset_each_visit_and_none_is_preserved():
    primary = Primary(object(), (decision(0, False), decision(1, True)))
    tone = ToneEngine((None, None))
    detector = ToneConditionedSameRxRescueDetector(
        primary, tone, acquisition=Acquisition(), scorer=score,
    )
    first = detector.process(raw(), (key(0), key(1)), start_counter=0, visit_index=0)
    second = detector.process(raw(), (key(0), key(1)), start_counter=1, visit_index=1)
    assert len(first.tone_guided_calls) == len(second.tone_guided_calls) == 1
    assert first.tone_guided_calls[0].observation is None
    assert second.tone_guided_calls[0].observation is None


def test_constructor_rejects_shared_or_invalid_rescue_port():
    engine = ToneEngine()
    primary = Primary(engine, (decision(0, False), decision(1, False)))
    with pytest.raises(ValueError, match="distinct fixed"):
        ToneConditionedSameRxRescueDetector(primary, engine)
    with pytest.raises(ValueError, match="distinct fixed"):
        ToneConditionedSameRxRescueDetector(primary, object())


def test_primary_state_rolls_back_when_tone_port_raises():
    class Broken:
        def guided(self, *_args, **_kwargs):
            raise RuntimeError("broken tone port")

    primary = Primary(object(), (decision(0, False), decision(1, True)))
    detector = ToneConditionedSameRxRescueDetector(
        primary, Broken(), acquisition=Acquisition(), scorer=score,
    )
    with pytest.raises(RuntimeError, match="broken"):
        detector.process(raw(), (key(0), key(1)), start_counter=0, visit_index=0)
    assert primary.state == 0
