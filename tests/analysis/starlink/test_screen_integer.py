"""The component bound must safely cover reference quantization at high IQ amplitude."""

from types import SimpleNamespace

import numpy as np

from leo.analysis.starlink._screen_integer import bound


def test_worst_accumulation_range_and_reference_quantization():
    geometry = SimpleNamespace(OFDM_SYMBOL_DURATION_S=.0001, FRAME_RATE_HZ=1000,
                               _power_prefix=lambda x: np.r_[0., np.cumsum(abs(x)**2)])
    rng = np.random.default_rng(20261103)
    x = np.full(512, 32767*(1+1j))
    reference = rng.normal(size=64) + 1j*rng.normal(size=64)
    args = x, reference, 80_000., (0., 3000.), (0, 1, 2), 80
    result = bound(geometry, args)
    assert result['eligible']
    qmax = result['quantized_maximum']
    assert 2*8*32767*qmax < 2**31
    r = reference[:8]*np.exp(2j*np.pi*3000*np.arange(8)/80000)
    scale = result['reference_scale']
    q = (np.rint(r.real*scale) + 1j*np.rint(r.imag*scale))/scale
    delta = abs(abs(np.vdot(r, x[:8]))-abs(np.vdot(q, x[:8])))
    delta /= np.linalg.norm(x[:8])*np.linalg.norm(r)
    assert delta <= result['absolute_error']
