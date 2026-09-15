"""Causal tracking lifecycle and source isolation, independently supplied observations."""

import pytest

from leo.analysis.starlink.pss_tracker import PssObservation, PssTracker


def observation(t, phase=0.0002, cfo=100000.0):
    return PssObservation(t, phase, cfo, 2e-8, 25000.0, 12.0)


def test_lifecycle_prediction_gap_and_reacquisition():
    tracker = PssTracker("radio:rx0:ch1lower")
    for t in (0.0, 1.0, 2.0):
        result = tracker.update("radio:rx0:ch1lower", t, (observation(t, 0.0002 + t * 1e-7),))
    assert result.state == "tracking"
    assert result.candidate_only
    assert result.timing_rate_s_per_s == pytest.approx(1e-7, abs=2e-8)
    result = tracker.update("radio:rx0:ch1lower", 3.0, ())
    assert result.state == "coasting"
    result = tracker.update("radio:rx0:ch1lower", 10.0, ())
    assert result.state == "lost"
    result = tracker.update("radio:rx0:ch1lower", 11.0, (observation(11.0, 0.0008),))
    assert result.state == "acquiring"


def test_ambiguity_abstains_and_source_and_time_are_enforced():
    tracker = PssTracker("source")
    result = tracker.update("source", 0.0, (observation(0.0), observation(0.0, 0.0005)))
    assert result.state == "acquiring"
    assert result.reason == "ambiguous timing modes"
    assert result.frame_phase_s is None
    with pytest.raises(ValueError, match="source"):
        tracker.update("rx1", 1.0, ())
    with pytest.raises(ValueError, match="increasing"):
        tracker.update("source", 0.0, ())


def test_outlier_does_not_pull_estimate_and_phase_wrap_is_safe():
    tracker = PssTracker("source")
    period = 1 / 750
    for i in range(3):
        tracker.update(
            "source", float(i), (observation(float(i), (period - 1e-7 + i * 1e-7) % period),)
        )
    result = tracker.update("source", 3.0, (observation(3.0, 0.0005),))
    assert result.state == "coasting"
    assert result.reason == "no observation inside prediction gate"
    assert abs(result.timing_rate_s_per_s - 1e-7) < 2e-8


def test_prediction_bank_is_nonmutating_bounded_and_returns_blind_after_gap():
    tracker = PssTracker("source")
    blind = (-1e6, 0.0, 1e6)
    assert tracker.frequency_bank(0.0, blind, step_hz=25000.0) == blind
    for i in range(3):
        tracker.update("source", float(i), (observation(float(i)),))
    bank = tracker.frequency_bank(3.0, blind, step_hz=25000.0)
    assert min(blind) <= min(bank) < 100000.0 < max(bank) <= max(blind)
    assert len(bank) <= 257
    assert tracker.frequency_bank(3.0, blind, step_hz=25000.0) == bank
    assert tracker.frequency_bank(10.0, blind, step_hz=25000.0) == blind
