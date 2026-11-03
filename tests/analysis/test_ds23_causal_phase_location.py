import numpy as np
import pytest

from ds23_causal_phase_location import location_feature, qualify, adjust_means


def fixture_rows():
    # Constant signed bias with a balanced, deterministic innovation pattern.
    return [dict(norad=i, validation_time_ns=0 if i < 200 else 2,
        predicted_sigma_s=1., age_s=43200., unit_forecast_s=0.,
        next_innovation_s=1.5+(-.2 if i % 2 else .2)) for i in range(400)]


def test_signed_bias_qualifies_on_later_updates_and_unseen_satellites():
    model = dict(shrinkage=0., multiplier=1., nu=None)
    result = qualify(fixture_rows(), 1, model, model)
    assert result['qualified']
    assert abs(result['coefficient']-1.5) < .02
    assert result['disjoint_future_gain'] > 0


def test_later_and_held_satellite_targets_do_not_change_prefix_fit():
    model = dict(shrinkage=0., multiplier=1., nu=None)
    rows = fixture_rows()
    before = qualify(rows, 1, model, model)['prefix']
    changed = [dict(r, next_innovation_s=-7.) if r['validation_time_ns'] > 1 or r['norad'] % 5 == 0 else r for r in rows]
    after = qualify(changed, 1, model, model)['prefix']
    assert before == after


def test_unqualified_correction_is_an_exact_null():
    ordinary = np.array([.3, -.2])
    np.testing.assert_array_equal(adjust_means(ordinary, [], {}, dict(qualified=False)), ordinary)


def test_negative_age_is_rejected():
    with pytest.raises(ValueError):
        location_feature('age', [1.], [-1.], 1.)
