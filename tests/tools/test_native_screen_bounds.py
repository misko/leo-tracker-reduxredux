"""Candidate bounds must depend on inputs, with explicit exceptional-case fallback."""

from types import SimpleNamespace

import numpy as np
from native_screen_bounds import bound

ACQUISITION = SimpleNamespace(OFDM_SYMBOL_DURATION_S=.04, FRAME_RATE_HZ=10,
                             _power_prefix=lambda v: np.r_[0., np.cumsum(abs(v)**2)])


def test_safe_range_has_positive_bound_and_scales_with_signal():
    rng = np.random.default_rng(16)
    values = rng.normal(size=100) + 1j*rng.normal(size=100)
    template = rng.normal(size=20) + 1j*rng.normal(size=20)
    args = (values, template, 100., (0., 1.), (0, 1, 2), 10)
    result = bound(ACQUISITION, args)
    assert result['eligible'] and 0 < result['absolute_error'] < .1
    assert not result['production_qualified']
    scaled = bound(ACQUISITION, (values*4, template*2, *args[2:]))
    assert scaled['eligible']
    np.testing.assert_allclose(result['absolute_error'], scaled['absolute_error'], rtol=1e-12)


def test_unsupported_inputs_request_fallback():
    values, template = np.ones(100, complex), np.ones(20, complex)
    tails = (100., (0., 1.), (0, 1, 2), 10)
    for samples, reference in [(values*0, template), (values*1e20, template),
                               (values*np.nan, template), (values, template*1e-100),
                               (values.astype(np.complex64), template),
                               (values, template.astype(np.complex64))]:
        assert not bound(ACQUISITION, (samples, reference, *tails))['eligible']


def test_energy_allowance_covers_prefix_cancellation_against_extended_precision():
    rng = np.random.default_rng(51)
    values = np.r_[np.full(300, 1e8), rng.normal(size=700)*3].astype(complex)
    template = np.ones(20, complex)
    result = bound(ACQUISITION, (values, template, 100., (0., 1.), (0, 1, 2), 10))
    assert result['eligible']
    prefix = ACQUISITION._power_prefix(values)
    received = prefix[4:] - prefix[:-4]
    wide = values.real.astype(np.longdouble)**2 + values.imag.astype(np.longdouble)**2
    exact = np.array([np.sum(wide[i:i+4]) for i in range(len(values)-3)])
    positive = received > 0
    ratios = exact[positive]/received[positive]
    assert np.max(ratios) <= result['maximum_energy_ratio']
