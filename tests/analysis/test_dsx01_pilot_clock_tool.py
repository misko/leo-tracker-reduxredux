"""Independent waveform controls for the frame-local two-clock prototype."""

import numpy as np
import pytest
from dsx01_pilot_clock import FrameClock, WindowClock, differential_chirp, synthetic_frame


@pytest.mark.parametrize("edge,ppm", [("lower", -30), ("upper", 25), ("lower", 0)])
def test_separates_carrier_and_symbol_clock_with_unknown_channel(edge, ppm):
    gains = np.array([0.2, 0.4, 0.7, 1.3, 1.0, 0.3, 0.7, 0.1]) * np.exp(0.7j * np.arange(8))
    iq = synthetic_frame(edge=edge, cfo=203217.4, ppm=ppm, gains=gains)
    fit = FrameClock(iq, 2_500_000, 10.27, 203000, edge).fit()
    assert fit.residual_cfo_hz == pytest.approx(217.4, abs=0.01)
    assert fit.symbol_clock_ppm == pytest.approx(ppm, abs=0.01)
    assert fit.explained_fraction > 0.999999
    assert fit.converged and not fit.boundary


def test_joint_clock_removes_asymmetric_tone_carrier_bias():
    gains = np.linspace(0.1, 2, 8)
    iq = synthetic_frame(cfo=120.0, ppm=40, gains=gains)
    model = FrameClock(iq, 2_500_000, 10.27, 0, "lower")
    common, joint = model.fit(symbol_clock=False), model.fit()
    assert abs(common.residual_cfo_hz - 120) > 10
    assert joint.residual_cfo_hz == pytest.approx(120, abs=0.01)
    assert joint.explained_fraction > common.explained_fraction


def test_profiled_gradient_matches_finite_difference():
    iq = synthetic_frame(cfo=170, ppm=-20, noise=0.2)
    model = FrameClock(iq, 2_500_000, 10.27, 0, "lower")
    x = np.array([0.2, -0.1])
    _, jac = model.objective(x)
    for j in range(2):
        dx = np.eye(2)[j] * 1e-5
        finite = (model.objective(x + dx)[0] - model.objective(x - dx)[0]) / 2e-5
        assert jac[j] == pytest.approx(finite, abs=1e-7)


def test_wrong_sequence_and_noise_do_not_become_coherent():
    iq = synthetic_frame(cfo=150, ppm=20, roll=17, noise=0.2)
    exact = FrameClock(iq, 2_500_000, 10.27, 0, "lower").fit()
    control = FrameClock(iq, 2_500_000, 10.27, 0, "lower", roll=17).fit()
    assert exact.explained_fraction < 0.03
    assert control.explained_fraction > 0.95
    noise = synthetic_frame(gains=np.zeros(8), noise=1)
    null = FrameClock(noise, 2_500_000, 10.27, 0, "lower").fit()
    assert null.explained_fraction < 0.03


def test_half_frame_estimates_and_constant_complex_phase_are_consistent():
    iq = synthetic_frame(cfo=-270, ppm=45, noise=0.01)
    fits = [
        FrameClock(iq * np.exp(1.2j), 2_500_000, 10.27, 0, "lower", half=h).fit()
        for h in [None, 0, 1]
    ]
    assert np.ptp([v.residual_cfo_hz for v in fits]) < 1
    assert np.ptp([v.symbol_clock_ppm for v in fits]) < 1


def test_refuses_incomplete_or_zero_energy_frame():
    with pytest.raises(ValueError, match="complete"):
        FrameClock(np.ones(100), 2_500_000, 10.27, 0, "lower")
    with pytest.raises(ValueError, match="nonzero"):
        FrameClock(np.zeros(4000), 2_500_000, 10.27, 0, "lower")


def test_window_likelihood_allows_independent_frame_phases_and_channels():
    frames = []
    rng = np.random.default_rng(42)
    for number in range(6):
        gain = rng.uniform(0.5, 2, 8) * np.exp(1j * rng.uniform(-np.pi, np.pi, 8))
        iq = synthetic_frame(cfo=317, ppm=-23, gains=gain, noise=0.02, seed=number)
        frames.append(FrameClock(iq, 2_500_000, 10.27, 300, "lower"))
    fit = WindowClock(frames).fit()
    assert fit.residual_cfo_hz == pytest.approx(17, abs=1)
    assert fit.symbol_clock_ppm == pytest.approx(-23, abs=1)
    assert fit.explained_fraction > 0.99


def test_template_free_differential_chirp_recovers_relative_radio_rate():
    rng = np.random.default_rng(91)
    rate, epoch = 2_500_000, 13.0
    time = np.arange(50000) / rate
    centered = time - (epoch / rate + 7 / 750)
    common = rng.normal(size=len(time)) + 1j * rng.normal(size=len(time))
    frame_index = np.maximum(0, np.floor((time - epoch / rate) * 750).astype(int))
    phases = rng.uniform(-np.pi, np.pi, 16)[frame_index]
    first = common * np.exp(2j * np.pi * (26370 * time - 15000 * centered**2) + 1j * phases)
    second = common
    result = differential_chirp(first, second, rate, epoch)
    assert result["frequency_difference_hz"] == pytest.approx(26370, abs=1)
    assert result["difference_rate_hz_s"] == pytest.approx(-30000, abs=100)
    assert result["explained_fraction"] > result["constant_explained_fraction"]
    assert result["converged"] and not result["boundary"]
