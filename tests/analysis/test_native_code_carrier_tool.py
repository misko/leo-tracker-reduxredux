import numpy as np
from probe_native_code_carrier import interpolate_periodic,periodic_upsample


def test_fourier_upsampling_recovers_fractional_tone_phase_across_period_seam():
    n=64;factor=32;k=7;wave=np.exp(2j*np.pi*k*np.arange(n)/n)
    fine=periodic_upsample(wave,factor);positions=np.array([-.2,.3,63.9,64.4,128.8])
    actual=interpolate_periodic(fine,positions*factor)
    expected=np.exp(2j*np.pi*k*positions/n)
    np.testing.assert_allclose(actual,expected,atol=6e-5)


def test_real_nyquist_tone_stays_real_and_preserves_original_samples():
    x=(-1.)**np.arange(16);fine=periodic_upsample(x,8)
    np.testing.assert_allclose(fine.real,np.cos(np.pi*np.arange(128)/8),atol=1e-14)
    np.testing.assert_allclose(fine.imag,0,atol=1e-14)
    np.testing.assert_allclose(fine[::8],x,atol=1e-14)


def test_odd_length_complex_waveform_preserves_all_original_samples():
    rng=np.random.default_rng(17);x=rng.normal(size=15)+1j*rng.normal(size=15)
    np.testing.assert_allclose(periodic_upsample(x,4)[::4],x,atol=1e-14)
