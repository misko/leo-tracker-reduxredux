import numpy as np
import pytest

from leo.analysis.research.causal_pss_lock import (
    PssLockConfig,
    PssLockObservation,
    track_pss_observations,
)


def points(count=750):
    rng = np.random.default_rng(13)
    t = np.arange(count) / 750
    # Cross the circular frame boundary while drifting at four ppm.
    phase = (1 / 750 - 1e-6 + 4e-6 * t - 0.15e-6 * t * t + rng.normal(0, 3e-9, count)) % (1 / 750)
    return [PssLockObservation(float(x), float(y), 20) for x, y in zip(t, phase, strict=True)]


def test_rejects_repetition_alias_burst_without_moving_predictions():
    raw = points()
    for i in range(210, 310):
        p = raw[i]
        raw[i] = PssLockObservation(p.time_s, p.phase_s + 128 / 240e6, 30)
    decisions = track_pss_observations(tuple(raw))
    assert decisions[63].status == "lock_acquired"
    assert all(x.status == "acquiring" for x in decisions[:63])
    assert all(x.status == "rejected" for x in decisions[210:310])
    assert all(x.status == "accepted" for x in decisions[310:])
    assert max(x.lock_id for x in decisions) == 1
    assert abs(decisions[-1].innovation_s) < 20e-9


def test_future_observations_cannot_change_earlier_decisions():
    raw = points()
    prefix = track_pss_observations(tuple(raw[:400]))
    for i in range(400, len(raw)):
        p = raw[i]
        raw[i] = PssLockObservation(p.time_s, p.phase_s + 300e-6, 20)
    assert track_pss_observations(tuple(raw))[:400] == prefix


def test_long_rejection_burst_expires_and_declares_a_new_lock():
    raw = points()
    for i in range(200, len(raw)):
        p = raw[i]
        raw[i] = PssLockObservation(p.time_s, p.phase_s + 3e-6, 20)
    d = track_pss_observations(tuple(raw))
    lost = [x for x in d if x.status == "lost_lock"]
    assert len(lost) == 1 and lost[0].reset_reason == "coast_expired"
    assert d[-1].lock_id == 2 and d[-1].status == "accepted"


def test_continuity_change_resets_and_weak_measurements_do_not_update():
    raw = points(200)
    raw[100] = PssLockObservation(raw[100].time_s, raw[100].phase_s, 1)
    for i in range(130, len(raw)):
        p = raw[i]
        raw[i] = PssLockObservation(p.time_s, p.phase_s, 20, 1)
    d = track_pss_observations(tuple(raw))
    assert d[100].status == "rejected"
    assert d[130].status == "lost_lock"
    assert d[130].reset_reason == "continuity_segment_changed"
    assert d[-1].lock_id == 2


def test_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="increasing"):
        track_pss_observations((points()[0], points()[0]))
    with pytest.raises(ValueError, match="finite"):
        track_pss_observations((PssLockObservation(0, float("nan"), 20),))
    with pytest.raises(ValueError, match="half a frame"):
        PssLockConfig(innovation_gate_s=0.01)
