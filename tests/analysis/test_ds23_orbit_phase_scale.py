"""Research model tests: causal joins, null identity and scale recovery."""

import copy
import numpy as np
import pytest

from ds23_orbit_phase_scale import attach_features, features, fit_scale, scale_for_elements
from learn_ds23_causal_phase_forecast import distribution_cost
from ds23_orbit_phase_scale import objective

LINES = [
    '1 44718U 19074F   26287.30500671  .00051103  00000-0  47053-3 0  9994',
    '2 44718  53.1476 210.4606 0005941  78.7099 281.4585 15.67147100382794',
]


def test_zero_coefficients_preserve_density_and_element_scale():
    errors = np.array([-.3, .1, 1.2]); sigma = np.array([1., 2., 3.])
    model = dict(multiplier=.6, nu=3.)
    x = np.tile(features(LINES), (3, 1))
    expected = distribution_cost(errors, sigma, .6, 3.).sum()
    assert objective(np.zeros(4), x, errors, sigma, model) == expected
    assert scale_for_elements(LINES, [0.]*4) == 1.


def test_scale_bounded_under_extreme_elements_and_coefficients():
    assert .25 <= scale_for_elements(LINES, [100.]*4) <= 4.
    assert .25 <= scale_for_elements(LINES, [-100.]*4) <= 4.


def test_join_uses_middle_element_never_target():
    versions = [dict(epoch=e, collected_utc_ns=e+10**9, lines=list(LINES)) for e in (10**9, 3*10**9, 6*10**9)]
    history = dict(cutoff_utc_ns=8*10**9, past_versions={'44718': versions})
    row = dict(norad=44718, validation_time_ns=7*10**9, age_s=4., epoch_gap_s=2.)
    forecast = dict(transitions=[row])
    first = attach_features(history, forecast)[0]
    changed = copy.deepcopy(history)
    changed['past_versions']['44718'][2]['lines'][1] = LINES[1].replace('15.67147100', '14.67147100')
    assert attach_features(changed, forecast)[0] == first
    assert first['feature_epoch_ns'] == 3*10**9
    changed['past_versions']['44718'][2]['collected_utc_ns'] = 9*10**9
    with pytest.raises(ValueError, match='future TLE'):
        attach_features(changed, forecast)


def test_recovers_heteroskedastic_scale_without_satellite_id_features():
    rng = np.random.default_rng(8123)
    x = np.c_[np.ones(8000), rng.uniform(-1., 1., (8000, 3))]
    theta = np.array([-.15, .35, -.25, .2])
    target = rng.normal(size=len(x)) * np.exp(x @ theta)
    rows = [dict(next_innovation_s=float(y), unit_forecast_s=0., predicted_sigma_s=1.,
                 age_s=0., scale_features=v.tolist()) for y, v in zip(target, x)]
    model = dict(multiplier=1., nu=None, shrinkage=0.)
    result = fit_scale(rows, model)
    np.testing.assert_allclose(result['coefficients'], theta, atol=.045, rtol=0)
    scalar = fit_scale(rows, model, conditional=False)
    assert scalar['coefficients'][1:] == [0., 0., 0.]
    assert result['objective'] < scalar['objective'] - 500
