"""Settling extrapolation requires observed curvature, rather than a ramp."""

import numpy as np
from probe_dsx01_settling import summarize


def windows(tau):
    rng = np.random.default_rng(9)
    times = np.linspace(-0.008, 0.009, 14)
    result = []
    for _ in range(80):
        basis = times if np.isinf(tau) else -tau * np.expm1(-times / tau)
        y = rng.normal(0, 50) + rng.normal(-20000, 4000) * basis + rng.normal(0, 15, len(times))
        result.append(dict(time=times, frequency=y, weight=np.ones(len(times))))
    return result


def test_curved_settling_signal_identifies_shared_time_constant():
    fit = summarize(windows(0.010), bootstrap=32)
    assert fit["identified_for_extrapolation"]
    assert 8 < fit["best_tau_ms"] < 12


def test_linear_radio_ramps_do_not_authorize_a_settling_correction():
    fit = summarize(windows(np.inf), bootstrap=32)
    assert not fit["identified_for_extrapolation"]
    assert fit["best_tau_ms"] is None or fit["best_tau_ms"] > 50
