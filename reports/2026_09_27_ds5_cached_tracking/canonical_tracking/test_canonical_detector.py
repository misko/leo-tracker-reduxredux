from __future__ import annotations

from dataclasses import dataclass
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from canonical_detector import (  # noqa: E402
    CacheKey,
    CanonicalTrackingDetector,
    MARGIN_GATE,
)


RATE = 2_500_000


@dataclass(frozen=True)
class Proposal:
    receiver: int
    probe_index: int
    probe_start_sample: int
    local_epoch_sample: float
    acquired_cfo_hz: float
    supported: bool = True
    fitted: bool = True
    fractional_complete: bool = True
    margin: float = -999.0  # Native margin must never decide canonical activity.


class FakeEngine:
    def __init__(self, proposals=()):
        self.proposals = tuple(proposals)
        self.screen_calls = 0
        self.blind_calls = 0

    def screen(self, raw, *, receiver):
        self.screen_calls += 1
        return object()

    def blind(self, raw, *, receiver, screen):
        self.blind_calls += 1
        return tuple(item for item in self.proposals if item.receiver == receiver)


class FakeScorer:
    def __init__(self, *, margin=0.2, tracking_cfo=1_250.0, fail_probes=()):
        self.margin = margin
        self.tracking_cfo = tracking_cfo
        self.fail_probes = set(fail_probes)
        self.calls = []

    def __call__(self, samples, rate, *, epoch_sample, acquired_cfo_hz, edge):
        # Identify the probe from a marker in the test raw array.
        probe = int(round(float(samples.real[0])))
        self.calls.append((probe, epoch_sample, acquired_cfo_hz, edge, len(samples)))
        margin = -0.1 if probe in self.fail_probes else self.margin
        return SimpleNamespace(
            exact_score=margin + 0.1,
            control_score=0.1,
            margin=margin,
            residual_cfo_hz=self.tracking_cfo - acquired_cfo_hz,
            tracking_cfo_hz=self.tracking_cfo,
        )


def raw(rate=RATE):
    values = np.zeros((rate * 120 // 1_000, 2, 2), dtype=np.int16)
    stride = rate // 100
    for probe in range(11):
        values[probe * stride, :, 0] = probe
    values.setflags(write=False)
    return values


def key(receiver=0, channel=1):
    return CacheKey("session", receiver, channel, "lower", RATE, "tune", "cal")


def pair_proposals(receiver=0, *, fractional=True):
    fraction = 0.25 if fractional else 0.0
    return (
        Proposal(receiver, 0, 0, 100 + fraction, 1_000.0),
        Proposal(receiver, 2, 2 * (RATE // 100), 100 + fraction, 1_000.0),
    )


def test_discovery_uses_all_supported_proposals_and_only_canonical_margin() -> None:
    proposals = pair_proposals() + (
        Proposal(0, 4, 4 * (RATE // 100), 200.5, 1_000.0, supported=False),
    )
    engine = FakeEngine(proposals)
    scorer = FakeScorer()
    detector = CanonicalTrackingDetector(engine, scorer=scorer)
    result = detector.process(raw(), key(), start_counter=2**55, visit_index=1)
    assert result.active and result.route == "discovery_cold"
    assert result.pair is not None and result.pair.first.probe_index == 0
    assert result.pair.second.probe_index == 2
    assert result.proposal_count == 3
    assert result.canonical_score_count == 4  # floor+ceil for two supported proposals
    assert result.state_established
    assert engine.screen_calls == engine.blind_calls == 1
    assert all(item.margin == -999.0 for item in proposals)


def test_integer_hypothesis_is_complete_but_never_claimed_fitted() -> None:
    engine = FakeEngine(pair_proposals(fractional=False))
    result = CanonicalTrackingDetector(engine, scorer=FakeScorer()).process(
        raw(), key(), start_counter=100_000, visit_index=1
    )
    assert result.pair is not None
    for item in (result.pair.first, result.pair.second):
        assert item.fractional_complete
        assert not item.fitted
        assert item.proposal_fitted
        assert item.source_epoch_fraction == 0.0
        assert item.support_frames >= 14


def test_blind_fractional_anchor_is_separate_from_selected_integer_coordinate() -> None:
    detector = CanonicalTrackingDetector(
        FakeEngine(pair_proposals()), scorer=FakeScorer()
    )
    result = detector.process(raw(), key(), start_counter=2**55, visit_index=1)
    assert result.pair is not None
    assert result.pair.first.local_epoch_sample == 100
    anchor = detector.states[key()].anchors[0]
    assert anchor.source_epoch_counter == 2**55 + 100
    assert anchor.source_epoch_fraction == pytest.approx(0.25)


def test_guided_path_skips_rank_and_does_not_train_timing_state() -> None:
    engine = FakeEngine(pair_proposals())
    scorer = FakeScorer()
    detector = CanonicalTrackingDetector(engine, scorer=scorer)
    detector.process(raw(), key(), start_counter=1_000_000, visit_index=1)
    before = detector.states[key()]
    result = detector.process(
        raw(), key(), start_counter=1_300_000, visit_index=2
    )
    after = detector.states[key()]
    assert result.active and result.route == "guided"
    assert result.proposal_count == 0 and result.guided_attempts == 2
    assert engine.screen_calls == engine.blind_calls == 1
    assert after.anchors == before.anchors
    assert after.timing_rate_samples_per_s == before.timing_rate_samples_per_s
    assert after.guided_accepts_since_discovery == 1


def test_guided_failure_falls_open_to_one_discovery() -> None:
    engine = FakeEngine(pair_proposals())
    scorer = FakeScorer()
    detector = CanonicalTrackingDetector(engine, scorer=scorer)
    detector.process(raw(), key(), start_counter=1_000_000, visit_index=1)
    scorer.fail_probes.add(0)
    result = detector.process(raw(), key(), start_counter=1_300_000, visit_index=2)
    assert result.route == "discovery_guided_failure"
    assert result.guided_attempts == 1
    assert engine.screen_calls == engine.blind_calls == 2


def test_no_single_probe_or_cfo_inconsistent_pair_can_activate() -> None:
    one = FakeEngine(pair_proposals()[:1])
    assert not CanonicalTrackingDetector(one, scorer=FakeScorer()).process(
        raw(), key(), start_counter=1, visit_index=1
    ).active

    scorer = FakeScorer()

    def cfo_by_probe(samples, rate, *, epoch_sample, acquired_cfo_hz, edge):
        probe = int(round(float(samples.real[0])))
        tracking = 0.0 if probe == 0 else 8_001.0
        return SimpleNamespace(
            exact_score=0.2,
            control_score=0.0,
            margin=0.2,
            tracking_cfo_hz=tracking,
        )

    inconsistent = CanonicalTrackingDetector(
        FakeEngine(pair_proposals()), scorer=cfo_by_probe
    ).process(raw(), key(), start_counter=1, visit_index=1)
    assert not inconsistent.active


def test_expected_physical_cfo_is_not_an_input_to_raw_measurement() -> None:
    parameters = inspect.signature(FakeScorer().__call__).parameters
    assert "expected_physical_cfo_hz" not in parameters
    scorer = FakeScorer(tracking_cfo=12_345.0)
    detector = CanonicalTrackingDetector(FakeEngine(pair_proposals()), scorer=scorer)
    result = detector.process(raw(), key(), start_counter=10_000, visit_index=1)
    assert result.pair is not None
    assert result.pair.first.tracking_cfo_hz == 12_345.0
    assert result.pair.first.scoring_cfo_hz == 1_000.0


def test_margin_gate_is_inclusive() -> None:
    result = CanonicalTrackingDetector(
        FakeEngine(pair_proposals()), scorer=FakeScorer(margin=MARGIN_GATE)
    ).process(raw(), key(), start_counter=1, visit_index=1)
    assert result.active


def test_expiry_force_and_periodic_routes() -> None:
    engine = FakeEngine(pair_proposals(fractional=False))
    detector = CanonicalTrackingDetector(engine, scorer=FakeScorer())
    detector.process(raw(), key(), start_counter=1_000_000, visit_index=1)
    forced = detector.process(
        raw(), key(), start_counter=1_300_000, visit_index=2, force_discovery=True
    )
    assert forced.route == "discovery_forced"
    expired = detector.process(
        raw(), key(), start_counter=1_300_000 + 6_000_000, visit_index=3
    )
    assert expired.route == "discovery_expired"

    detector.clear()
    start = 10_000_000
    detector.process(raw(), key(), start_counter=start, visit_index=1)
    for index in range(2, 33):
        result = detector.process(
            raw(), key(), start_counter=start + (index - 1) * 100_000, visit_index=index
        )
        assert result.route == "guided"
    periodic = detector.process(
        raw(), key(), start_counter=start + 32 * 100_000, visit_index=33
    )
    assert periodic.route == "discovery_periodic"


def test_huge_counter_key_isolation_snapshot_and_repeat() -> None:
    engine = FakeEngine(pair_proposals(0) + pair_proposals(1))
    detector = CanonicalTrackingDetector(engine, scorer=FakeScorer())
    start = 2**55 + 123
    first = detector.process(raw(), key(0), start_counter=start, visit_index=1)
    detector.process(raw(), key(1), start_counter=start, visit_index=1)
    assert first.pair is not None
    assert first.pair.first.source_epoch_counter == start + 100
    assert len(detector.states) == 2

    snapshot = detector.snapshot()
    result1 = detector.process(
        raw(), key(0), start_counter=start + 300_000, visit_index=2
    )
    detector.restore(snapshot)
    result2 = detector.process(
        raw(), key(0), start_counter=start + 300_000, visit_index=2
    )
    assert result1 == result2


def test_huge_counter_prediction_keeps_fraction_before_float_elapsed() -> None:
    detector = CanonicalTrackingDetector(
        FakeEngine(pair_proposals()), scorer=FakeScorer()
    )
    start = 2**55 + 17
    detector.process(raw(), key(), start_counter=start, visit_index=1)
    state = detector.states[key()]
    detector.states[key()] = state.__class__(
        **{
            **{name: getattr(state, name) for name in state.__dataclass_fields__},
            "timing_rate_samples_per_s": 10.0,
        }
    )
    prediction = detector._prediction(
        key(), detector.states[key()], detector.states[key()].anchors[0], start + 300_000
    )
    assert prediction.local_epoch_sample == pytest.approx(101.45)


def test_new_discovery_track_rejects_old_out_of_bounds_slopes() -> None:
    engine = FakeEngine(pair_proposals())
    scorer = FakeScorer(tracking_cfo=1_000.0)
    detector = CanonicalTrackingDetector(engine, scorer=scorer)
    detector.process(raw(), key(), start_counter=1_000_000, visit_index=1)
    old = detector.states[key()]
    detector.states[key()] = old.__class__(
        **{
            **{name: getattr(old, name) for name in old.__dataclass_fields__},
            "timing_rate_samples_per_s": 50.0,
            "cfo_rate_hz_per_s": 500.0,
        }
    )
    engine.proposals = (
        Proposal(0, 0, 0, 1_100.25, 20_000.0),
        Proposal(0, 2, 2 * (RATE // 100), 1_100.25, 20_000.0),
    )
    scorer.tracking_cfo = 20_000.0
    detector.process(
        raw(), key(), start_counter=1_300_000, visit_index=2, force_discovery=True
    )
    new = detector.states[key()]
    assert new.timing_rate_samples_per_s == 0.0
    assert new.cfo_rate_hz_per_s == 0.0


def test_public_process_has_no_oracle_or_reference_input() -> None:
    parameters = inspect.signature(CanonicalTrackingDetector.process).parameters
    assert "reference" not in parameters and "oracle" not in parameters
    assert set(parameters) == {
        "self",
        "raw",
        "key",
        "start_counter",
        "visit_index",
        "force_discovery",
    }
