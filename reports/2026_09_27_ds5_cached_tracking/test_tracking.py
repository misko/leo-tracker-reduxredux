import importlib.util
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'cached_tracking', Path(__file__).with_name('tracking.py'))
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def key(rx=0, channel=1, session='s', rate=2500000):
    return m.Key(session, rx, channel, 'lower', rate)


def observation(epoch=317.25, cfo=100000, window=0, exact=.4, control=.01):
    return m.Observation(window, epoch, cfo, exact, control)


def seed(tracker, k, start=2**55, obs=None):
    assert tracker.begin(k, start, 0) == (None, 'cold')
    tracker.update(k, start, 0, obs or observation(), discovery=True)


def test_exact_counter_difference_preserves_fraction_and_noninteger_frame_period():
    t = m.Tracker()
    k = key()
    seed(t, k)
    predicted, reason = t.begin(k, 2**55 + 300001, 1)
    assert reason == 'predicted'
    assert predicted.epoch_samples == pytest.approx(316.25)


def test_states_are_separate_across_channels_receivers_and_sessions():
    t = m.Tracker()
    seed(t, key())
    for k in (key(rx=1), key(channel=2), key(session='other')):
        assert t.begin(k, 2**55 + 300000, 1) == (None, 'cold')


def test_stale_and_periodic_force_discovery():
    t = m.Tracker(m.Policy(max_age_seconds=.5, discovery_interval=2))
    k = key()
    seed(t, k)
    prediction, _ = t.begin(k, 2**55 + 300000, 1)
    obs = observation(epoch=prediction.epoch_samples)
    assert t.accepts(k, prediction, obs)
    t.update(k, 2**55 + 300000, 1, obs, discovery=False)
    assert t.begin(k, 2**55 + 600000, 2)[1] == 'periodic_discovery'
    assert t.begin(k, 2**55 + 3000000, 3)[1] == 'expired'


def test_unknown_or_failed_measurement_does_not_refresh_cache():
    t = m.Tracker()
    k = key()
    seed(t, k)
    t.begin(k, 2**55 + 300000, 1)
    assert not t.update(k, 2**55 + 300000, 1,
                        observation(exact=.01, control=.1), discovery=False)
    assert t.states[k].last_visit_start == 2**55


def test_rejects_lookahead_and_updates_from_other_visits():
    t = m.Tracker()
    k = key()
    seed(t, k)
    with pytest.raises(ValueError):
        t.begin(k, 2**55 - 1, 1)
    with pytest.raises(ValueError):
        t.update(k, 2**55 + 1, 1, observation(), discovery=False)


def test_wrong_cache_innovation_and_different_windows_rejected():
    t = m.Tracker()
    k = key()
    prediction = m.Prediction(0, 317.25, 100000, .12)
    assert not t.accepts(k, prediction, observation(cfo=200000))
    assert not t.accepts(k, prediction, observation(epoch=400))
    assert not t.accepts(k, prediction, observation(window=1))


def test_cross_window_reference_association_does_not_require_same_window():
    assert m.reference_match(observation(), observation(window=2), 2500000)
    assert not m.reference_match(observation(), observation(window=2, cfo=120000), 2500000)


def test_cfo_rate_uses_only_previous_strategy_observations_and_is_bounded():
    t = m.Tracker()
    k = key()
    seed(t, k)
    t.begin(k, 2**55 + 300000, 1)
    t.update(k, 2**55 + 300000, 1, observation(cfo=101000), discovery=False)
    p, _ = t.begin(k, 2**55 + 600000, 2)
    assert p.cfo_hz == pytest.approx(101000)


def test_drift_learned_from_two_independent_confirmations_including_fallback():
    t = m.Tracker()
    k = key()
    seed(t, k)
    t.begin(k, 2**55 + 1000000, 1)
    t.update(k, 2**55 + 1000000, 1, observation(epoch=323.25, cfo=98800), discovery=True)
    p, _ = t.begin(k, 2**55 + 2000000, 2)
    assert p.epoch_samples == pytest.approx(329.25, abs=.001)
    assert p.cfo_hz == pytest.approx(97600, abs=.01)


def test_bad_config_rejected_and_predicted_timing_does_not_learn_itself():
    with pytest.raises(ValueError):
        m.Policy(maximum_clock_error_ppm=float('nan'))
    t = m.Tracker()
    k = key()
    seed(t, k)
    t.begin(k, 2**55 + 1000000, 1)
    obs = m.Observation(0, 323.25, 100000, .4, .01, True, 'predicted_verified')
    t.update(k, 2**55 + 1000000, 1, obs, discovery=False)
    assert t.states[k].timing_rate_samples_per_s == 0


def test_point_confirmation_cannot_shorten_timing_fit_baseline():
    t = m.Tracker()
    k = key()
    seed(t, k)
    t.begin(k, 2**55 + 1000000, 1)
    obs = m.Observation(0, 317.25, 100000, .4, .01, True, 'predicted_verified')
    t.update(k, 2**55 + 1000000, 1, obs, discovery=False)
    t.begin(k, 2**55 + 1250000, 2)
    t.update(k, 2**55 + 1250000, 2, observation(epoch=324.75), discovery=True)
    assert t.states[k].timing_rate_samples_per_s == pytest.approx(15, abs=.001)


def test_cfo_outlier_does_not_erase_an_independent_timing_fit():
    t = m.Tracker()
    k = key()
    seed(t, k)
    t.begin(k, 2**55 + 1000000, 1)
    t.update(k, 2**55 + 1000000, 1, observation(epoch=323.25), discovery=True)
    anchor = t.states[k].fit_anchor_counter
    p, _ = t.begin(k, 2**55 + 1250000, 2)
    obs = m.Observation(0, p.epoch_samples, 107000, .4, .01, True, 'predicted_verified')
    assert t.accepts(k, p, obs)
    t.update(k, 2**55 + 1250000, 2, obs, discovery=False)
    assert t.states[k].fit_anchor_counter == anchor
    assert t.states[k].timing_rate_samples_per_s == pytest.approx(15, abs=.001)


def test_scoring_cfo_and_physical_cfo_have_separate_support_and_innovation():
    t = m.Tracker()
    k = key()
    seed(t, k, obs=m.Observation(0, 317.25, 401000, .4, .01,
                                scoring_cfo_hz=390000))
    p, reason = t.begin(k, 2**55 + 300000, 1)
    assert reason == 'predicted'
    assert p.cfo_hz == 401000
    assert p.scoring_cfo_hz == 390000
    assert t.accepts(k, p, m.Observation(0, p.epoch_samples, 402000, .4, .01,
                                        scoring_cfo_hz=390000))
    assert not t.accepts(k, p, m.Observation(0, p.epoch_samples, 390000, .4, .01,
                                            scoring_cfo_hz=390000))


def test_scoring_cfo_offset_preserved_by_causal_physical_rate():
    t = m.Tracker()
    k = key()
    seed(t, k, obs=m.Observation(0, 317.25, 5000, .4, .01,
                                scoring_cfo_hz=103000))
    t.begin(k, 2**55 + 1000000, 1)
    t.update(k, 2**55 + 1000000, 1,
             m.Observation(0, 317.25, 5400, .4, .01, scoring_cfo_hz=103400),
             discovery=True)
    p, _ = t.begin(k, 2**55 + 2000000, 2)
    assert p.cfo_hz == pytest.approx(5800)
    assert p.scoring_cfo_hz == pytest.approx(103800)
