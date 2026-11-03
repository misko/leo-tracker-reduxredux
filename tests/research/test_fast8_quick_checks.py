"""Synthetic properties of exploratory prefilters, without radio fixtures."""
import numpy as np
import pytest

from tools.fast8_quick_checks import (
    power_features,
    reduced_pilot_features,
    repeat_features,
    spectrum_features,
)


def noise(seed=21, count=50000):
    rng = np.random.default_rng(seed)
    return rng.normal(size=count) + 1j * rng.normal(size=count)


def test_adaptive_power_convention_and_gain():
    x = noise()
    score = power_features(x, 2500000)
    expected = 10 * np.log10(np.mean(np.r_[x.real**2, x.imag**2]) / 32768**2)
    assert score['power_dbfs'] == pytest.approx(expected)
    delta = power_features(2*x, 2500000)['power_dbfs'] - score['power_dbfs']
    assert delta == pytest.approx(20*np.log10(2))


def test_burst_energy_detects_intermittency():
    x = noise()
    burst = x.copy()
    burst[10000:20000] *= 4
    assert (
        power_features(burst, 2500000)['burst_spread_db']
        > power_features(x, 2500000)['burst_spread_db'] + 8
    )


def test_repeat_is_gain_and_constant_frequency_offset_invariant():
    x = np.tile(noise(count=10000), 5)
    result = repeat_features(x, 2500000)
    shifted = repeat_features(7*x*np.exp(2j*np.pi*.12*np.arange(len(x))), 2500000)
    assert result['repeat_excess'] > .99
    assert shifted['repeat_excess'] == pytest.approx(result['repeat_excess'], abs=2e-4)
    assert repeat_features(noise(), 2500000)['repeat_excess'] < .01


def test_repeat_controls_reject_tone():
    tone = np.exp(2j*np.pi*.07*np.arange(50000))
    result = repeat_features(tone, 2500000)
    assert result['repeat_coherence'] == pytest.approx(1)
    assert abs(result['repeat_excess']) < 1e-10
    assert spectrum_features(tone, 2500000)['spectral_peak_fraction'] > .4


def test_spectrum_is_scale_invariant():
    x = noise()
    for key, value in spectrum_features(x, 2500000).items():
        assert spectrum_features(x*3, 2500000)[key] == pytest.approx(value)


def test_reduced_pilot_recovers_planted_epoch_without_glrt():
    # Arbitrary deterministic symbol replica tests the search arithmetic;
    # actual Qin templates are bound separately in the corpus experiment.
    exact = noise(count=3333)
    control = np.roll(exact, 187)
    x = noise(count=50000) * .02
    for frame in range(14):
        start = 123 + round(frame * 2500000 / 750)
        x[start:start+3333] += exact
    x *= np.exp(2j*np.pi*80000*np.arange(len(x))/2500000)
    score = reduced_pilot_features(x, 2500000, exact, control, half_width_hz=80000)
    assert score['pilot_epoch_sample'] == 123
    assert score['pilot_cfo_hz'] == 80000
    assert score['pilot_exact'] > .99
    assert score['pilot_margin'] > .7


def test_zero_and_invalid_inputs():
    zero = np.zeros(50000, complex)
    assert repeat_features(zero, 2500000)['repeat_excess'] == 0
    assert np.isfinite(list(power_features(zero, 2500000).values())).all()
    with pytest.raises(ValueError):
        power_features(np.array([np.nan]*1024), 2500000)
    with pytest.raises(ValueError):
        reduced_pilot_features(zero, 5000000, zero, zero)
