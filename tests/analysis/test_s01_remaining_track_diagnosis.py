"""Numerical controls for the remaining-track research diagnostics."""

import importlib
import sys
from pathlib import Path

import numpy as np


def module():
    directory = str(Path(__file__).resolve().parents[2] / "tools")
    if directory not in sys.path:
        sys.path.insert(0, directory)
    return importlib.import_module("diagnose_s01_ch2_t000")


def test_shared_rate_recovers_known_rate_despite_alias_and_curve_constants():
    m = module()
    times = np.linspace(220, 280, 31)
    frequency = -2100 * (times - 250) + 2 * (times - 250) ** 2
    tracks = [dict(times=times, rf_hz=rf) for rf in (10.8e9, 12.2e9)]
    values = [
        t["rf_hz"] / 11.5e9 * (frequency + 7.5 * (times - 250)) + bias
        for t, bias in zip(tracks, (m.matching.PERIOD + 200, -400), strict=True)
    ]
    rate = m.fitted_rate(tracks, values, times, frequency, [0, 1], 250)
    assert np.isclose(rate, 7.5, atol=1e-8)


def test_hardware_preserves_receiver_band_drift_and_rf_coefficient():
    m = module()
    times = np.array([0.0, 150.0, 300.0])
    beta = np.array([10, 20, 30, 40, 100, 200, 300, 400, 50.0])
    track = dict(receiver=2, channel=7, times=times, rf_hz=12e9)
    np.testing.assert_allclose(m.hardware(track, beta), [-335, 65, 465])


def test_below_horizon_prediction_cannot_pass_even_with_small_residual():
    m = module()
    times = np.linspace(0, 30, 31)
    prediction = times**2
    track = dict(key="synthetic", times=times, rf_hz=11.5e9)
    values = prediction + 5 * np.sin(np.arange(len(times)) * 2.3)
    row = m.evaluate([track], [values], times, prediction, np.full(len(times), -1))[0]
    assert row["rms_hz"] < 5
    assert not row["passing"]


def test_receiver_clock_rate_uses_ppm_and_preserves_reference_and_rx2():
    module()
    m = importlib.import_module("fit_s01_ch2_orbit_timing")
    t = np.array([220.0, 250.0, 280.0])
    np.testing.assert_allclose(
        m.warp("rx1_clock_rate_5000ppm", -3000, t, 1, 250), [220.09, 250.0, 279.91]
    )
    np.testing.assert_array_equal(m.warp("rx1_clock_rate_5000ppm", -3000, t, 2, 250), t)
    np.testing.assert_array_equal(m.warp("rx1_clock_rate_100ppm", 0, t, 1, 250), t)


def test_receiver_clock_offset_is_actual_time_shift_only_for_rx1():
    module()
    m = importlib.import_module("fit_s01_ch2_orbit_timing")
    t = np.array([220.0, 250.0, 280.0])
    np.testing.assert_allclose(m.warp("rx1_clock_offset_s", 0.25, t, 1, 250), t + 0.25)
    np.testing.assert_array_equal(m.warp("rx1_clock_offset_s", 0.25, t, 2, 250), t)
    np.testing.assert_array_equal(m.warp("e_sin_omega", 0.0002, t, 1, 250), t)
