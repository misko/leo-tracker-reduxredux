"""Shared UTC, independent orbit phase and elapsed hardware time stay distinct."""

import numpy as np
import pytest
from dsx01_common_clock import CommonClockMixin


class Base:
    def __init__(self):
        self.initial = np.array([0.2, 0.4])
        self.lower = np.array([-1.0, -1.0])
        self.upper = np.array([1.0, 1.0])
        self.flat_times = np.array([1.0, 2.0, 3.0])

    def decode(self, x):
        assert len(x) == 2
        return dict(original_parameters=np.array(x))

    def residual(self, x, *, details=False):
        r = self.decode(x)["original_parameters"]
        return (r, ["diagnostic"]) if details else r


class Clock(CommonClockMixin, Base):
    pass


def test_shared_clock_uses_measured_bounds_and_adds_one_gaussian_prior():
    p = Clock(clock=dict(lower_shift_s=-0.12, upper_shift_s=0.13, mean_shift_s=0.005, sigma_s=0.07))
    x = np.r_[p.initial[:2], 1.0]
    state = p.decode(x)
    assert state["common_utc_shift_s"] == pytest.approx(0.075)
    np.testing.assert_array_equal(state["original_parameters"], [0.2, 0.4])
    np.testing.assert_allclose(p.observation_times(state), [1.075, 2.075, 3.075])
    np.testing.assert_array_equal(p.flat_times, [1, 2, 3])
    assert p.decode(p.lower)["common_utc_shift_s"] == pytest.approx(-0.12)
    assert p.decode(p.upper)["common_utc_shift_s"] == pytest.approx(0.13)
    residual, details = p.residual(x, details=True)
    np.testing.assert_array_equal(residual, [0.2, 0.4, 1.0])
    assert details == ["diagnostic"] and p.timing_parameters == 1
