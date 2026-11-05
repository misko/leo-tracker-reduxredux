from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.localization_v3.family_weighting import (
    candidate_profile,
    competitor_confidence,
    family_weights,
)
from leo.analysis.localization_v3.history_policy import paired_policy, validate_history
from leo.analysis.localization_v3.history_position import forecast_phase_mean, make_problem
from tests.analysis.test_localization_v3_position import prepared


def test_optional_orbit_prior_adds_variance_without_learning_multiple_owner_claim(monkeypatch):
    from leo.analysis.localization_v3 import history_position
    from leo.analysis.research.orbital_support import requires_multiple_orbital_owners

    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=0))}
    def modes(actual, labels, supported, kind):
        assert actual is scan and supported == [0] and kind == 'physical'
        return dict(time_s=scan.sky['time_s'],
            position_km=np.repeat(scan.sky['position_km'],3,axis=0),
            velocity_km_s=np.repeat(scan.sky['velocity_km_s'],3,axis=0)), []
    monkeypatch.setattr(history_position,'build_modes',modes)
    args = (scan,node,np.ones(41,bool),'c0',np.zeros(1),np.ones(1),np.zeros(1),1.,4.)
    nominal = make_problem(*args)
    prior = make_problem(*args,support_policy='active_uncertainty')
    assert nominal.supported == [] and prior.supported == [0]
    assert not requires_multiple_orbital_owners(prior,0)
    assert len(prior.calculate(np.zeros(2))['coefficient']) == (
        len(nominal.calculate(np.zeros(2))['coefficient'])+3)
    with pytest.raises(ValueError,match='unknown physical orbital support'):
        make_problem(*args,support_policy='unqualified')


def test_family_support_uses_active_receiver_owners_and_conditional_confidence():
    rows = [dict(candidate_index=0) for _ in range(3)]
    tracks = [dict(receiver=1, channel=1), dict(receiver=1, channel=2), dict(receiver=2, channel=1)]
    weights, owners, count = family_weights(rows, [0, 1, 2], tracks, [.96, .94, 1.],
                                            'cross_rx_support', [20, 20, 0])
    np.testing.assert_array_equal(weights, [.6, .2, .6])
    assert owners == {0: {(1, 1), (1, 2)}} and count == {0: 40}
    weights, _, _ = family_weights(rows, [0, 1, 2], tracks, [0., 0., 0.],
                                    'cross_rx_support', [20, 20, 1])
    np.testing.assert_array_equal(weights, np.ones(3))


def test_full_catalogue_profile_preserves_aliases_and_rejects_below_horizon():
    t = np.arange(20.)
    signal = 100*t*t
    frequency = np.stack([signal, signal+2*1.0e6])
    result = candidate_profile(signal, frequency, np.ones_like(frequency)*100.,
        np.stack([np.ones(20)*30, np.ones(20)*-1]), 150., np.ones(2))
    assert np.isfinite(result['cost'][0]) and np.isinf(result['cost'][1])
    assert result['rms_hz'][0] == 0
    weight, gap = competitor_confidence(result['cost'], 0)
    assert weight > .99 and np.isinf(gap)


def history():
    raw = dict(case='SCAN', origin_utc_ns=100, cutoff_utc_ns=90,
               past_versions={'unused-candidate': [dict(epoch=80, collected_utc_ns=85)]})
    forecast = dict(case='SCAN', strictly_pre_RF=True, GPS_or_radio_used=False,
        history_sha256='bound',
        distribution_validation=dict(count=30, negative_twice_log_density=9.),
        original_distribution_validation=dict(count=30, negative_twice_log_density=10.),
        all_past_distribution=dict(shrinkage=.5, multiplier=2., nu=4., fallback=False))
    return raw, forecast


def check_history(raw, forecast):
    return validate_history(raw, forecast, case='SCAN', origin_utc_ns=100,
                             cutoff_utc_ns=90, raw_sha256='bound')


def test_history_checks_all_candidates_and_uses_validation_fallback():
    raw, forecast = history()
    model, qualified = check_history(raw, forecast)
    assert qualified and model == forecast['all_past_distribution']
    model['shrinkage'] = .9
    assert forecast['all_past_distribution']['shrinkage'] == .5
    future = deepcopy(raw)
    future['past_versions']['unused-candidate'][0]['collected_utc_ns'] = 91
    with pytest.raises(ValueError, match='post-scan'):
        check_history(future, forecast)
    forecast['distribution_validation']['count'] = 29
    model, qualified = check_history(raw, forecast)
    assert not qualified and model == dict(shrinkage=0., multiplier=1., nu=None, fallback=True)


@pytest.mark.parametrize('field,value', [('history_sha256', 'changed'), ('case', 'different'),
                                        ('GPS_or_radio_used', True)])
def test_history_identity_and_inference_independence_are_required(field, value):
    raw, forecast = history()
    forecast[field] = value
    with pytest.raises(ValueError):
        check_history(raw, forecast)


def test_phase_forecast_uses_causal_alignment_and_caps_extrapolation():
    receipts = [dict(old_new_alignment_s=10., previous_epoch_gap_s=100., age_s=500., sigma_s=2.),
                dict(old_new_alignment_s=None, previous_epoch_gap_s=None, age_s=500., sigma_s=1.)]
    np.testing.assert_array_equal(forecast_phase_mean(receipts, .5), [-6., 0.])


def test_history_posterior_carries_absolute_phase_mean_and_frozen_curve_noise():
    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=0))}
    p = make_problem(scan, node, np.ones(41, bool), 'c0', np.zeros(1), np.ones(1),
                     np.array([.1]), 2., 4.)
    result = p.calculate(np.zeros(2))
    expected = np.zeros(len(result['coefficient']))
    expected[p.hardware.shape[1]+p.smooth.shape[1]] = .05
    np.testing.assert_array_equal(result['coefficient'], result['latent_coefficient']+expected)
    np.testing.assert_array_equal(p.phase_sigma, [2.])
    np.testing.assert_array_equal(p.point_noise, np.full(41, 150.))


def test_predictive_pair_falls_back_together_on_one_arm_failure_or_nonconvergence():
    curved = {'sentinel': 'curved pair'}
    linear = {arm:dict(gates=dict(tracks=[dict(compatible=True)]),
                       linear_gates=[dict(compatible=True)], final_phase_change_s=0.,
                       endpoint_east_north_km=np.zeros(2)) for arm in ('c0', 'fitted_c')}
    selected, accepted = paired_policy(curved, linear)
    assert accepted and selected is linear
    linear['fitted_c']['linear_gates'][0]['compatible'] = False
    assert paired_policy(curved, linear) == (curved, False)
    linear['fitted_c']['linear_gates'][0]['compatible'] = True
    linear['fitted_c']['final_phase_change_s'] = .011
    assert paired_policy(curved, linear) == (curved, False)
