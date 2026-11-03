"""Numerical oracles for rejected research-only coarse correlation prototypes."""

import numpy as np
import pytest
from experimental_folded_gemm import folded_gemm

from leo.analysis.starlink import acquisition as a


@pytest.mark.hardware
@pytest.mark.parametrize('method', ['gemm', 'overlap_fft'])
@pytest.mark.parametrize('rate', [2_500_000, 10_000_000])
def test_experimental_correlations_preserve_partial_frame_scores(method, rate):
    if a._native_acquisition is None:
        pytest.skip('requires compiled native acquisition oracle')
    rng = np.random.default_rng(20261103)
    template = a.qin_edge_pilot_frame(rate, 'lower')
    values = rng.normal(size=len(template)*2+27)+1j*rng.normal(size=len(template)*2+27)
    values[:len(template)//2] = 0
    args = (values, template, rate, (-31371., 0., 80000.), (2, 28, 288), round(rate/750))
    expected = a._folded_anchor_score_grid_native(*args)
    actual = folded_gemm(*args, correlation=method)
    np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=1e-12)
    np.testing.assert_array_equal(np.argmax(actual, axis=1), np.argmax(expected, axis=1))
