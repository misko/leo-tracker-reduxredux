from importlib import import_module

import numpy as np
import pytest

audit = import_module("reports.ALGO08.single-core-2x.absolute_timing_trial")


@pytest.mark.parametrize("offset_s", [-0.000300, 0.000579])
def test_unknown_transmit_phase_absorbs_constant_range_on_both_receivers(offset_s):
    rate = 10_000_000
    times = np.array([.012, .310, 15.001, 291.547])
    counters = np.rint((times - .01) * rate)
    delays = np.array([.0018, .0017, .0023, .0031])
    periods = rate / 750 * (1 + np.array([1e-5, 1e-5, 2e-5, 1e-5]))
    error = audit.phase_gauge(delays, offset_s, .00031, times, counters, rate, periods)
    assert error < audit.TOLERANCE_SAMPLES


def test_transmit_phase_authority_restores_the_instantaneous_delay_change():
    rate = 10_000_000
    period = rate / 750
    a = np.array([.003])
    b = np.array([.0030005])
    time = np.array([.01005])
    anchor = np.array([0])
    known_phase = .00041
    first = audit.receive_epoch(a, known_phase, time, anchor, rate, period, .00005, 0)
    shifted = audit.receive_epoch(b, known_phase, time, anchor, rate, period, .00005, 0)
    receiver_b = audit.receive_epoch(b, known_phase, time, anchor, rate, period, .00005, 1)
    np.testing.assert_allclose(shifted - first, [5.], atol=1e-9, rtol=0.)
    np.testing.assert_allclose(receiver_b - shifted, [.42], atol=1e-9, rtol=0.)
