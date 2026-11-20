import numpy as np
import pytest

from tools.pipeline_eval.variants import doppler_turns as receiver


@pytest.mark.parametrize("direction", [-1, 1])
def test_native_time_bracket_reproduces_both_kinds_of_turn_and_cancels_level(direction):
    t = np.arange(0, 48, 0.25)
    f = direction * -180 * np.abs(t - 24.15)
    _, observed = receiver.scan(t, f)
    _, calibrated = receiver.scan(t, f + 30_000)
    a, b = receiver.unique_events(observed), receiver.unique_events(calibrated)
    assert len(a) == len(b) == 1
    assert a[0]["direction"] == b[0]["direction"] == direction
    assert a[0]["time_s"] == pytest.approx(b[0]["time_s"], abs=1e-10)
    assert a[0]["time_s"] == pytest.approx(24.15, abs=1e-10)


def test_monotone_extrapolated_and_large_central_gap_cannot_create_measured_turn():
    t = np.arange(0, 45, 0.25)
    assert not receiver.scan(t, -1100 * t + 1.5 * t**2)[1]
    assert not receiver.scan(t, -180 * abs(t - 47))[1]
    gap = t[np.abs(t - 21) > 3.0]
    assert not receiver.scan(gap, -180 * abs(gap - 21))[1]


def test_single_split_turn_fails_held_validation():
    t = np.arange(0, 48, 0.25)
    f = -180 * np.abs(t - 24.15)
    f[1::2] = -180 * t[1::2]
    proposals, held = receiver.scan(t, f)
    assert proposals
    assert not held
