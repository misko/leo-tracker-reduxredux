"""Numerical invariants, planted timing, and interference controls."""
import numpy as np
import pytest

from tools.fast8_cfo_free_checks import (
    coherent_repeat_features,
    multi_repeat_features,
    prepare_bank,
    template_features,
)


def signal(seed, n):
    rng = np.random.default_rng(seed)
    return rng.normal(size=n)+1j*rng.normal(size=n)


@pytest.mark.parametrize('lags', [(0,), (1,), (1, 2, 4)])
def test_template_gain_cfo_invariance_and_timing(lags):
    exact, control = signal(1, 10000), signal(2, 10000)
    bank = prepare_bank(exact, control, lags)
    x = np.tile(np.roll(exact, 127), 5)
    original = template_features(x, bank)
    assert original['epoch_sample'] == 127
    assert original['exact'] == pytest.approx(1, abs=1e-12)
    assert original['margin'] > .95
    for cfo in (-400000, -120000, 120000, 400000):
        shifted = 3*x*np.exp(2j*np.pi*cfo*np.arange(len(x))/2500000)
        result = template_features(shifted, bank)
        assert result['epoch_sample'] == 127
        assert result['margin'] == pytest.approx(original['margin'], abs=1e-11)


def test_multi_repeat_fractional_frame_period():
    # An exactly periodic, bandlimited waveform with a fractional sampled
    # frame period. Three repeated rounded 3333-sample blocks would be wrong.
    rng = np.random.default_rng(5)
    spectrum = np.zeros(10000, complex)
    indexes = np.arange(-3000, 3001, 3)
    spectrum[indexes % 10000] = rng.normal(size=len(indexes))+1j*rng.normal(size=len(indexes))
    x = np.tile(np.fft.ifft(spectrum), 5)
    result = multi_repeat_features(x)
    for frame in (1, 2, 3):
        assert result[f'repeat_frame{frame}_excess'] > .99
    shifted = multi_repeat_features(x*np.exp(2j*np.pi*120000*np.arange(len(x))/2500000))
    assert shifted['repeat_multi_excess'] == pytest.approx(result['repeat_multi_excess'], abs=.001)


def test_repetition_controls_reject_tones_and_noise():
    x = signal(6, 50000)
    assert abs(coherent_repeat_features(x)['repeat_long_excess']) < .001
    assert abs(multi_repeat_features(x)['repeat_multi_excess']) < .001
    tone = np.exp(2j*np.pi*.071*np.arange(50000))
    assert abs(coherent_repeat_features(tone)['repeat_long_excess']) < 1e-12
    assert abs(multi_repeat_features(tone)['repeat_multi_excess']) < 1e-8


def test_zero_and_geometry_validation():
    zero = np.zeros(50000, complex)
    bank = prepare_bank(signal(1,10000), signal(2,10000), (1,2,4))
    assert template_features(zero, bank)['margin'] == 0
    assert coherent_repeat_features(zero)['repeat_long_excess'] == 0
    assert multi_repeat_features(zero)['repeat_multi_excess'] == 0
    with pytest.raises(ValueError):
        template_features(zero[:49999], bank)
    with pytest.raises(ValueError):
        prepare_bank(np.zeros(3333),np.zeros(3333),(1,))
