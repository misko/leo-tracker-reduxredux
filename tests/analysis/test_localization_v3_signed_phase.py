import numpy as np
import pytest

from leo.analysis.localization_v3.signed_phase import adjust_means, location_feature, qualify


def transitions(target=2.):
    return [dict(validation_time_ns=0 if i < 40 else 1,
                 norad=1 if i < 80 else 5, predicted_sigma_s=.5, age_s=3600.,
                 unit_forecast_s=0., next_innovation_s=target) for i in range(120)]


def test_signed_prior_requires_improvement_on_later_and_satellite_disjoint_evidence():
    model = dict(shrinkage=0., multiplier=1., nu=None)
    result = qualify(transitions(), 0, model, model)
    assert result['qualified'] and result['kind'] == 'seconds'
    assert 1.4 < result['coefficient'] < 3.
    assert result['training_count'] == result['disjoint_future_count'] == 40
    assert result['future_count'] == 80
    assert not qualify(transitions(0.), 0, model, model)['qualified']
    # Plenty of transitions alone is insufficient without a separate family group.
    no_disjoint = [dict(r, norad=1) for r in transitions()]
    assert not qualify(no_disjoint, 0, model, model)['qualified']


def test_signed_adjustment_respects_phase_cap_and_does_not_mutate_ordinary_means():
    original = np.array([14., -2.])
    receipts = [dict(sigma_s=10., age_s=0.), dict(sigma_s=.5, age_s=0.)]
    adjusted = adjust_means(original, receipts, dict(multiplier=1.),
        dict(qualified=True, kind='seconds', coefficient=3.))
    np.testing.assert_array_equal(adjusted, [15., 1.])
    np.testing.assert_array_equal(original, [14., -2.])
    unchanged = adjust_means(original, receipts, {}, dict(qualified=False))
    assert unchanged is not original
    np.testing.assert_array_equal(unchanged, original)


def test_signed_features_use_causal_age_and_reject_invalid_scale():
    np.testing.assert_array_equal(location_feature('age', [1., 2.], [0., 43200.], 2.), [0., 1.])
    np.testing.assert_array_equal(location_feature('standardized', [1., 2.], 0., 2.), [2., 4.])
    for sigma, age, multiplier in [(0., 1., 1.), (1., -1., 1.), (1., 1., np.nan)]:
        with pytest.raises(ValueError):
            location_feature('age', sigma, age, multiplier)
