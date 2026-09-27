from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from native_rescue_detector import (  # noqa: E402
    CONFIRMATION_PROBE,
    MAXIMUM_CANDIDATES,
    CacheKey,
    NativeTradeoffDecision,
    NativeTradeoffDetector,
    SameRxRescueDetector,
)


RATE = 2_500_000
PERIOD = RATE / 750.0


def key(receiver: int, *, rate: int = RATE) -> CacheKey:
    return CacheKey("session", receiver, 1, "lower", rate, "tune", f"cal-{receiver}")


def inactive(receiver: int) -> NativeTradeoffDecision:
    return NativeTradeoffDecision(
        False, "blind_cold", f"inactive-{receiver}", None, 11, 0, 11, 0, 11, False
    )


def active(receiver: int) -> NativeTradeoffDecision:
    return NativeTradeoffDecision(
        True, "blind_cold", f"active-{receiver}", None, 11, 0, 11, 2, 11, True
    )


class StubPrimary(NativeTradeoffDetector):
    def __init__(self, engine, decisions):
        self.engine = engine
        self.decisions = tuple(decisions)
        self.calls = []
        self.state = 0

    def process(self, raw, cache_key, **kwargs):
        self.calls.append((cache_key.receiver, kwargs, raw))
        self.state += 1
        return self.decisions[cache_key.receiver]

    def clear(self):
        self.state = 0

    def snapshot(self):
        return self.state

    def restore(self, snapshot):
        self.state = snapshot


def candidate(rank: int, epoch: int, cfo: float):
    return SimpleNamespace(rank=rank, refined_epoch_sample=epoch, absolute_cfo_hz=cfo)


def python_score(margin: float, tracking: float):
    return SimpleNamespace(
        exact_score=0.2 + margin,
        control_score=0.2,
        margin=margin,
        tracking_cfo_hz=tracking,
    )


def observation(
    receiver: int,
    probe: int,
    *,
    epoch: float = 123.25,
    scoring: float = 100_000.0,
    physical: float = 105_000.0,
    margin: float = 0.04,
    support: int = 15,
    status: int = 0,
    bounds: bool = True,
):
    start = probe * RATE // 100
    return SimpleNamespace(
        receiver=receiver,
        probe_index=probe,
        probe_start_sample=start,
        local_epoch_sample=epoch,
        dwell_epoch_sample=start + epoch,
        acquired_cfo_hz=scoring,
        tracking_cfo_hz=physical,
        margin=margin,
        exact_score=0.3 + margin,
        control_score=0.3,
        support_frames=support,
        fractional_complete=True,
        supported=True,
        fitted=False,
        valid_bounds=bounds,
        status=status,
        candidate_index=0,
    )


class StubEngine:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.guided_calls = []

    def guided(self, raw, **kwargs):
        self.guided_calls.append((raw, kwargs))
        return self.replies.pop(0)


class StubAcquisition:
    def __init__(self, candidates):
        self.output = tuple(candidates)
        self.calls = []

    def __call__(self, samples, rate, calibration, **kwargs):
        self.calls.append((samples.copy(), rate, calibration, kwargs))
        return SimpleNamespace(candidates=self.output)


class StubScorer:
    def __init__(self, by_epoch):
        self.by_epoch = dict(by_epoch)
        self.calls = []

    def __call__(self, samples, rate, **kwargs):
        self.calls.append((samples.copy(), rate, kwargs))
        return self.by_epoch[kwargs["epoch_sample"]]


def raw(rate: int = RATE) -> np.ndarray:
    values = np.zeros((rate * 120 // 1_000, 2, 2), dtype=np.int16)
    values[: rate // 50, 0, 0] = 11
    values[: rate // 50, 1, 0] = 22
    return values


def detector(decisions, engine, acquisition, scorer):
    primary = StubPrimary(engine, decisions)
    return SameRxRescueDetector(
        primary, engine, acquisition=acquisition, scorer=scorer
    ), primary


def test_active_primary_decisions_are_preserved_without_rescue():
    engine = StubEngine()
    acquire = StubAcquisition(())
    score = StubScorer({})
    tested, primary = detector((active(0), active(1)), engine, acquire, score)
    values = raw()
    before = values.copy()

    result = tested.process(values, (key(0), key(1)), start_counter=1000, visit_index=0)

    assert result.decisions == result.primary_decisions == (active(0), active(1))
    assert result.rescue_receiver is None
    assert result.rescue_acquisition_count == 0
    assert [item[0] for item in primary.calls] == [0, 1]
    assert primary.state == 2
    assert not acquire.calls and not engine.guided_calls
    np.testing.assert_array_equal(values, before)


def test_rank_order_dual_native_measurement_and_distinct_cfos():
    candidates = (
        candidate(0, 90, 10_000.0),
        candidate(1, 100, 20_000.0),
        candidate(2, 123, 100_000.0),
    )
    acquire = StubAcquisition(candidates)
    score = StubScorer({
        90: python_score(0.01, 11_000.0),
        100: python_score(0.03, 21_500.0),
        123: python_score(0.04, 105_000.0),
    })
    seed = observation(1, 0, epoch=123.25, scoring=100_000.0, physical=105_500.0)
    confirmation = observation(
        1, CONFIRMATION_PROBE, epoch=123.5,
        scoring=100_000.0, physical=106_000.0,
    )
    engine = StubEngine((None, seed, confirmation))
    tested, primary = detector((active(0), inactive(1)), engine, acquire, score)
    values = raw()
    before = values.copy()

    result = tested.process(values, (key(0), key(1)), start_counter=1_000_000, visit_index=7)

    assert result.decisions[0] is result.primary_decisions[0]
    rescued = result.decisions[1]
    assert rescued.active and rescued.route == "rescue_probe0_probe2"
    assert rescued.pair.first.local_epoch_sample == 123.25
    assert rescued.pair.second.local_epoch_sample == 123.5
    assert rescued.pair.first.acquired_cfo_hz == 100_000.0
    assert rescued.pair.second.acquired_cfo_hz == 100_000.0
    assert not rescued.state_established
    assert result.rescue_receiver == 1
    assert (
        result.rescue_candidate_count,
        result.rescue_candidate_score_count,
        result.rescue_seed_guided_count,
        result.rescue_confirmation_guided_count,
    ) == (3, 3, 2, 1)
    assert result.total_scoring_count == result.primary_scoring_count + 6
    assert [event.reason for event in result.rescue_events] == [
        "python_margin_failed", "native_seed_unavailable", "accepted"
    ]
    assert [call[1]["probe_index"] for call in engine.guided_calls] == [0, 0, 2]
    rank2_seed = engine.guided_calls[1][1]
    assert rank2_seed["scoring_cfo_hz"] == 100_000.0
    assert rank2_seed["expected_physical_cfo_hz"] == 105_000.0
    rank2_confirmation = engine.guided_calls[2][1]
    assert rank2_confirmation["scoring_cfo_hz"] == 100_000.0
    assert rank2_confirmation["expected_physical_cfo_hz"] == 105_000.0
    assert rank2_confirmation["predicted_local_epoch_sample"] == pytest.approx(123.0)
    assert acquire.calls[0][0][0] == 22 + 0j
    config = acquire.calls[0][3]["config"]
    assert config.retained_candidate_count == MAXIMUM_CANDIDATES
    assert config.candidate_epoch_separation_samples == 5
    assert config.candidate_cfo_separation_hz == 10_000.0
    assert [item[0] for item in primary.calls] == [0, 1]
    np.testing.assert_array_equal(values, before)


def test_both_inactive_always_selects_rx0_and_does_not_inject_state():
    acquire = StubAcquisition(())
    engine = StubEngine()
    tested, primary = detector((inactive(0), inactive(1)), engine, acquire, StubScorer({}))
    result = tested.process(raw(), (key(0), key(1)), start_counter=0, visit_index=0)

    assert result.rescue_receiver == 0
    assert result.decisions == result.primary_decisions
    assert result.rescue_acquisition_count == 1
    assert primary.state == 2
    assert acquire.calls[0][0][0] == 11 + 0j


@pytest.mark.parametrize(
    ("confirmation", "reason"),
    [
        (observation(0, 2, margin=0.024), "native_pair_failed"),
        (observation(0, 2, support=1), "native_pair_failed"),
        (observation(0, 2, status=1), "native_pair_failed"),
        (observation(0, 2, bounds=False), "native_pair_failed"),
        (observation(0, 2, epoch=140.0), "native_pair_failed"),
        (observation(0, 2, physical=113_001.0), "native_pair_failed"),
    ],
)
def test_confirmation_requires_every_native_and_identity_gate(confirmation, reason):
    acquire = StubAcquisition((candidate(0, 123, 100_000.0),))
    score = StubScorer({123: python_score(0.04, 105_000.0)})
    seed = observation(0, 0, epoch=123.0, physical=105_000.0)
    engine = StubEngine((seed, confirmation))
    tested, _ = detector((inactive(0), active(1)), engine, acquire, score)

    result = tested.process(raw(), (key(0), key(1)), start_counter=0, visit_index=0)

    assert not result.decisions[0].active
    assert result.decisions[1].active
    assert result.rescue_events[-1].reason == reason
    assert result.rescue_confirmation_guided_count == 1


@pytest.mark.parametrize(
    "seed",
    [
        observation(0, 0, margin=0.024),
        observation(0, 0, physical=113_001.0),
        observation(0, 0, epoch=140.0),
        observation(0, 0, scoring=100_000.000_001),
    ],
)
def test_seed_must_match_python_conditioned_hypothesis(seed):
    acquire = StubAcquisition((candidate(0, 123, 100_000.0),))
    score = StubScorer({123: python_score(0.04, 105_000.0)})
    engine = StubEngine((seed,))
    tested, _ = detector((inactive(0), active(1)), engine, acquire, score)

    result = tested.process(raw(), (key(0), key(1)), start_counter=0, visit_index=0)

    assert not result.decisions[0].active
    assert result.rescue_events[0].reason == "native_seed_failed"
    assert result.rescue_confirmation_guided_count == 0


def test_confirmation_must_also_match_original_python_physical_cfo():
    acquire = StubAcquisition((candidate(0, 123, 100_000.0),))
    score = StubScorer({123: python_score(0.04, 105_000.0)})
    # Each native point is within 8 kHz of its neighbor, but the confirmation
    # has accumulated too much innovation from the original Python seed.
    seed = observation(0, 0, epoch=123.0, physical=112_999.0)
    confirmation = observation(0, 2, epoch=123.0, physical=120_998.0)
    engine = StubEngine((seed, confirmation))
    tested, _ = detector((inactive(0), active(1)), engine, acquire, score)

    result = tested.process(raw(), (key(0), key(1)), start_counter=0, visit_index=0)

    assert not result.decisions[0].active
    assert result.rescue_events[0].reason == "native_pair_failed"


def test_confirmation_must_return_original_python_scoring_cfo():
    acquire = StubAcquisition((candidate(0, 123, 100_000.0),))
    score = StubScorer({123: python_score(0.04, 105_000.0)})
    seed = observation(0, 0, epoch=123.0, scoring=100_000.0, physical=105_000.0)
    confirmation = observation(
        0, 2, epoch=123.0, scoring=100_000.000_001, physical=105_000.0
    )
    engine = StubEngine((seed, confirmation))
    tested, _ = detector((inactive(0), active(1)), engine, acquire, score)

    result = tested.process(raw(), (key(0), key(1)), start_counter=0, visit_index=0)

    assert not result.decisions[0].active
    assert result.rescue_events[0].reason == "native_pair_failed"


def test_guided_observation_must_report_the_requested_probe():
    acquire = StubAcquisition((candidate(0, 123, 100_000.0),))
    score = StubScorer({123: python_score(0.04, 105_000.0)})
    engine = StubEngine((observation(0, 2),))
    tested, _ = detector((inactive(0), active(1)), engine, acquire, score)

    with pytest.raises(ValueError, match="identity disagrees"):
        tested.process(raw(), (key(0), key(1)), start_counter=0, visit_index=0)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_timing_transport_uses_physical_frame_modulo(rate):
    period = rate / 750.0
    near_seam = period - 0.125
    transported = SameRxRescueDetector._transport_epoch(rate, near_seam, 0, 2)
    assert transported == pytest.approx(near_seam, abs=1e-10)
    probe_three = SameRxRescueDetector._transport_epoch(rate, near_seam, 0, 3)
    expected = (((near_seam - 3 * rate // 100) * 750) % rate) / 750
    assert probe_three == pytest.approx(expected, abs=1e-10)


def test_snapshot_restore_and_clear_delegate_only_to_primary():
    engine = StubEngine()
    tested, primary = detector((active(0), active(1)), engine, StubAcquisition(()), StubScorer({}))
    assert tested.snapshot() == 0
    tested.restore(4)
    assert primary.state == 4
    tested.clear()
    assert primary.state == 0


def test_integrity_exception_restores_both_receiver_primary_state():
    engine = StubEngine()
    acquire = StubAcquisition((candidate(1, 1, 0.0),))
    tested, primary = detector((inactive(0), active(1)), engine, acquire, StubScorer({}))

    with pytest.raises(ValueError, match="rank order"):
        tested.process(raw(), (key(0), key(1)), start_counter=0, visit_index=0)

    assert primary.state == 0


def test_input_contract_candidate_budget_and_rank_order_fail_closed():
    engine = StubEngine()
    acquire = StubAcquisition(tuple(candidate(index, index, 0.0) for index in range(11)))
    tested, _ = detector((inactive(0), active(1)), engine, acquire, StubScorer({}))
    with pytest.raises(ValueError, match="candidate budget"):
        tested.process(raw(), (key(0), key(1)), start_counter=0, visit_index=0)

    acquire.output = (candidate(1, 1, 0.0),)
    with pytest.raises(ValueError, match="rank order"):
        tested.process(raw(), (key(0), key(1)), start_counter=0, visit_index=1)

    with pytest.raises(ValueError, match="ordered RX0 then RX1"):
        tested.process(raw(), (key(1), key(0)), start_counter=0, visit_index=2)
    with pytest.raises(ValueError, match="C-contiguous"):
        tested.process(raw()[::2], (key(0), key(1)), start_counter=0, visit_index=3)
