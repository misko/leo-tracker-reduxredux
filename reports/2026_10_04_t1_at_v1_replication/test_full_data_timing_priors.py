from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from full_data_timing_priors import PRECISIONS, specification, summarize
from timing_prior_ablation import PriorObjective, ScaledTimingObjective, TimingObjective, CalibrationObjective
from timing_model import zero_sum_basis


@pytest.mark.parametrize('mode', PRECISIONS)
def test_prior_value_gradient_and_fisher_all_change_together(mode):
    precision = PRECISIONS[mode]
    base = object.__new__(ScaledTimingObjective)
    base.prior_precision = precision; base.basis = zero_sum_basis(3); base.common_prior = True
    v = np.array([4., 2., 100., 1., 200., 3., 2., 3., -4.])
    value, gradient = base.penalty(v)
    raw, raw_gradient = TimingObjective.penalty(base, v)
    np.testing.assert_allclose(value, precision*raw)
    np.testing.assert_allclose(gradient, precision*raw_gradient)
    np.testing.assert_array_equal(gradient[:6], 0.)
    for j in range(len(v)):
        e = np.eye(len(v))[j]*1e-5
        fd = (base.penalty(v+e)[0]-base.penalty(v-e)[0])/2e-5
        assert abs(fd-gradient[j]) < 1e-7
    obj = object.__new__(PriorObjective); obj.size = 9; obj.base = base
    h0 = np.diag([4., 4., 4., 4., 4., 4., 4.01, 5., 5., 4.])
    with patch.object(CalibrationObjective, 'curvature', return_value=h0.copy()):
        actual = obj.curvature(np.zeros(10))
    expected = np.eye(10)*4.
    expected[6, 6] += .01*precision
    expected[7, 7] += precision; expected[8, 8] += precision
    np.testing.assert_allclose(actual, expected)


def test_uniform_is_bounded_and_gaussian_widths_are_std_not_variance():
    for mode in PRECISIONS:
        r = specification(mode)
        assert r['common_bound_s'] == 10. and r['total_satellite_bound_s'] == 20.
        assert r['relative_sum_zero']
    assert specification('uniform')['relative_sigma_s'] is None
    assert specification('wider')['relative_sigma_s'] == 3.
    assert specification('tighter')['relative_sigma_s'] == 1./3.
    assert specification('baseline')['common_sigma_s'] == 10.


def test_summary_keeps_fit_quality_separate_from_position_and_convergence():
    rows = []
    for arm in ('fitted-c', 'zero-c'):
        for mode in PRECISIONS:
            for scan in ('N01', 'N02'):
                changed = mode != 'baseline'
                rows.append(dict(scan=scan, arm=arm, mode=mode, distance_m=1200. if changed else 900.,
                    converged=not changed, boundary=False, posterior_weighted_residual_rms_hz=20. if changed else 40.,
                    data_nll=100. if changed else 200., roof_diagnostics={'gradient_norm_per_100m': 1.},
                    timing={'relative_timing_rms_s': .2}))
    summary = summarize(rows)
    assert len(summary) == 8
    for r in summary:
        if r['mode'] != 'baseline':
            assert r['worsened_over_1m'] == 2 and r['below_1km'] == 0 and r['converged'] == 0
            assert r['median_posterior_rms_hz'] == 20. and r['total_data_nll'] == 200.
