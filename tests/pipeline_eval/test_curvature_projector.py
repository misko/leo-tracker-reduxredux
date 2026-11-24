from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from curvature_projector import CurveRows, ReceiverProjector, rank_preference


def test_weighted_projection_matches_one_combined_design():
    times = (np.arange(9.)**2, np.arange(1., 10.)*3.)
    mock = np.random.default_rng(153)
    scales = (np.linspace(0.4, 1., 9), np.linspace(0.8, 1.5, 9))
    curve = [CurveRows(t, mock.normal(size=9), w, mock.normal(size=(9, 2)), q)
             for t, w, q in zip(times, scales, (0.9, 1.1), strict=True)]
    frequencies = mock.normal(size=(2, 9))
    raw = np.concatenate([(c.values-c.rf_ratio*f)*c.inverse_sigma for c, f in zip(curve, frequencies, strict=True)])
    full = np.zeros((18, 6))
    for i, c in enumerate(curve):
        block = slice(i*9, (i+1)*9)
        full[block, 2*i:2*i+2] = c.inverse_sigma[:, None]*np.column_stack((np.ones(9), c.times))
        full[block, 4:] = c.rf_ratio*c.inverse_sigma[:, None]*c.smooth
    expected = raw-full@np.linalg.lstsq(full, raw, rcond=None)[0]
    model = ReceiverProjector(curve)
    assert model.dimension == 12
    assert model.score(frequencies) == pytest.approx(expected@expected, abs=1e-12)


def test_true_shared_coefficients_cancel_but_independent_receiver_smooth_does_not():
    times = np.arange(7.)
    basis = ((times-4.)**2)[:, None]
    flat = np.ones(7)
    c = CurveRows(times, 1e6+times*700+4*basis[:, 0], flat, basis, 1.)
    d = CurveRows(times, -1e6-times*45+4*basis[:, 0], flat, basis, 1.)
    model = ReceiverProjector([c, d])
    np.testing.assert_allclose(model.score([np.zeros(7)]*2), 0., atol=1e-17)
    assert model.score([np.zeros(7), basis[:, 0]]) > 10.


def test_only_strict_finite_comparable_pairs_order():
    assert rank_preference([1., 1.]) is None
    assert rank_preference([3., 2.]) == 1
    assert rank_preference([2., 3.]) == 0
    with pytest.raises(ValueError):
        rank_preference([1., np.inf])
