from __future__ import annotations

from dataclasses import dataclass, replace
import inspect
from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from native_tradeoff_detector import (  # noqa: E402
    CacheKey,
    NativeTradeoffDetector,
)


RATE = 2_500_000


@dataclass(frozen=True)
class Window:
    probe_index: int
    probe_start_sample: int


@dataclass(frozen=True)
class Screen:
    receiver: int
    windows: tuple[Window, ...]


@dataclass(frozen=True)
class Observation:
    receiver: int
    probe_index: int
    probe_start_sample: int
    local_epoch_sample: float
    acquired_cfo_hz: float = 300_000.0
    tracking_cfo_hz: float = 100_000.0
    margin: float = 0.2
    fractional_complete: bool = True
    supported: bool = True
    fitted: bool = True
    candidate_index: int = 0
    exact_score: float = 0.3
    control_score: float = 0.1
    support_frames: int = 14
    valid_bounds: bool = True
    status: int = 0

    @property
    def dwell_epoch_sample(self) -> float:
        return self.probe_start_sample + self.local_epoch_sample


def key(
    receiver: int = 0,
    *,
    channel: int = 1,
    continuity: str = "session-a",
    tuning: str = "tune-a",
) -> CacheKey:
    return CacheKey(
        continuity,
        receiver,
        channel,
        "lower",
        RATE,
        tuning,
        "cal-a",
    )


def probe_start(index: int, rate: int = RATE) -> int:
    return index * rate // 100


def phase_local(
    start_counter: int,
    phase_counter: int,
    probe_index: int,
    *,
    fraction: float = 0.25,
    rate: int = RATE,
) -> float:
    start = probe_start(probe_index, rate)
    integer = ((phase_counter - start_counter - start) * 750 % rate) / 750
    return (integer + fraction) % (rate / 750)


def blind_pair(
    start_counter: int,
    phase_counter: int,
    *,
    receiver: int = 0,
    fraction: float = 0.25,
    acquired_cfo_hz: float = 300_000.0,
    tracking_cfo_hz: float = 100_000.0,
) -> tuple[Observation, Observation]:
    return tuple(
        Observation(
            receiver,
            index,
            probe_start(index),
            phase_local(
                start_counter,
                phase_counter,
                index,
                fraction=fraction,
            ),
            acquired_cfo_hz=acquired_cfo_hz,
            tracking_cfo_hz=tracking_cfo_hz,
        )
        for index in (0, 2)
    )


def raw(
    k: CacheKey,
    *,
    blind=(),
    guided_mode: str = "good",
    guided_tracking_cfo_hz: float | None = None,
    guided_status: int = 0,
    guided_supported: bool = True,
) -> dict:
    return {
        "key": k,
        "screen": Screen(
            k.receiver,
            tuple(Window(index, probe_start(index, k.rate_hz)) for index in range(11)),
        ),
        "blind": tuple(blind),
        "guided_mode": guided_mode,
        "guided_tracking_cfo_hz": guided_tracking_cfo_hz,
        "guided_status": guided_status,
        "guided_supported": guided_supported,
    }


class FakeEngine:
    def __init__(self) -> None:
        self.screen_calls = 0
        self.blind_calls = 0
        self.guided_calls: list[dict] = []

    def screen(self, values, *, receiver):
        self.screen_calls += 1
        assert receiver == values["key"].receiver
        return values["screen"]

    def blind(self, values, *, receiver, screen):
        self.blind_calls += 1
        assert receiver == values["key"].receiver
        assert screen is values["screen"]
        return values["blind"]

    def guided(
        self,
        values,
        *,
        receiver,
        probe_index,
        predicted_local_epoch_sample,
        scoring_cfo_hz,
        expected_physical_cfo_hz,
    ):
        call = {
            "receiver": receiver,
            "probe_index": probe_index,
            "predicted_local_epoch_sample": predicted_local_epoch_sample,
            "scoring_cfo_hz": scoring_cfo_hz,
            "expected_physical_cfo_hz": expected_physical_cfo_hz,
        }
        self.guided_calls.append(call)
        if values["guided_mode"] == "none":
            return None
        tracking = values["guided_tracking_cfo_hz"]
        if tracking is None:
            tracking = expected_physical_cfo_hz
        return Observation(
            receiver,
            probe_index,
            probe_start(probe_index, values["key"].rate_hz),
            predicted_local_epoch_sample,
            acquired_cfo_hz=scoring_cfo_hz,
            tracking_cfo_hz=tracking,
            margin=-0.1 if values["guided_mode"] == "negative" else 0.2,
            fitted=False,
            status=values["guided_status"],
            supported=values["guided_supported"],
        )


def seed(
    detector: NativeTradeoffDetector,
    engine: FakeEngine,
    k: CacheKey,
    *,
    start_counter: int = 2**55 + 17,
    visit_index: int = 1,
    phase_offset: int = 317,
) -> tuple[int, object]:
    phase = start_counter + phase_offset
    result = detector.process(
        raw(k, blind=blind_pair(start_counter, phase, receiver=k.receiver)),
        k,
        start_counter=start_counter,
        visit_index=visit_index,
    )
    assert result.active and result.route == "blind_cold"
    return phase, result


def test_cold_blind_maps_large_counter_and_exposes_complete_cost_inventory() -> None:
    engine = FakeEngine()
    detector = NativeTradeoffDetector(engine)
    k = key()
    start = 2**55 + 17
    _, result = seed(detector, engine, k, start_counter=start)
    assert result.pair is not None and result.state_established
    assert result.pair.first.source_epoch_counter == start + 317
    assert result.pair.first.source_epoch_fraction == pytest.approx(0.25)
    assert result.screened_probe_count == 11
    assert result.blind_probe_count == 11
    assert result.guided_probe_count == 0
    assert result.proposal_count == 2
    assert result.scoring_count == 11


def test_guided_hit_uses_only_prior_probe_indices_and_never_calls_rank() -> None:
    engine = FakeEngine()
    detector = NativeTradeoffDetector(engine)
    k = key()
    start = 2**55 + 17
    seed(detector, engine, k, start_counter=start)
    before = detector.states[k]
    result = detector.process(
        raw(k),
        k,
        start_counter=start + 300_000,
        visit_index=2,
    )
    after = detector.states[k]
    assert result.active and result.route == "guided"
    assert [item["probe_index"] for item in engine.guided_calls] == [0, 2]
    assert engine.screen_calls == engine.blind_calls == 1
    assert result.screened_probe_count == result.blind_probe_count == 0
    assert result.guided_probe_count == result.scoring_count == 2
    assert after.anchors == before.anchors
    assert after.timing_rate_samples_per_s == before.timing_rate_samples_per_s
    assert after.cfo_rate_hz_per_s == before.cfo_rate_hz_per_s
    assert after.guided_accepts_since_discovery == 1


@pytest.mark.parametrize(
    ("changes", "attempts"),
    [
        ({"guided_mode": "none"}, 1),
        ({"guided_supported": False}, 1),
        ({"guided_status": 7}, 1),
        ({"guided_mode": "negative"}, 1),
    ],
)
def test_invalid_guided_evidence_fails_open_once_and_blind_negative_clears_state(
    changes, attempts
) -> None:
    engine = FakeEngine()
    detector = NativeTradeoffDetector(engine)
    k = key()
    start = 1_000_000
    seed(detector, engine, k, start_counter=start)
    result = detector.process(
        raw(k, **changes),
        k,
        start_counter=start + 300_000,
        visit_index=2,
    )
    assert not result.active and result.route == "blind_guided_failure"
    assert result.guided_probe_count == attempts
    assert engine.blind_calls == 2
    assert k not in detector.states


def test_physical_cfo_is_measured_not_echoed_and_wrong_track_falls_open() -> None:
    engine = FakeEngine()
    detector = NativeTradeoffDetector(engine)
    k = key()
    start = 1_000_000
    seed(detector, engine, k, start_counter=start)
    expected = detector._prediction(
        k, detector.states[k], detector.states[k].anchors[0], start + 300_000
    ).physical_cfo_hz
    fixed_measurement = expected + 9_000.0
    result = detector.process(
        raw(k, guided_tracking_cfo_hz=fixed_measurement),
        k,
        start_counter=start + 300_000,
        visit_index=2,
    )
    assert not result.active and result.route == "blind_guided_failure"
    assert engine.guided_calls[0]["expected_physical_cfo_hz"] == pytest.approx(expected)
    # The fake measurement ignored that expectation and the controller rejected it.
    assert fixed_measurement != engine.guided_calls[0]["expected_physical_cfo_hz"]


def test_failed_guided_can_establish_a_fresh_blind_track() -> None:
    engine = FakeEngine()
    detector = NativeTradeoffDetector(engine)
    k = key()
    start = 1_000_000
    seed(detector, engine, k, start_counter=start)
    second_start = start + 300_000
    replacement_phase = second_start + 811
    result = detector.process(
        raw(
            k,
            guided_mode="none",
            blind=blind_pair(
                second_start,
                replacement_phase,
                tracking_cfo_hz=120_000.0,
            ),
        ),
        k,
        start_counter=second_start,
        visit_index=2,
    )
    assert result.active and result.route == "blind_guided_failure"
    assert detector.states[k].physical_cfo_hz == 120_000.0
    assert detector.states[k].guided_accepts_since_discovery == 0


def test_metadata_keys_are_isolated_and_snapshot_replay_is_exact() -> None:
    engine = FakeEngine()
    detector = NativeTradeoffDetector(engine)
    start = 2**55
    keys = (key(0), key(1), key(0, channel=2), key(0, continuity="session-b"))
    for current in keys:
        phase = start + 317
        detector.process(
            raw(
                current,
                blind=blind_pair(start, phase, receiver=current.receiver),
            ),
            current,
            start_counter=start,
            visit_index=1,
        )
    assert len(detector.states) == len(keys)

    snapshot = detector.snapshot()
    next_start = start + 300_000
    result1 = detector.process(
        raw(keys[0]), keys[0], start_counter=next_start, visit_index=2
    )
    detector.restore(snapshot)
    result2 = detector.process(
        raw(keys[0]), keys[0], start_counter=next_start, visit_index=2
    )
    assert result1 == result2


def test_expiry_force_and_forced_next_after_31_guided_accepts() -> None:
    engine = FakeEngine()
    detector = NativeTradeoffDetector(engine)
    k = key()
    start = 10_000_000
    seed(detector, engine, k, start_counter=start)
    forced_start = start + 100_000
    forced = detector.process(
        raw(k, blind=blind_pair(forced_start, forced_start + 317)),
        k,
        start_counter=forced_start,
        visit_index=2,
        force_discovery=True,
    )
    assert forced.route == "blind_forced"

    detector.clear()
    seed(detector, engine, k, start_counter=start)
    for visit in range(2, 33):
        result = detector.process(
            raw(k),
            k,
            start_counter=start + (visit - 1) * 100_000,
            visit_index=visit,
        )
        assert result.route == "guided"
    periodic_start = start + 32 * 100_000
    periodic = detector.process(
        raw(k, blind=blind_pair(periodic_start, periodic_start + 317)),
        k,
        start_counter=periodic_start,
        visit_index=33,
    )
    assert periodic.route == "blind_periodic"

    detector.clear()
    seed(detector, engine, k, start_counter=start)
    expired_start = start + 2 * RATE + 1
    expired = detector.process(
        raw(k, blind=blind_pair(expired_start, expired_start + 317)),
        k,
        start_counter=expired_start,
        visit_index=2,
    )
    assert expired.route == "blind_expired"


def test_only_blind_pairs_fit_slopes_and_new_trajectory_resets_them() -> None:
    engine = FakeEngine()
    detector = NativeTradeoffDetector(engine)
    k = key()
    start = 1_000_000
    seed(detector, engine, k, start_counter=start, phase_offset=100)

    second_start = start + 300_000
    detector.process(
        raw(
            k,
            blind=blind_pair(
                second_start,
                second_start + 101,
                tracking_cfo_hz=100_120.0,
            ),
        ),
        k,
        start_counter=second_start,
        visit_index=2,
        force_discovery=True,
    )
    fitted = detector.states[k]
    assert fitted.timing_rate_samples_per_s != 0.0
    assert fitted.cfo_rate_hz_per_s != 0.0

    guided_start = second_start + 100_000
    detector.process(
        raw(k), k, start_counter=guided_start, visit_index=3
    )
    guided = detector.states[k]
    assert guided.timing_rate_samples_per_s == fitted.timing_rate_samples_per_s
    assert guided.cfo_rate_hz_per_s == fitted.cfo_rate_hz_per_s

    third_start = guided_start + 100_000
    detector.process(
        raw(
            k,
            blind=blind_pair(
                third_start,
                third_start + 1_100,
                tracking_cfo_hz=250_000.0,
            ),
        ),
        k,
        start_counter=third_start,
        visit_index=4,
        force_discovery=True,
    )
    reset = detector.states[k]
    assert reset.timing_rate_samples_per_s == 0.0
    assert reset.cfo_rate_hz_per_s == 0.0


def test_single_probe_and_invalid_support_cannot_activate() -> None:
    engine = FakeEngine()
    detector = NativeTradeoffDetector(engine)
    k = key()
    start = 1_000_000
    one = blind_pair(start, start + 317)[0]
    result = detector.process(
        raw(k, blind=(one,)), k, start_counter=start, visit_index=1
    )
    assert not result.active and k not in detector.states

    unsupported = replace(one, probe_index=2, probe_start_sample=probe_start(2), support_frames=1)
    result = detector.process(
        raw(k, blind=(one, unsupported)),
        k,
        start_counter=start + 300_000,
        visit_index=2,
    )
    assert not result.active


def test_public_api_has_no_oracle_or_reference_input() -> None:
    parameters = inspect.signature(NativeTradeoffDetector.process).parameters
    assert "reference" not in parameters and "oracle" not in parameters
    assert set(parameters) == {
        "self",
        "raw",
        "key",
        "start_counter",
        "visit_index",
        "force_discovery",
    }
