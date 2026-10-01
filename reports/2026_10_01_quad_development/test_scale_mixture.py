import numpy as np
from scale_mixture import mixture, held_prediction, track_weights
from scale_prediction import log_density


def test_singleton_and_empty_training():
    row = dict(d=7, q=5., logdet=3.)
    np.testing.assert_allclose(mixture([row]), log_density(7, 5., 3.), atol=1e-12)
    value, probability = held_prediction(row, [])
    np.testing.assert_allclose(value, mixture([row]), atol=1e-12)
    assert probability == .5


def test_conditional_ratio_matches_training_responsibility():
    rows = [dict(d=7, q=q, logdet=4.) for q in (1., 3., 80.)]
    value, _ = held_prediction(rows[-1], rows[:-1])
    np.testing.assert_allclose(value, mixture(rows)-mixture(rows[:-1]), atol=1e-12)


def test_extreme_statistics_stay_finite():
    rows = [dict(d=7, q=1e100, logdet=1e4), dict(d=20, q=.01, logdet=-100.)]
    assert np.isfinite(mixture(rows))
    weights, probability = track_weights(rows)
    assert np.isfinite(weights).all() and 0 <= probability <= 1


def test_mixture_track_weights_match_joint_gradient():
    rows = [dict(d=7, q=q, logdet=3.) for q in (2., 40., 9.)]
    weights, _ = track_weights(rows)
    for i in range(3):
        plus = [dict(r) for r in rows]; minus = [dict(r) for r in rows]
        plus[i]['q'] += 1e-4; minus[i]['q'] -= 1e-4
        numeric = (mixture(plus)-mixture(minus))/2e-4
        np.testing.assert_allclose(numeric, -.5*weights[i], atol=1e-8)
