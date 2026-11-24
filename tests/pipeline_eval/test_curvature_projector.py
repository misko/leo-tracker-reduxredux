from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from curvature_projector import CurveRows, ReceiverProjector, rank_preference
from curvature_projector_trial import phase_inputs, phase_vector


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


def test_only_actual_nominated_phase_rows_cross_the_paired_phase_port():
    from types import SimpleNamespace

    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency

    positions = np.tile([7000., 2., 3.], (4, 2, 1))
    velocities = np.tile([1., 3., 7.], (4, 2, 1))
    bank = dict(time_s=np.array([0., 10.]), position_km=positions, velocity_km_s=velocities)
    phases = phase_vector(SimpleNamespace(norads=[101, 202, 303, 404]), [0, 3], [1., -1.])
    used, remapped, subset = phase_inputs(bank, np.array([3, 0, 3]))
    assert np.isnan(phases[1:3]).all()
    assert used.tolist() == [0, 3]
    assert remapped.tolist() == [1, 0, 1]
    assert phases[used].tolist() == [1., -1.]
    frequency, elevation = paired_phase_frequency(subset, np.array([4., 4., 4.]), remapped, phases[used], 0., 0.)
    assert np.isfinite(frequency).all() and np.isfinite(elevation).all()
    assert frequency[0] == frequency[2] != frequency[1]
