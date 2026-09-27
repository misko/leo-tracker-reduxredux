from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("tg11_decision", HERE / "decision.py")
assert SPEC is not None and SPEC.loader is not None
d = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = d
SPEC.loader.exec_module(d)


def key(**changes):
    fields = {
        "continuity_epoch": "session-a",
        "receiver": 0,
        "channel": 2,
        "edge": "upper",
        "rate_hz": 2_500_000,
        "tuning_identity": "tune-a",
        "calibration_identity": "cal-a",
    }
    fields.update(changes)
    return d.CacheKey(**fields)


def probe_start(rate, index):
    return index * rate // 100


def local_epoch(rate, anchor_counter, anchor_fraction, start_counter, index):
    start = probe_start(rate, index)
    integer = ((anchor_counter - start_counter - start) * 750 % rate) / 750
    return (integer + anchor_fraction) % (rate / 750)


def screen(rate, start_counter, anchor_counter, anchor_fraction=0.25, *, offset=0.0):
    return d.ScreenResult(
        tuple(
            d.ScreenWindow(
                index,
                probe_start(rate, index),
                local_epoch(
                    rate, anchor_counter, anchor_fraction, start_counter, index
                )
                + offset,
                1.0,
            )
            for index in range(11)
        )
    )


def observation(
    rate,
    start_counter,
    anchor_counter,
    index,
    *,
    receiver=0,
    anchor_fraction=0.25,
    acquired_cfo_hz=300_000.0,
    tracking_cfo_hz=100_000.0,
    margin=0.2,
    fitted=True,
    valid_support=True,
    support_frames=15,
    candidate_index=0,
):
    local = local_epoch(
        rate, anchor_counter, anchor_fraction, start_counter, index
    )
    start = probe_start(rate, index)
    return d.Observation(
        receiver=receiver,
        probe_index=index,
        probe_start_sample=start,
        local_epoch_sample=local,
        acquired_cfo_hz=acquired_cfo_hz,
        tracking_cfo_hz=tracking_cfo_hz,
        margin=margin,
        fractional_complete=True,
        supported=True,
        fitted=fitted,
        candidate_index=candidate_index,
        exact_score=margin + 0.1,
        control_score=0.1,
        support_frames=support_frames,
        valid_support=valid_support,
        dwell_epoch_sample=start + local,
    )


def blind_pair(rate, start_counter, anchor_counter, **changes):
    return tuple(
        observation(rate, start_counter, anchor_counter, index, **changes)
        for index in (0, 2)
    )


class FakeEngine:
    def __init__(self):
        self.screen_calls = 0
        self.blind_calls = 0
        self.guided_calls = []

    def screen(self, raw, *, receiver):
        self.screen_calls += 1
        assert receiver == raw["receiver"]
        return raw["screen"]

    def blind(self, raw, *, receiver, screen):
        self.blind_calls += 1
        assert receiver == raw["receiver"]
        assert screen is raw["screen"]
        return tuple(raw.get("blind", ()))

    def guided(
        self,
        raw,
        *,
        receiver,
        probe_index,
        predicted_local_epoch_sample,
        scoring_cfo_hz,
        expected_physical_cfo_hz,
    ):
        self.guided_calls.append(
            {
                "receiver": receiver,
                "probe_index": probe_index,
                "predicted_local_epoch_sample": predicted_local_epoch_sample,
                "scoring_cfo_hz": scoring_cfo_hz,
                "expected_physical_cfo_hz": expected_physical_cfo_hz,
            }
        )
        mode = raw.get("guided", "good")
        if mode == "none":
            return None
        margin = -0.1 if mode == "negative" else 0.2
        rate = raw["rate_hz"]
        start = probe_start(rate, probe_index)
        return d.Observation(
            receiver=receiver,
            probe_index=probe_index,
            probe_start_sample=start,
            local_epoch_sample=predicted_local_epoch_sample,
            acquired_cfo_hz=scoring_cfo_hz,
            tracking_cfo_hz=expected_physical_cfo_hz,
            margin=margin,
            fractional_complete=True,
            supported=True,
            fitted=False,
            support_frames=14,
            valid_support=True,
            dwell_epoch_sample=start + predicted_local_epoch_sample,
        )


def raw_for(
    k,
    start_counter,
    anchor_counter,
    *,
    blind=(),
    guided="good",
    screen_offset=0.0,
):
    return {
        "receiver": k.receiver,
        "rate_hz": k.rate_hz,
        "screen": screen(
            k.rate_hz,
            start_counter,
            anchor_counter,
            offset=screen_offset,
        ),
        "blind": blind,
        "guided": guided,
    }


def seed(detector, k, start_counter=2**55, *, fraction=0.25):
    anchor = start_counter + 317
    rows = blind_pair(
        k.rate_hz,
        start_counter,
        anchor,
        receiver=k.receiver,
        anchor_fraction=fraction,
    )
    raw = raw_for(k, start_counter, anchor, blind=rows)
    result = detector.process(raw, k, start_counter=start_counter, visit_index=0)
    assert result.active and result.route == "blind_cold"
    return anchor, result


def test_cold_route_screens_then_blind_maps_large_source_counter_exactly():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    anchor, result = seed(detector, k, start, fraction=0.375)
    assert engine.screen_calls == engine.blind_calls == 1
    assert result.screen_windows == 11
    assert result.guided_attempts == 0
    assert result.pair.first.source_epoch_counter == anchor
    assert result.pair.first.source_epoch_fraction == pytest.approx(0.375)
    assert result.pair.first.dwell_epoch_sample == pytest.approx(317.375)
    state = detector.states[k]
    assert type(state.fitted_source_anchor_counter) is int
    assert state.fitted_source_anchor_fraction == pytest.approx(0.375)


def test_guided_pair_passes_distinct_scoring_and_physical_cfo_and_preserves_fit():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    anchor, _ = seed(detector, k, start)
    fitted = detector.states[k]
    next_start = start + 300_000
    raw = raw_for(k, next_start, fitted.fitted_source_anchor_counter)
    result = detector.process(raw, k, start_counter=next_start, visit_index=1)
    assert result.active and result.route == "guided"
    assert result.guided_attempts == 3
    assert result.blind_observations == 0
    assert engine.guided_calls[0]["scoring_cfo_hz"] == 300_000.0
    assert engine.guided_calls[0]["expected_physical_cfo_hz"] == 100_000.0
    updated = detector.states[k]
    assert updated.fitted_source_anchor_counter == fitted.fitted_source_anchor_counter
    assert updated.fitted_source_anchor_fraction == fitted.fitted_source_anchor_fraction
    assert updated.timing_rate_samples_per_s == fitted.timing_rate_samples_per_s
    assert updated.cfo_rate_hz_per_s == fitted.cfo_rate_hz_per_s
    assert updated.guided_accepts_since_discovery == 1
    assert result.pair.first.source_epoch_counter >= next_start
    assert anchor < result.pair.first.source_epoch_counter


def test_failed_guided_check_fails_open_and_never_emits_stale_positive():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    seed(detector, k, start)
    previous = detector.states[k]
    next_start = start + 300_000
    raw = raw_for(
        k,
        next_start,
        previous.fitted_source_anchor_counter,
        blind=(),
        guided="none",
    )
    result = detector.process(raw, k, start_counter=next_start, visit_index=1)
    assert not result.active
    assert result.route == "blind_guided_failure"
    assert result.guided_attempts == 1
    assert engine.blind_calls == 2
    assert detector.states[k] == previous


def test_screen_disagreement_is_only_a_route_and_cannot_declare_negative():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    seed(detector, k, start)
    previous = detector.states[k]
    next_start = start + 300_000
    replacement_anchor = next_start + 611
    rows = blind_pair(k.rate_hz, next_start, replacement_anchor)
    raw = raw_for(
        k,
        next_start,
        previous.fitted_source_anchor_counter,
        blind=rows,
        screen_offset=k.rate_hz * 20e-6,
    )
    result = detector.process(raw, k, start_counter=next_start, visit_index=1)
    assert result.active
    assert result.route == "blind_screen_disagreement"
    assert result.blind_observations == 2
    assert not engine.guided_calls
    assert detector.states[k].fitted_source_anchor_counter != previous.fitted_source_anchor_counter


def test_expiry_forces_blind_without_refreshing_state_on_negative():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    seed(detector, k, start)
    previous = detector.states[k]
    next_start = start + 2 * k.rate_hz + 1
    raw = raw_for(k, next_start, previous.fitted_source_anchor_counter, blind=())
    result = detector.process(raw, k, start_counter=next_start, visit_index=1)
    assert not result.active and result.route == "blind_expired"
    assert detector.states[k] == previous


def test_one_discovery_plus_31_guided_accepts_forces_next_visit_blind():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    seed(detector, k, start)
    for visit in range(1, 32):
        current = start + visit * 300_000
        state = detector.states[k]
        raw = raw_for(k, current, state.fitted_source_anchor_counter)
        result = detector.process(raw, k, start_counter=current, visit_index=visit)
        assert result.route == "guided"
    assert detector.states[k].guided_accepts_since_discovery == 31
    guided_calls = len(engine.guided_calls)
    current = start + 32 * 300_000
    state = detector.states[k]
    rows = blind_pair(k.rate_hz, current, current + 317)
    raw = raw_for(k, current, state.fitted_source_anchor_counter, blind=rows)
    result = detector.process(raw, k, start_counter=current, visit_index=32)
    assert result.active and result.route == "blind_periodic_discovery"
    assert len(engine.guided_calls) == guided_calls
    assert detector.states[k].guided_accepts_since_discovery == 0


@pytest.mark.parametrize(
    "changed",
    [
        {"continuity_epoch": "session-b"},
        {"receiver": 1},
        {"channel": 3},
        {"edge": "lower"},
        {"rate_hz": 5_000_000},
        {"tuning_identity": "tune-b"},
        {"calibration_identity": "cal-b"},
    ],
    ids=("continuity", "receiver", "channel", "edge", "rate", "tuning", "calibration"),
)
def test_every_cache_key_dimension_isolated(changed):
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    base = key()
    start = 2**55
    seed(detector, base, start)
    other = key(**changed)
    raw = raw_for(other, start + 300_000, start + 300_317, blind=())
    result = detector.process(raw, other, start_counter=start + 300_000, visit_index=1)
    assert not result.active and result.route == "blind_cold"
    assert engine.guided_calls == []


def test_pair_gate_is_inclusive_and_uses_nonoverlap_and_cfo():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    anchor = start + 317
    first = observation(
        k.rate_hz, start, anchor, 0, margin=0.025, tracking_cfo_hz=0.0
    )
    overlap = observation(
        k.rate_hz, start, anchor, 1, margin=0.9, tracking_cfo_hz=0.0
    )
    edge = observation(
        k.rate_hz, start, anchor, 2, margin=0.025, tracking_cfo_hz=8_000.0
    )
    raw = raw_for(k, start, anchor, blind=(first, overlap, edge))
    result = detector.process(raw, k, start_counter=start, visit_index=0)
    assert result.active
    assert result.pair.first.probe_index == 0
    assert result.pair.second.probe_index == 2

    engine2 = FakeEngine()
    detector2 = d.TG11Detector(engine2)
    outside = observation(
        k.rate_hz, start, anchor, 2, margin=0.025, tracking_cfo_hz=8_000.001
    )
    raw2 = raw_for(k, start, anchor, blind=(first, overlap, outside))
    result2 = detector2.process(raw2, k, start_counter=start, visit_index=0)
    assert not result2.active


def test_actual_available_support_is_accepted_without_requiring_sixteen_frames():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    anchor = start + 317
    rows = blind_pair(k.rate_hz, start, anchor, support_frames=14, valid_support=True)
    result = detector.process(
        raw_for(k, start, anchor, blind=rows),
        k,
        start_counter=start,
        visit_index=0,
    )
    assert result.active

    engine2 = FakeEngine()
    detector2 = d.TG11Detector(engine2)
    invalid = blind_pair(
        k.rate_hz, start, anchor, support_frames=15, valid_support=False
    )
    result2 = detector2.process(
        raw_for(k, start, anchor, blind=invalid),
        k,
        start_counter=start,
        visit_index=0,
    )
    assert not result2.active


def test_snapshot_restore_repeats_one_causal_visit_without_copying_engine():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    seed(detector, k, start)
    snapshot = detector.snapshot()
    next_start = start + 300_000
    state = detector.states[k]
    raw = raw_for(k, next_start, state.fitted_source_anchor_counter)
    first = detector.process(raw, k, start_counter=next_start, visit_index=1)
    detector.restore(snapshot)
    second = detector.process(raw, k, start_counter=next_start, visit_index=1)
    assert first == second
    assert detector.engine is engine


def test_fitted_rates_and_prediction_use_actual_moving_probe_observation_times():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    seed(detector, k, start)
    previous = detector.states[k]

    next_start = start + k.rate_hz
    target_probe = 8
    base = detector._prediction(
        previous, k, next_start, probe_start(k.rate_hz, target_probe)
    )
    base_counter = next_start + probe_start(k.rate_hz, target_probe) + int(base.local_epoch_sample)
    base_fraction = base.local_epoch_sample - int(base.local_epoch_sample)
    base_elapsed_samples = (
        base_counter
        - previous.fitted_source_anchor_counter
        + base_fraction
        - previous.fitted_source_anchor_fraction
    )
    timing_rate = 10.0
    shift = timing_rate * base_elapsed_samples / (k.rate_hz - timing_rate)
    shifted_local = base.local_epoch_sample + shift
    shifted_whole = int(shifted_local)
    shifted_fraction = shifted_local - shifted_whole
    shifted_counter = next_start + probe_start(k.rate_hz, target_probe) + shifted_whole
    fit_dt = (
        shifted_counter
        - previous.fitted_source_anchor_counter
        + shifted_fraction
        - previous.fitted_source_anchor_fraction
    ) / k.rate_hz
    fitted_cfo = previous.fitted_physical_cfo_hz + 1_000.0 * fit_dt

    def fitted(index, local, physical):
        return d.Observation(
            receiver=k.receiver,
            probe_index=index,
            probe_start_sample=probe_start(k.rate_hz, index),
            local_epoch_sample=local,
            acquired_cfo_hz=300_000.0,
            tracking_cfo_hz=physical,
            margin=0.2,
            fractional_complete=True,
            supported=True,
            fitted=True,
            support_frames=15,
            valid_support=True,
            dwell_epoch_sample=probe_start(k.rate_hz, index) + local,
        )

    first_local = local_epoch(
        k.rate_hz, shifted_counter, shifted_fraction, next_start, 0
    )
    rows = (fitted(0, first_local, fitted_cfo), fitted(target_probe, shifted_local, fitted_cfo))
    raw = raw_for(
        k,
        next_start,
        previous.fitted_source_anchor_counter,
        blind=rows,
        screen_offset=k.rate_hz * 20e-6,
    )
    result = detector.process(raw, k, start_counter=next_start, visit_index=1)
    assert result.active and result.route == "blind_screen_disagreement"
    state = detector.states[k]
    assert state.timing_rate_samples_per_s == pytest.approx(10.0, abs=1e-6)
    assert state.cfo_rate_hz_per_s == pytest.approx(1_000.0, abs=1e-6)

    final_start = next_start + k.rate_hz
    prediction = detector._prediction(state, k, final_start, 0)
    no_drift = (
        (
            (state.fitted_source_anchor_counter - final_start) * 750
            % k.rate_hz
        )
        / 750
        + state.fitted_source_anchor_fraction
    ) % (k.rate_hz / 750)
    timing_advance = d.circular_samples(
        prediction.local_epoch_sample - no_drift, k.rate_hz
    )
    assert timing_advance == pytest.approx(9.2, abs=0.01)
    assert prediction.physical_cfo_hz - state.physical_cfo_hz == pytest.approx(
        920.0, abs=0.1
    )


def test_native_shaped_observation_without_valid_support_alias_is_accepted():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    anchor = start + 317
    rows = []
    for index in (0, 2):
        item = observation(k.rate_hz, start, anchor, index)
        values = {
            name: getattr(item, name)
            for name in (
                "receiver",
                "probe_index",
                "probe_start_sample",
                "local_epoch_sample",
                "acquired_cfo_hz",
                "tracking_cfo_hz",
                "margin",
                "fractional_complete",
                "supported",
                "fitted",
            )
        }
        rows.append(SimpleNamespace(**values))
    result = detector.process(
        raw_for(k, start, anchor, blind=tuple(rows)),
        k,
        start_counter=start,
        visit_index=0,
    )
    assert result.active


def test_rejects_replay_and_incomplete_screen_geometry():
    engine = FakeEngine()
    detector = d.TG11Detector(engine)
    k = key()
    start = 2**55
    seed(detector, k, start)
    raw = raw_for(k, start, start + 317, blind=())
    with pytest.raises(ValueError, match="advance causally"):
        detector.process(raw, k, start_counter=start, visit_index=1)

    other = key(channel=4)
    broken = raw_for(other, start, start + 317, blind=())
    broken["screen"] = d.ScreenResult(broken["screen"].windows[:-1])
    with pytest.raises(ValueError, match="all eleven"):
        detector.process(broken, other, start_counter=start, visit_index=0)
