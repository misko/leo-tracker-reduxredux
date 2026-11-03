"""Integer screening must bound quantization and reject non-integer IQ."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from native_integer_screen import bound, transform


def geometry():
    return SimpleNamespace(OFDM_SYMBOL_DURATION_S=.0001, FRAME_RATE_HZ=1000,
                           _power_prefix=lambda x: np.r_[0., np.cumsum(abs(x)**2)])


def test_quantization_bound_covers_direct_complex_correlation():
    rng = np.random.default_rng(20261103)
    g = geometry()
    for maximum in (1, 127, 1023, 32767):
        values = (rng.integers(-maximum, maximum+1, 512)
                  + 1j*rng.integers(-maximum, maximum+1, 512))
        template = rng.normal(size=64) + 1j*rng.normal(size=64)
        args = values, template, 80_000., (-4000., 0., 4000.), (0, 1, 2), 80
        b = bound(g, args)
        assert b['eligible']
        assert 2*8*b['max_sample_component']*b['quantized_maximum'] < 2**31
        for s in (0, 8, 16):
            r = template[s:s+8] * np.exp(2j*np.pi*4000*np.arange(8)/80_000)
            q = (np.rint(r.real*b['reference_scale'])
                 + 1j*np.rint(r.imag*b['reference_scale']))/b['reference_scale']
            for i in (0, 30, 100):
                x = values[i:i+8]
                denominator = np.linalg.norm(x)*np.linalg.norm(r)
                delta = abs(abs(np.vdot(r, x))-abs(np.vdot(q, x)))/denominator
                assert delta <= b['absolute_error']


@pytest.mark.parametrize('value', [.5+1j, 32768+1j, 0j])
def test_unsupported_values_rejected(value):
    args = (np.full(512, value, complex), np.ones(64, complex),
            80_000., (0.,), (0, 1), 80)
    assert not bound(geometry(), args)['eligible']


def test_transform_preserves_original_normalization():
    root = Path(__file__).resolve().parents[2] / 'src/leo/analysis/starlink'
    source, grid = [(root / n).read_text() for n in
                    ('_native_acquisition.c', '_native_acquisition_grid.inc')]
    changed, candidate = transform(source, grid)
    assert '__builtin_cpu_supports("avxvnni")' in changed
    assert 'kernel->cfo_count != 24' in candidate
    assert '_mm256_dpwssd_avx_epi32' in candidate
    tail = '                double received_energy ='
    ending = '    kernel->invalid_geometry ='
    original_tail = grid.split(tail)[1].split(ending)[0]
    candidate_tail = candidate.split(tail)[1].split(
        '#if defined(LEO_GRID_AVX2_12_REGISTER_ACCUMULATION)')[0]
    assert original_tail == candidate_tail


def test_unknown_source_rejected():
    with pytest.raises(ValueError):
        transform('', '')
