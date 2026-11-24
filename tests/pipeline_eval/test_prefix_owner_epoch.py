import numpy as np
import pytest

from reports.ALGO08.v3.prefix_owner_epoch import score_hypotheses, split_intervals


def test_held_observations_cannot_choose_orbit_timing():
    times = np.arange(20.)
    train, held = split_intervals(times)
    residual = np.sin(times[:-1]) * 5.
    dt = np.diff(times)
    models = [(0, np.zeros_like(dt)), (3, residual.copy())]
    measured = residual + dt * 4.
    original = score_hypotheses(measured, dt, train, held, models, 13_333.)
    measured[held] += 80.
    changed = score_hypotheses(measured, dt, train, held, models, 13_333.)
    assert original["shift_s"] == changed["shift_s"] == 3
    assert original["held_rms_samples"] == pytest.approx(0, abs=1e-10)
    assert changed["held_rms_samples"] == pytest.approx(80)


def test_intervals_leave_gap_and_share_no_observation():
    times = np.array([0, 1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15.])
    train, held = split_intervals(times)
    assert not train[2] and not held[2]
    assert set(np.flatnonzero(train) + 1).isdisjoint(np.flatnonzero(held))
    with pytest.raises(ValueError, match="Insufficient"):
        score_hypotheses(np.diff(times), np.diff(times), train, train, [], 100.)
